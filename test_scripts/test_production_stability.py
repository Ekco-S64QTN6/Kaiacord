import sys
import os
import asyncio
import time
import shutil

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import (
    SemanticCache, 
    PersonalizationEngine, 
    PerformanceMonitor, 
    PersistentStateManager, 
    ContextOptimizer,
    IntelligentCacheInvalidator
)
from utils.kaia_logger import log_success, log_info, log_error

async def test_production_stability():
    log_info("Starting Production Stability Test...")
    
    # 1. Test State Persistence
    log_info("\n--- Testing State Persistence ---")
    cache = SemanticCache()
    personalization = PersonalizationEngine()
    monitor = PerformanceMonitor()
    state_manager = PersistentStateManager(state_dir="./test_storage/state")
    
    # Set some state
    await cache.set("test query", "test response", user_id=123)
    personalization.user_profiles["123"] = {'conciseness': 0.8, 'technicality': 0.2}
    monitor.record_hit(exact=True)
    
    # Save
    state_manager.save_state(cache, personalization, monitor)
    
    # New instances
    cache2 = SemanticCache()
    personalization2 = PersonalizationEngine()
    monitor2 = PerformanceMonitor()
    
    # Load
    success = state_manager.load_state(cache2, personalization2, monitor2)
    
    if success and "123:test query" in cache2.exact_cache and personalization2.user_profiles["123"]['conciseness'] == 0.8:
        log_success("State persistence verified.")
    else:
        log_error("State persistence failed.")

    # 2. Test Token Allocation Guarantees
    log_info("\n--- Testing Token Allocation Guarantees ---")
    optimizer = ContextOptimizer(max_tokens=2000) # Small budget to force rebalancing
    
    # Simulate large inputs
    persona = "persona " * 2000
    rag_nodes = ["rag " * 2000]
    history = ["history " * 2000]
    
    optimized = optimizer.optimize_context("knowledge", persona, rag_nodes, history)
    
    # Check if guarantees are met (min_rag=1024, min_history=512)
    rag_len = len(optimized['rag'].split()) * 1.3
    hist_len = len(optimized['history'].split()) * 1.3
    
    log_info(f"Optimized RAG tokens: {rag_len:.0f} (min 1024)")
    log_info(f"Optimized History tokens: {hist_len:.0f} (min 512)")
    
    if rag_len >= 1000 and hist_len >= 500: # Allow some margin for word/token conversion
        log_success("Token allocation guarantees verified.")
    else:
        log_error("Token allocation guarantees failed.")

    # 3. Test Cache Invalidation
    log_info("\n--- Testing Cache Invalidation ---")
    invalidator = IntelligentCacheInvalidator(cache)
    
    class MockNode:
        def __init__(self, file_path):
            self.metadata = {'file_path': file_path}
            
    nodes = [MockNode("knowledge_base/test.txt")]
    query = "what is in test.txt?"
    
    # Track
    invalidator.track(query, nodes)
    await cache.set(query, "it contains data", user_id=123)
    
    # Verify it's in cache
    if await cache.get(query, user_id=123):
        log_info("Query is in cache.")
    
    # Invalidate
    invalidator.invalidate_for_file("knowledge_base/test.txt")
    
    # Verify it's gone
    if not await cache.get(query, user_id=123):
        log_success("Cache invalidation verified.")
    else:
        log_error("Cache invalidation failed.")

    # Cleanup
    if os.path.exists("./test_storage"):
        shutil.rmtree("./test_storage")

if __name__ == "__main__":
    asyncio.run(test_production_stability())
