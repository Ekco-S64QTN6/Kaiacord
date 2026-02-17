
import asyncio
import logging
import sys
import os

# Add the current directory to sys.path
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success

async def smoke_test():
    logging.basicConfig(level=logging.INFO)
    log_info("Starting RAG smoke test...")
    
    try:
        # Initialize KaiaRAG
        # This should trigger _initialize_indices()
        rag = KaiaRAG()
        log_success("KaiaRAG initialized successfully.")
        
        # Try a simple retrieval to ensure embedding model and index are working
        # Note: Since it's rebuilding, this might take a moment if the KB is large,
        # but for a smoke test we just want to see it not crash.
        query = "test"
        log_info(f"Testing retrieval with query: {query}")
        results = await rag.retrieve(query)
        log_success(f"Retrieval successful. Found {len(results)} nodes.")
        
        return True
    except Exception as e:
        import traceback
        logging.error(f"Smoke test failed: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(smoke_test())
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
