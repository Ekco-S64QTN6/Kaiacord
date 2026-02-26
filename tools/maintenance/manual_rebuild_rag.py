import os
import asyncio
import traceback
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action

async def rebuild_rag():
    log_action("Starting Manual RAG Rebuild...")
    
    try:
        # 1. Initialize RAG
        # This will set up the embedding model (forced to CPU) 
        # and the LLM (chat model).
        rag = KaiaRAG()
        
        # 2. Async initialization
        # This loads the manifest and initializes the storage context/indices.
        await rag.initialize_async()
        
        # 3. Trigger full refresh
        # This scans the knowledge base and indexes all files.
        # We increase max_concurrent_files slightly since this is a dedicated task.
        log_info("Scanning and indexing knowledge base...")
        await rag.refresh_knowledge_base(max_concurrent_files=4)
        
        log_success("Manual RAG Rebuild complete.")
        
    except Exception as e:
        log_error(f"RAG Rebuild failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Ensure current directory is the project root
    if not os.path.exists("knowledge_base"):
        print("Error: Script must be run from the project root (Kaiacord/).")
    else:
        asyncio.run(rebuild_rag())
