"""
Compatibility shim — re-exports from gpu_manager.py.

This file exists only to protect legacy imports. Do NOT add logic here.
All GPU management code lives in utils/infrastructure/gpu/gpu_manager.py.
Converted to shim: February 26, 2026.
"""
from utils.infrastructure.gpu.gpu_manager import (
    GPUMemoryManager,
    GPUTaskPriority,
    gpu_memory_manager,
)

__all__ = ["GPUMemoryManager", "GPUTaskPriority", "gpu_memory_manager"]
