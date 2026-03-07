import asyncio
import sys
import os
sys.path.append(os.getcwd())
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action

async def force_reindex():
    log_action("Initializing RAG for force reindex...")
    rag = KaiaRAG()
    await rag.initialize_async()  # ← loads indices AND manifest
    
    if len(sys.argv) > 1:
        # Specific file passed as argument — clear it from manifest
        target = os.path.abspath(sys.argv[1])
        if target in rag.indexed_files:
            del rag.indexed_files[target]
            log_info(f"Cleared {target} from manifest. Will re-index on refresh.")
        else:
            log_info(f"File not in manifest: {target}")
    # else: no args = true incremental, just scan for new/changed files
    # DO NOT clear manifest here — that's what option 3 is for
    
    log_action("Running incremental knowledge base refresh...")
    await rag.refresh_knowledge_base()
    log_success("Incremental refresh complete.")

if __name__ == "__main__":
    asyncio.run(force_reindex())
