#!/usr/bin/env python3
"""
Utility script to aggressively clear GPU memory when Kaiacord has OOM issues.
Run this script to reset PyTorch's CUDA allocator without restarting the bot.
"""

import gc
import sys


def clear_gpu_memory(silent: bool = False):
    """Aggressively clear all GPU memory"""
    # Lazy import to avoid Python 3.14 startup hang from torch.quantization
    try:
        import torch
    except ImportError:
        if not silent:
            print("PyTorch not installed")
        return
    
    if not torch.cuda.is_available():
        if not silent:
            print("CUDA not available")
        return
    
    if not silent:
        print("Clearing GPU memory...")
    
    # Empty cache multiple times
    for i in range(5):
        gc.collect()
        torch.cuda.empty_cache()
    
    # Synchronize CUDA operations
    torch.cuda.synchronize()
    
    # Reset memory stats
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.reset_accumulated_memory_stats()
    
    # Final cache clear
    torch.cuda.empty_cache()
    
    if not silent:
        print("GPU memory cleared")


def force_clear_gpu() -> bool:
    """
    Emergency GPU cleanup - more aggressive than clear_gpu_memory.
    
    Attempts to release ALL GPU memory including reserved pools.
    Use during shutdown or after critical failures.
    
    Returns:
        True if cleanup was successful, False otherwise
    """
    try:
        import torch
    except ImportError:
        return True  # No torch = nothing to clear = success
    
    if not torch.cuda.is_available():
        return True
    
    try:
        # Phase 1: Standard cleanup
        for _ in range(3):
            gc.collect()
            torch.cuda.empty_cache()
        
        torch.cuda.synchronize()
        
        # Phase 2: Reset allocator stats
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.reset_accumulated_memory_stats()
        
        # Phase 3: IPC cleanup for multi-process scenarios
        try:
            torch.cuda.ipc_collect()
        except:
            pass
        
        # Phase 4: Final aggressive cleanup
        for _ in range(5):
            gc.collect()
            torch.cuda.empty_cache()
        
        torch.cuda.synchronize()
        
        # Check result
        allocated = torch.cuda.memory_allocated() / 1024**3
        
        return allocated < 0.5  # Success if less than 0.5 GiB still allocated
        
    except Exception as e:
        print(f"GPU force clear error: {e}")
        return False


def kill_orphaned_runners():
    """Aggressively kill any lingering ollama runner processes to reclaim VRAM."""
    import psutil
    import os
    
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check for ollama runner processes
            cmdline = proc.info.get('cmdline') or []
            if 'ollama' in proc.info['name'].lower() and 'runner' in ' '.join(cmdline).lower():
                print(f"🔪 Killing orphaned Ollama runner (PID: {proc.info['pid']})")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    print("✨ Orphaned runners cleared.")


if __name__ == "__main__":
    kill_orphaned_runners()
    clear_gpu_memory()

