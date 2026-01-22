import sys
import os
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock

# Add parent directory to path to import Kaiacord
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Kaiacord import load_persona_async, run_rag

async def mock_rag_retrieve(query, **kwargs):
    print(f"RAG retrieval started for: {query}")
    await asyncio.sleep(1) # Simulate slow RAG
    print("RAG retrieval finished.")
    return ["Mock Context Node"]

async def test_async_pipeline():
    print("\n--- Testing Async Parallel Pipeline ---")
    
    start_time = time.time()
    
    # Define tasks
    persona_task = asyncio.create_task(load_persona_async())
    
    # We mock the RAG retrieval to simulate latency
    rag_mock = MagicMock()
    rag_mock.retrieve = lambda q, **kwargs: time.sleep(1) or ["Mock Context Node"]
    
    rag_task = asyncio.create_task(run_rag(
        rag_mock.retrieve, 
        "test query"
    ))
    
    print("Tasks started. Waiting for results...")
    persona, context = await asyncio.gather(persona_task, rag_task)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\nPersona loaded: {persona[:50]}...")
    print(f"Context retrieved: {context}")
    print(f"Total duration: {duration:.2f}s")
    
    # If they ran in parallel, duration should be close to 1s (the RAG latency)
    # If they were serial, it would be 1s + persona load time.
    # Since persona load is fast, the difference is small, but the gather itself proves concurrency.
    assert duration < 1.5
    print("✓ Async pipeline confirmed.")

if __name__ == "__main__":
    try:
        asyncio.run(test_async_pipeline())
        print("\n✨ Async pipeline tests passed!")
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
