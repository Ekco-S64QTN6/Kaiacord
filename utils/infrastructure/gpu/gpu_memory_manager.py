"""
Simplified GPU Memory Manager
==============================

Lightweight GPU guard that focuses on concurrency gating via semaphore.
Complex reservation and preemption logic removed to ensure stability
and eliminate event loop hangs.
"""

import asyncio
import logging
import uuid
import time
from contextvars import ContextVar
from enum import Enum
from utils.infrastructure.logging.kaia_logger import log_debug
from utils.infrastructure.gpu.gpu_manager import gpu_semaphore, ModelContextMonitor

logger = logging.getLogger(__name__)

class GPUTaskPriority(Enum):
    """Priority levels for GPU tasks (Simplified for compatibility)"""
    CRITICAL = 0
    CHAT = 1
    EMBEDDING = 2

# Track if the current task is already inside a GPU-guarded block
_gpu_context_active = ContextVar('gpu_context_active', default=False)

class GPUMemoryManager:
    """
    Simplified GPU guard.
    Prioritizes stability by removing complex VRAM reservation/preemption logic.
    Reliability over aggressive resource optimization.
    """
    
    def __init__(self):
        self._torch = None
        self._cuda_available = None

    def _lazy_import_torch(self):
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
        self._lazy_import_torch()
        return self._cuda_available
    
    def get_vram_status(self) -> dict:
        torch = self._lazy_import_torch()
        if not torch or not self.is_cuda_available():
            return {'total': 0.0, 'allocated': 0.0, 'free': 0.0}
        try:
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            allocated = torch.cuda.memory_allocated() / 1024**3
            free = total - allocated
            return {'total': total, 'allocated': allocated, 'free': free}
        except Exception:
            return {'total': 0.0, 'allocated': 0.0, 'free': 0.0}

    async def run_with_gpu_guard(
        self, 
        model_name: str, 
        priority: GPUTaskPriority = GPUTaskPriority.CHAT, 
        coro = None, 
        vram_gb: float = 0.0, # Ignored in simplified version
        task_id: str = None
    ):
        """
        Gated execution for GPU tasks via semaphore.
        """
        if task_id is None:
            task_id = f"gpu_{uuid.uuid4().hex[:6]}"

        if _gpu_context_active.get():
            return await coro

        token = _gpu_context_active.set(True)
        try:
            async with gpu_semaphore:
                await ModelContextMonitor.set_model(model_name)
                t_start = time.time()
                log_debug(f"[{task_id}] Executing protected GPU coro: {model_name}")
                result = await coro
                log_debug(f"[{task_id}] Finished in {time.time() - t_start:.2f}s")
                return result
        finally:
            _gpu_context_active.reset(token)

    # Legacy Stubs
    async def request_vram(self, *args, **kwargs): return True
    async def release_vram(self, *args, **kwargs): return True
    def get_memory_pressure(self) -> str: return 'low'

# Global instance
gpu_memory_manager = GPUMemoryManager()
