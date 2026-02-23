"""
gpu_memory_manager.py — compatibility shim
==========================================

All GPU memory management logic has been consolidated into gpu_manager.py.
This file exists solely to preserve backward-compatible imports for any
external scripts or cached references.

Do not add new logic here.
"""

# Re-export everything from the canonical source
from utils.infrastructure.gpu.gpu_manager import (
    GPUTaskPriority,
    GPUMemoryManager,
    gpu_memory_manager,
)

__all__ = ['GPUTaskPriority', 'GPUMemoryManager', 'gpu_memory_manager']
