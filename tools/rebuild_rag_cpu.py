import os
import shutil
import sys
import argparse
import time
import traceback
import asyncio

# Add parent directory to path to allow importing from utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action, log_warning
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.system.yaml_config import config

async def rebuild_rag(clear_storage=False):
    """
    Rebuild the RAG index standalone.
    """
    persist_dir = "./memory/rag_storage"
    
    if clear_storage:
        log_warning(f"CLEARING storage directory: {persist_dir}")
        if os.path.exists(persist_dir):
            # Keep .gitkeep if it exists
            gitkeep_path = os.path.join(persist_dir, ".gitkeep")
            has_gitkeep = os.path.exists(gitkeep_path)
            
            shutil.rmtree(persist_dir)
            os.makedirs(persist_dir)
            
            if has_gitkeep:
                with open(gitkeep_path, 'w') as f:
                    pass
            log_success("Storage directory cleared.")
    
    log_info("Initializing KaiaRAG...")
    try:
        rag = KaiaRAG()
        # Initialize manifest/indices in thread to match production Phase 3
        await asyncio.to_thread(rag._load_indexed_files)
        await asyncio.to_thread(rag._initialize_indices)
        
        log_action("Starting full knowledge base refresh...")
        start_time = time.time()
        
        # Correctly await the async refresh
        await rag.refresh_knowledge_base()
        
        duration = time.time() - start_time
        log_success(f"RAG rebuild complete in {duration:.2f} seconds.")
        
    except Exception as e:
        log_error(f"FATAL: RAG rebuild failed: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone RAG Rebuild Tool")
    parser.add_argument("--clear", action="store_true", help="Clear the storage directory before rebuilding")
    args = parser.parse_args()
    
    # Check if Ollama is running (embedding model depends on it)
    log_info("Checking Ollama status...")
    import requests
    try:
        requests.get("http://localhost:11434/api/tags", timeout=5)
        log_success("Ollama is online.")
    except Exception:
        log_error("Ollama is offline or unreachable at localhost:11434. Please start Ollama first.")
        sys.exit(1)
        
    asyncio.run(rebuild_rag(clear_storage=args.clear))
