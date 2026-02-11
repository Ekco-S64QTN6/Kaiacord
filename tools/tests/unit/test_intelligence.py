import sys
import os
import asyncio
import time
import shutil
import ollama

# Add parent directory to path
sys.path.append(os.getcwd())

from utils.core.performance_monitor import PerformanceMonitor
from utils.core.kaia_intelligence import (
    PersonalizationEngine, 
    PersistentStateManager, 
    ContextOptimizer,
    RelevanceFeedback,
    IntentParser,
    Intent
)
from utils.infrastructure.logging.kaia_logger import log_success, log_info, log_error

async def test_state_persistence():
    log_info("\n--- Testing State Persistence ---")
    personalization = PersonalizationEngine()
    monitor = PerformanceMonitor()
    state_manager = PersistentStateManager(state_dir="./test_storage/state")
    
    # Set some state
    personalization.user_profiles["123"] = {
        'conciseness': 0.8,
        'technicality': 0.2,
        'formality': 0.5,
        'humor': 0.5
    }
    monitor.metrics['cache_hits'] = 10
    
    # Save (relevance_feedback and cache removed from state manager signature)
    state_manager.save_state(personalization, monitor)
    
    # New instances
    personalization2 = PersonalizationEngine()
    monitor2 = PerformanceMonitor()
    
    # Load
    success = state_manager.load_state(personalization2, monitor2)
    
    if success and personalization2.user_profiles.get("123", {}).get('conciseness') == 0.8:
        log_success("State persistence verified.")
    else:
        log_error(f"State persistence failed. Profiles: {personalization2.user_profiles}")

async def test_token_allocation():
    log_info("\n--- Testing Token Allocation Guarantees ---")
    optimizer = ContextOptimizer(max_tokens=2000) # Small budget to force rebalancing
    
    # Simulate large inputs
    persona = "persona " * 2000
    rag_nodes = [{"content": "rag " * 2000, "metadata": {"source_type": "docs"}}]
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

async def test_intent_parsing():
    log_info("\n--- Testing Intent Parsing ---")
    client = ollama.AsyncClient()
    parser = IntentParser(client)
    
    # Test fast-path
    log_info("Testing fast-path (Greeting)")
    intent = parser.fast_parse("hi kaia")
    if intent and intent.suggested_strategy == "SOCIAL_GREETING":
        log_success("Fast-path greeting verified.")
    else:
        log_error(f"Fast-path greeting failed: {intent}")

    # Test complex intent (will use LLM if it doesn't match fast-path)
    log_info("Testing full parse (Technical query)")
    intent = await parser.parse_intent("how do I fix a CUDA error in pytorch?")
    log_info(f"Detected strategy: {intent.suggested_strategy}")
    if intent.suggested_strategy in ["DIAGNOSTIC_DEEP_DIVE", "EXPLORATORY_DIALOGUE"]:
        log_success("Intent parsing verified.")
    else:
        log_error(f"Intent parsing unexpected strategy: {intent.suggested_strategy}")

async def main():
    print("=== Running Intelligence Layer Tests ===")
    
    await test_state_persistence()
    await test_token_allocation()
    await test_intent_parsing()
    
    # Cleanup
    if os.path.exists("./test_storage"):
        shutil.rmtree("./test_storage")
        
    print("\n=== All Intelligence Tests Completed ===")

if __name__ == "__main__":
    asyncio.run(main())
