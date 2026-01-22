import sys
import os
import asyncio
import time
import shutil
import ollama

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import SemanticCache, QueryClassifier, PerformanceMonitor
from utils.kaia_logger import log_success, log_info, log_error

async def stress_test():
    log_info("Starting Kaia 2.0 Stress Test...")
    client = ollama.AsyncClient()
    monitor = PerformanceMonitor()
    cache = SemanticCache(threshold=0.80)
    classifier = QueryClassifier(client)
    
    user_id = 123
    
    tests = [
        ("hi kaia", "casual", "Rule-based check"),
        ("hi kaia", "casual", "Exact cache check"),
        ("hey kaia", "casual", "Semantic cache check"),
        ("who am i", "identity", "Rule-based identity"),
        ("what is quantum physics?", "knowledge", "Model-based classification"),
        ("draw a cat", "command", "Rule-based command"),
    ]
    
    for i, (query, expected_cat, note) in enumerate(tests):
        log_info(f"\nTest {i+1}: '{query}' ({note})")
        
        start = time.time()
        
        # 1. Cache Check
        cached = await cache.get(query, user_id, monitor=monitor)
        if cached:
            log_success(f"Cache hit! Time: {(time.time()-start)*1000:.1f}ms")
        else:
            log_info("Cache miss. Processing...")
            
            # 2. Classification
            monitor.start_timer('classify')
            cat = await classifier.classify(query)
            monitor.stop_timer('classify', 'classification_time')
            log_info(f"Classified as: {cat}")
            
            # 3. Simulate Response & Cache
            response = f"Simulated response for {query}"
            await cache.set(query, response, user_id)
            log_info(f"Total processing time: {(time.time()-start)*1000:.1f}ms")

    log_info("\n" + monitor.get_report())
    
    # Verify exact cache hit rate
    if monitor.metrics['exact_hits'] >= 1:
        log_success("Exact cache hit verified.")
    else:
        log_error("Exact cache hit failed.")

if __name__ == "__main__":
    asyncio.run(stress_test())
