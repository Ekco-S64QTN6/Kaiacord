
import os
import time
import psutil
import re
import numpy as np
from rank_bm25 import BM25Okapi

class MockNode:
    def __init__(self, text):
        self.text = text
    def get_content(self):
        return self.text

def tokenize(text):
    return re.sub(r'[^\w\s]', ' ', text.lower()).split()

def stress_test_bm25(node_count, words_per_node=200):
    print(f"Stress Testing BM25 with {node_count} nodes...")
    process = psutil.Process(os.getpid())
    start_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Initial Memory: {start_mem:.2f} MB")
    
    # 1. Create nodes
    print(f"  Creating mock nodes...")
    dummy_text = "This is a sample node with some random words to simulate real data. " * (words_per_node // 10)
    nodes = [MockNode(dummy_text) for _ in range(node_count)]
    mid_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Memory after nodes: {mid_mem:.2f} MB (Delta: {mid_mem - start_mem:.2f} MB)")
    
    # 2. Tokenize
    print(f"  Tokenizing...")
    start_time = time.time()
    tokenized_docs = [tokenize(node.get_content()) for node in nodes]
    tokenize_time = time.time() - start_time
    tok_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Memory after tokenization: {tok_mem:.2f} MB (Delta: {tok_mem - mid_mem:.2f} MB)")
    print(f"  Tokenization took: {tokenize_time:.2f}s")
    
    # 3. BM25 Init
    print(f"  Initializing BM25Okapi...")
    start_time = time.time()
    bm25 = BM25Okapi(tokenized_docs)
    bm25_time = time.time() - start_time
    final_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Final Memory: {final_mem:.2f} MB (Delta: {final_mem - tok_mem:.2f} MB)")
    print(f"  BM25 Init took: {bm25_time:.2f}s")
    print(f"  TOTAL MEMORY SPIKE: {final_mem - start_mem:.2f} MB")
    print("-" * 30)

if __name__ == "__main__":
    # Test with 50k nodes (representative of one large index)
    stress_test_bm25(50000)
    
    # Test with 150k nodes (extreme case or combined indices)
    stress_test_bm25(150000)
