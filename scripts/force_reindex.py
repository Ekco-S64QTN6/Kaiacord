import os
import asyncio
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success

async def force_reindex():
    rag = KaiaRAG()
    target_files = [
        os.path.abspath("knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260209.txt"),
        os.path.abspath("knowledge_base/user_logs/MetroGnowmOSexual_579396554536910859/interactions_20260209.txt")
    ]
    
    log_info("Forcing re-index of sanitized logs...")
    for tf in target_files:
        if tf in rag.indexed_files:
            del rag.indexed_files[tf]
            log_info(f"Removed {tf} from indexed_files cache.")
            
    # Trigger refresh
    rag.refresh_knowledge_base()
    log_success("Re-index triggered.")

if __name__ == "__main__":
    asyncio.run(force_reindex())
