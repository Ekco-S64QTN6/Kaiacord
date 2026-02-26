import asyncio
import sys
import os
sys.path.append(os.getcwd())
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action

async def force_reindex():
    log_action("Initializing RAG for force reindex...")
    rag = KaiaRAG()
    await asyncio.to_thread(rag._load_indexed_files)
    await asyncio.to_thread(rag._initialize_indices)
    
    if len(sys.argv) > 1:
        # Specific file passed as argument — clear it from manifest
        target = os.path.abspath(sys.argv[1])
        if target in rag.indexed_files:
            del rag.indexed_files[target]
            log_info(f"Cleared {target} from manifest. Will re-index on refresh.")
        else:
            log_info(f"File not in manifest: {target}")
    else:
        # No argument — clear entire manifest to force full re-index
        count = len(rag.indexed_files)
        rag.indexed_files.clear()
        log_info(f"Cleared all {count} manifest entries. Full re-index will run.")
    
    log_action("Running knowledge base refresh...")
    await rag.refresh_knowledge_base()
    log_success("Force reindex complete.")

if __name__ == "__main__":
    asyncio.run(force_reindex())
