import torch
import gc
import os
import psutil
import time
from kaia_image import _generate_image_sync

def print_memory_stats(step):
    pid = os.getpid()
    py = psutil.Process(pid)
    memory_use = py.memory_info()[0] / 2. ** 30  # memory use in GB...I think
    
    print(f"[{step}] RAM: {memory_use:.2f} GB")
    if torch.cuda.is_available():
        print(f"[{step}] VRAM Allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
        print(f"[{step}] VRAM Reserved:  {torch.cuda.memory_reserved() / 1024**3:.2f} GB")
    print("-" * 20)

def main():
    print("Starting Memory Leak Test...")
    print_memory_stats("Start")

    try:
        print("Generating Image 1...")
        _generate_image_sync("a test image")
        print("Image 1 Done.")
        print_memory_stats("After Image 1")
        
        time.sleep(2)
        
        print("Generating Image 2...")
        _generate_image_sync("another test image")
        print("Image 2 Done.")
        print_memory_stats("After Image 2")

    except Exception as e:
        print(f"Error: {e}")

    print("Forcing final GC...")
    gc.collect()
    torch.cuda.empty_cache()
    print_memory_stats("Final")

if __name__ == "__main__":
    main()
