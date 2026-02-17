
import os
import time
import psutil
from llama_index.core import StorageContext, load_index_from_storage
import logging

logging.getLogger().setLevel(logging.ERROR)

def profile_index(itype, persist_dir="./memory/rag_storage"):
    path = os.path.join(persist_dir, itype)
    if not os.path.exists(path):
        print(f"Skipping {itype} (dir missing)")
        return
        
    print(f"Profiling Index: {itype}")
    process = psutil.Process(os.getpid())
    start_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Initial Memory: {start_mem:.2f} MB")
    
    start_time = time.time()
    try:
        sc = StorageContext.from_defaults(persist_dir=path)
        index = load_index_from_storage(sc)
        end_time = time.time()
        end_mem = process.memory_info().rss / (1024 * 1024)
        print(f"  Success! Index loaded in {end_time - start_time:.2f}s")
        print(f"  Memory Spike: {end_mem - start_mem:.2f} MB (Total: {end_mem:.2f} MB)")
        
        # Check node count
        node_count = len(index.docstore.docs)
        print(f"  Nodes: {node_count}")
        
    except Exception as e:
        print(f"  FAILED: {e}")
    print("-" * 30)

if __name__ == "__main__":
    itypes = ['knowledge', 'logs', 'dreams', 'user_profiles', 'persona', 'conversations']
    for t in itypes:
        profile_index(t)
