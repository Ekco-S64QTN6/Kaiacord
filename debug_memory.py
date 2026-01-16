import torch
import os
import sys
import time

def print_memory(label):
    if torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f"[{label}] Allocated: {allocated:.2f} GB, Reserved: {reserved:.2f} GB")
    else:
        print(f"[{label}] CUDA not available")

print("Starting memory debug...")
print_memory("Start")

print("Importing kaia_rag...")
from kaia_rag import KaiaRAG
print_memory("After kaia_rag import")

print("Initializing KaiaRAG...")
rag = KaiaRAG()
print_memory("After KaiaRAG init")

print("Importing kaia_image...")
from kaia_image import generate_image
print_memory("After kaia_image import")

# Check if we can clear it
import gc
del rag
gc.collect()
torch.cuda.empty_cache()
print_memory("After cleanup")
