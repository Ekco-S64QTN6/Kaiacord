import sys
import os
import asyncio
import time
import numpy as np

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import SemanticCache
from utils.kaia_logger import log_success, log_info, log_error

async def test_adaptive_cache():
    log_info("Starting Adaptive Cache Test...")
    # Small cache size to trigger pruning
    cache = SemanticCache(max_size=10, threshold=0.80)
    user_id = 123
    
    # 1. Fill the cache
    log_info("Filling cache with 10 items...")
    for i in range(10):
        query = f"Query number {i}"
        response = f"Response number {i}"
        await cache.set(query, response, user_id)
        
    log_info(f"Cache size: {len(cache.cache)}")
    
    # 2. Access some items multiple times to increase frequency
    log_info("Accessing Query 0 and Query 1 multiple times...")
    for _ in range(5):
        await cache.get("Query number 0", user_id)
        await cache.get("Query number 1", user_id)
        
    # 3. Add more items to trigger pruning
    log_info("Adding 5 more items to trigger pruning...")
    for i in range(10, 15):
        query = f"Query number {i}"
        response = f"Response number {i}"
        await cache.set(query, response, user_id)
        
    log_info(f"Cache size after pruning: {len(cache.cache)}")
    
    # 4. Check if frequently accessed items survived
    res0 = await cache.get("Query number 0", user_id)
    res1 = await cache.get("Query number 1", user_id)
    
    if res0 and res1:
        log_success("Frequently accessed items survived pruning!")
    else:
        log_error(f"Frequently accessed items were pruned. Res0: {res0}, Res1: {res1}")
        
    # 5. Check if some old, infrequent items were pruned
    res9 = await cache.get("Query number 9", user_id)
    if not res9:
        log_success("Infrequent item was correctly pruned.")
    else:
        log_info("Item 9 survived (might be due to 80% keep ratio).")

if __name__ == "__main__":
    asyncio.run(test_adaptive_cache())
