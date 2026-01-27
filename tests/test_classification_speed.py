import asyncio
import time
import sys
import os

# Add current directory to path so we can import utils
sys.path.append(os.getcwd())

from utils.kaia_intelligence import QueryClassifier

async def test_classification():
    classifier = QueryClassifier(timeout=5.0)
    await classifier.pre_warm()
    
    test_queries = [
        "how are you feeling now?",
        "who are you?",
        "what's the latest news on AI?",
        "starkind has detected some substantial handicaps in modern ai architecture.",
        "tell me about the security breach at Microsoft",
        "ping",
        "yeah",
        "what is the meaning of life?"
    ]
    
    print(f"{'Query':<40} | {'Category':<10} | {'Time (s)':<10}")
    print("-" * 65)
    
    for query in test_queries:
        start_time = time.time()
        # Test fast_classify first
        fast_cat = classifier.fast_classify(query)
        fast_time = time.time() - start_time
        
        # Test full classify
        start_time = time.time()
        full_cat = await classifier.classify(query)
        full_time = time.time() - start_time
        
        print(f"{query:<40} | {full_cat:<10} | {full_time:.4f} (Fast: {fast_cat}, {fast_time:.4f})")

if __name__ == "__main__":
    asyncio.run(test_classification())
