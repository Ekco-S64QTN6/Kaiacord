
import os
import time
import psutil
import re
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core import Document

def profile_file(file_path):
    print(f"Profiling: {file_path}")
    process = psutil.Process(os.getpid())
    start_mem = process.memory_info().rss / (1024 * 1024)
    print(f"Initial Memory: {start_mem:.2f} MB")
    
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()
    
    doc = Document(text=text)
    parser = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    
    start_time = time.time()
    try:
        nodes = parser.get_nodes_from_documents([doc])
        end_time = time.time()
        end_mem = process.memory_info().rss / (1024 * 1024)
        print(f"Success! {len(nodes)} nodes created in {end_time - start_time:.2f}s")
        print(f"Memory Spike: {end_mem - start_mem:.2f} MB (Total: {end_mem:.2f} MB)")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    path = "knowledge_base/Books/Artificial Intelligence A Modern Approach by Stuart Russell and Peter Norvig.md"
    if os.path.exists(path):
        profile_file(path)
    else:
        print("File not found")
