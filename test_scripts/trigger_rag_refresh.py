import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error

async def trigger_refresh():
    try:
        log_info("Initializing KaiaRAG for refresh...")
        rag = KaiaRAG()
        
        # We need to wait for initialization
        log_info("Waiting for RAG to settle...")
        await asyncio.sleep(2)
        
        log_info("Triggering Knowledge Base refresh...")
        rag.refresh_knowledge_base()
        
        # Wait for the background refresh to complete or at least start
        # refresh_knowledge_base is synchronous in terms of starting the task
        # but the actual work is in a background thread or async task if configured.
        # However, looking at the code, it populates new_file_paths and then iterates.
        
        log_success("Refresh triggered. Monitoring logs for completion is advised.")
    except Exception as e:
        log_error(f"Failed to trigger refresh: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_refresh())
