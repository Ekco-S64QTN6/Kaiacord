import sys
import os
import asyncio

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kaia_rag import KaiaRAG
from utils.kaia_logger import log_success, log_info, log_error

async def trigger_reindex():
    log_info("Triggering RAG re-indexing...")
    rag = KaiaRAG()
    
    # This will scan knowledge_base and index new/modified files
    # The new pre-chunking logic will prevent 400 errors for large files
    rag.refresh_knowledge_base()
    
    # Persist the changes
    rag.persist()
    log_success("Re-indexing complete.")

if __name__ == "__main__":
    asyncio.run(trigger_reindex())
