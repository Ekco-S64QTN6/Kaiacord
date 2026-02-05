import os
import sys
import time
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info

async def benchmark_rag():
    rag = KaiaRAG()
    
    long_query = """
    A death's head hawk moth's favorite food is nectar, but her offspring emerge as voracious tomato plant killers. In just three weeks, these very hungry caterpillars grow 16 times bigger. Now finger-length and armed with scissor-like mandibles, one caterpillar can devour an entire plant. An army of them will decimate the whole crop.

    But tomato plants have an invisible defense. Injured leaves release an airborne distress call, volatile chemicals that warn neighboring plants to prepare for war. This call to arms rallies nearby leaves to produce powerful toxins, rendering them inedible. And because these caterpillars only feed on plants in the tomato family, they begin to starve.

    A recent discovery reveals this tale has a sinister twist. With nothing left to eat, they eat each other. Cannibal caterpillars. The gruesome method of pest control when the killer tomatoes strike back.
    """
    
    print("\n--- Starting RAG Benchmark ---")
    
    # 1. Warm up
    print("Warming up...")
    await asyncio.to_thread(rag.retrieve, "test query")
    
    # 2. Benchmark current retrieval
    print(f"Running retrieval for long query ({len(long_query)} chars)...")
    start = time.time()
    results = await asyncio.to_thread(rag.retrieve, long_query)
    end = time.time()
    
    print(f"Retrieved {len(results)} results in {end - start:.2f}s")
    
    # 3. Test individual embedding speed
    print("\nMeasuring single embedding speed...")
    start_embed = time.time()
    # Access private embed model for measurement
    embedding = await rag.embed_model.aget_query_embedding(long_query)
    end_embed = time.time()
    print(f"Single embedding took {end_embed - start_embed:.2f}s")
    print(f"Theoretically, 3 re-embeddings would take ~{ (end_embed - start_embed) * 3 }s")

if __name__ == "__main__":
    asyncio.run(benchmark_rag())
