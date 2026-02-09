import sys
import os
import asyncio
import logging

# Setup paths
sys.path.append(os.getcwd())

# Mock config and logging if needed, or rely on imports
from utils.infrastructure.system.yaml_config import config
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import Intent

# Configure logging to stdout
logging.basicConfig(level=logging.INFO)

async def test_retrieval():
    print("Initializing KaiaRAG...")
    rag = KaiaRAG()
    
    query = "Three Buddy Problem Episode 84"
    print(f"\nTesting retrieval for query: '{query}'")
    
    # Simulate PRECISE_RECALL strategy
    intent = Intent(
        explicit_intent="Testing",
        implied_needs=[],
        emotional_context="neutral",
        temporal_focus="present",
        relational_context="none",
        suggested_strategy="PRECISE_RECALL",
        confidence=0.9
    )
    
    print("Strategy: PRECISE_RECALL (Identity)")
    
    results = rag.retrieve(
        query=query, 
        intent=intent, 
        category="identity", # PRECISE_RECALL often maps to identity
        top_k=5
    )
    
    if results:
        print(f"\n✅ Retrieved {len(results)} nodes:")
        for node in results:
            print(f"- [{node['score']:.4f}] {node['label']}: {node['content'][:100]}...")
    else:
        print("\n❌ No nodes retrieved (Filtered out?)")

    # Also test with "general" category/strategy to see if it makes a difference
    print(f"\nTesting retrieval for query (General): '{query}'")
    results_gen = rag.retrieve(
        query=query,
        category="general",
        top_k=5
    )
    
    if results_gen:
        print(f"\n✅ Retrieved {len(results_gen)} nodes:")
        for node in results_gen:
            print(f"- [{node['score']:.4f}] {node['label']}: {node['content'][:100]}...")
    else:
        print("\n❌ No nodes retrieved (General)")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
