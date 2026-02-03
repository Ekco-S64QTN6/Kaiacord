"""
Unified GPU Memory Manager
===========================

Centralized GPU memory management with reservation system, priority queue,
and preemption support.

This module consolidates GPU management logic from kaia_image.py, kaia_vision.py,
and gpu_manager.py into a single, unified manager.
"""

import asyncio
import gc
import logging
from typing import Optional, Dict, List
from enum import Enum
from dataclasses import dataclass
from utils.infrastructure.logging.kaia_logger import log_info, log_warning, log_error, log_success, log_debug

logger = logging.getLogger(__name__)


class GPUTaskPriority(Enum):
    """Priority levels for GPU tasks"""
    CHAT = 1          # Highest priority - chat model stays loaded
    VISION = 2        # Medium priority - can preempt image gen
    IMAGE_GEN = 3     # Lowest priority - yields to chat and vision


@dataclass
class GPUReservation:
    """Represents a GPU memory reservation"""
    task_id: str
    priority: GPUTaskPriority
    vram_gb: float
    model_name: str
    timestamp: float


class GPUMemoryManager:
    """
    Unified GPU memory manager with reservation system.
    
    Features:
    - VRAM reservation and tracking
    - Priority-based task management
    - Automatic preemption of lower-priority tasks
    - Memory pressure monitoring
    - Graceful degradation to CPU
    """
    
    def __init__(self):
        self.reservations: Dict[str, GPUReservation] = {}
        self.lock = asyncio.Lock()
        self._torch = None
        self._cuda_available = None
        
    def _lazy_import_torch(self):
        """Lazy import torch to avoid startup overhead"""
        if self._torch is None:
            try:
                import torch
                self._torch = torch
                self._cuda_available = torch.cuda.is_available()
            except ImportError:
                self._torch = False
                self._cuda_available = False
        return self._torch
    
    def is_cuda_available(self) -> bool:
        """Check if CUDA is available"""
        self._lazy_import_torch()
        return self._cuda_available
    
    def get_vram_status(self) -> Dict[str, float]:
        """
        Get current VRAM status.
        
        Returns:
            Dict with total, allocated, reserved, and free VRAM in GiB
        """
        torch = self._lazy_import_torch()
        if not torch or not self.is_cuda_available():
            return {
                'total': 0.0,
                'allocated': 0.0,
                'reserved': 0.0,
                'free': 0.0
            }
        
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        free = total - allocated
        
        return {
            'total': total,
            'allocated': allocated,
            'reserved': reserved,
            'free': free
        }
    
    async def request_vram(
        self, 
        task_id: str, 
        vram_gb: float, 
        priority: GPUTaskPriority,
        model_name: str
    ) -> bool:
        """
        Request VRAM reservation.
        
        Args:
            task_id: Unique identifier for this task
            vram_gb: Amount of VRAM needed in GiB
            priority: Task priority
            model_name: Name of the model
            
        Returns:
            True if reservation successful, False otherwise
        """
        async with self.lock:
            if not self.is_cuda_available():
                log_warning(f"CUDA not available, task {task_id} will use CPU")
                return False
            
            status = self.get_vram_status()
            
            log_debug(f"VRAM request: {task_id} needs {vram_gb:.1f} GiB")
            log_debug(f"  Current: {status['allocated']:.1f}/{status['total']:.1f} GiB")
            
            # Check if we have enough free VRAM
            if status['free'] >= vram_gb:
                # Grant reservation
                import time
                self.reservations[task_id] = GPUReservation(
                    task_id=task_id,
                    priority=priority,
                    vram_gb=vram_gb,
                    model_name=model_name,
                    timestamp=time.time()
                )
                log_success(f"✅ VRAM reserved for {task_id}: {vram_gb:.1f} GiB")
                return True
            
            # Check if we can preempt lower-priority tasks
            if await self._try_preempt(vram_gb, priority):
                # Retry after preemption
                status = self.get_vram_status()
                if status['free'] >= vram_gb:
                    import time
                    self.reservations[task_id] = GPUReservation(
                        task_id=task_id,
                        priority=priority,
                        vram_gb=vram_gb,
                        model_name=model_name,
                        timestamp=time.time()
                    )
                    log_success(f"✅ VRAM reserved for {task_id} after preemption: {vram_gb:.1f} GiB")
                    return True
            
            log_error(f"❌ Insufficient VRAM for {task_id}")
            return False
    
    async def _try_preempt(self, needed_vram: float, priority: GPUTaskPriority) -> bool:
        """
        Try to preempt lower-priority tasks to free VRAM.
        
        Args:
            needed_vram: Amount of VRAM needed
            priority: Priority of requesting task
            
        Returns:
            True if preemption successful
        """
        # Find lower-priority tasks
        preemptable = [
            (task_id, res) for task_id, res in self.reservations.items()
            if res.priority.value > priority.value
        ]
        
        if not preemptable:
            return False
        
        # Sort by priority (lowest first)
        preemptable.sort(key=lambda x: x[1].priority.value, reverse=True)
        
        freed = 0.0
        for task_id, res in preemptable:
            log_warning(f"Preempting {task_id} (priority {res.priority.name})")
            await self.release_vram(task_id)
            freed += res.vram_gb
            
            if freed >= needed_vram:
                return True
        
        return freed >= needed_vram
    
    async def release_vram(self, task_id: str) -> bool:
        """
        Release VRAM reservation.
        
        Args:
            task_id: Task identifier
            
        Returns:
            True if release successful
        """
        async with self.lock:
            if task_id in self.reservations:
                res = self.reservations.pop(task_id)
                log_info(f"Released VRAM for {task_id}: {res.vram_gb:.1f} GiB")
                
                # Trigger garbage collection
                gc.collect()
                if self.is_cuda_available():
                    torch = self._lazy_import_torch()
                    torch.cuda.empty_cache()
                
                return True
            return False
    
    def get_memory_pressure(self) -> str:
        """
        Get memory pressure level.
        
        Returns:
            'low', 'medium', 'high', or 'critical'
        """
        status = self.get_vram_status()
        if status['total'] == 0:
            return 'unavailable'
        
        usage_percent = (status['allocated'] / status['total']) * 100
        
        if usage_percent < 50:
            return 'low'
        elif usage_percent < 70:
            return 'medium'
        elif usage_percent < 90:
            return 'high'
        else:
            return 'critical'


# Global instance
gpu_memory_manager = GPUMemoryManager()
