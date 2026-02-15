
import os
import time
import psutil
import re
from rank_bm25 import BM25Okapi

class MockNode:
    def __init__(self, text):
        self.text = text
    def get_content(self):
        return self.text

def tokenize(text):
    return re.sub(r'[^\w\s]', ' ', text.lower()).split()

def test_optimized_memory(node_count, words_per_node=200):
    print(f"Testing Optimized BM25 with {node_count} nodes...")
    process = psutil.Process(os.getpid())
    start_mem = process.memory_info().rss / (1024 * 1024)
    
    dummy_text = "This is a sample node with some random words to simulate real data. " * (words_per_node // 10)
    nodes = [MockNode(dummy_text) for _ in range(node_count)]
    
    print("  Tokenizing and initializing BM25 (docs will be local variable)...")
    tokenized_docs = [tokenize(node.get_content()) for node in nodes]
    bm25 = BM25Okapi(tokenized_docs)
    
    mid_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Memory with tokenized docs: {mid_mem:.2f} MB")
    
    # Simulate doc list going out of scope
    del tokenized_docs
    import gc
    gc.collect()
    
    final_mem = process.memory_info().rss / (1024 * 1024)
    print(f"  Memory AFTER GC: {final_mem:.2f} MB")
    print(f"  SAVINGS: {mid_mem - final_mem:.2f} MB")
    
    # Verify retrieval still works
    query = tokenize("sample random")
    scores = bm25.get_scores(query)
    print(f"  Retrieval check: {len(scores)} scores generated.")

if __name__ == "__main__":
    test_optimized_memory(150000)
