
import asyncio
import os
import sys

# Mock configuration for testing
os.environ['KAIA_DASHBOARD'] = 'none'
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config

async def test_retrieval():
    print("Initializing KaiaRAG...")
    rag = KaiaRAG()
    
    # Force load one index to be sure
    itype = 'knowledge'
    if itype not in rag.indices:
        print(f"Index {itype} not found. RAG might be empty or missing storage.")
        return

    print(f"Testing retrieval for itype: {itype}")
    try:
        # We need to simulate the environment enough for hybrid.retrieve to work
        # HybridRetriever is used inside perform_hybrid_retrieval in KaiaRAG.retrieve
        
        # Test a direct retrieval call
        print("Executing RAG retrieval (async)...")
        results = await rag.retrieve("What is artificial intelligence?", top_k=5)
        print(f"Success! Found {len(results)} nodes.")
        for i, res in enumerate(results):
            print(f" [{i}] Score: {res.score:.4f} Content: {res.node.get_content()[:50]}...")
            
    except Exception as e:
        print(f"RETRIEVAL FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_retrieval())
