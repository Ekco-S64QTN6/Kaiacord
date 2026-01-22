import sys
import os
import asyncio
import time
import shutil

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG
from utils.kaia_logger import log_success, log_info, log_error

async def test_hybrid_search():
    log_info("Starting Hybrid Search Test...")
    
    # Setup clean environment
    if os.path.exists("./test_knowledge"):
        shutil.rmtree("./test_knowledge")
    os.makedirs("./test_knowledge")
    
    with open("./test_knowledge/test.txt", "w") as f:
        f.write("The secret password is 'antigravity'. This is a very specific keyword for BM25.")
        
    rag = KaiaRAG()
    rag.knowledge_base_dir = "./test_knowledge"
    rag.persist_dir = "./test_storage_rag"
    
    # 1. Index the file
    log_info("Indexing test file...")
    rag.refresh_knowledge_base()
    
    # 2. Test Vector Retrieval (should work)
    log_info("Testing retrieval with specific keyword...")
    query = "what is the secret password?"
    results = rag.retrieve(query)
    
    found = any("antigravity" in r.lower() for r in results)
    if found:
        log_success("Hybrid search found the specific keyword!")
    else:
        log_error("Hybrid search failed to find the keyword.")
        log_info(f"Results: {results}")

    # 3. Verify BM25 cache
    if 'knowledge' in rag.bm25_cache and rag.bm25_cache['knowledge'] is not None:
        log_success("BM25 cache correctly populated.")
    else:
        log_error("BM25 cache missing.")

    # Cleanup
    if os.path.exists("./test_knowledge"):
        shutil.rmtree("./test_knowledge")
    if os.path.exists("./test_storage_rag"):
        shutil.rmtree("./test_storage_rag")

if __name__ == "__main__":
    asyncio.run(test_hybrid_search())
