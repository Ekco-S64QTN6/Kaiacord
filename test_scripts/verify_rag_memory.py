import torch
import psutil
import os
from kaia_rag import KaiaRAG

def print_memory():
    pid = os.getpid()
    py = psutil.Process(pid)
    print(f"RAM: {py.memory_info()[0] / 1024**3:.2f} GB")
    if torch.cuda.is_available():
        print(f"VRAM: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")

print("Initializing RAG...")
rag = KaiaRAG()
print("RAG Initialized.")
print_memory()
