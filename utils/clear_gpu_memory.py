#!/usr/bin/env python3
"""
Utility script to aggressively clear GPU memory when Kaiacord has OOM issues.
Run this script to reset PyTorch's CUDA allocator without restarting the bot.
"""

import gc
import sys

def clear_gpu_memory():
    """Aggressively clear all GPU memory"""
    # Lazy import to avoid Python 3.14 startup hang from torch.quantization
    import torch
    
    if not torch.cuda.is_available():
        print("CUDA not available")
        return
    
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
    
    # Show memory stats
    allocated = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    total = torch.cuda.get_device_properties(0).total_memory / 1024**3
    
    print(f"\n=== GPU Memory Status ===")
    print(f"Allocated: {allocated:.2f} GiB")
    print(f"Reserved:  {reserved:.2f} GiB")
    print(f"Total:     {total:.2f} GiB")
    print(f"Free:      {total - allocated:.2f} GiB")
    print("="*25)

if __name__ == "__main__":
    clear_gpu_memory()
