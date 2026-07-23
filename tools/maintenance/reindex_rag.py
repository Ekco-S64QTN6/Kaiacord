"""
Standalone RAG Rebuild & Reindex Tool
=======================================

Rebuilds BM25 and vector RAG indices standalone or signals the live bot to perform an incremental refresh.
"""

import os
import sys
import shutil
import time
import argparse
import asyncio
import traceback
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action, log_warning
from utils.core.kaia_rag import KaiaRAG


async def rebuild_rag(clear_storage: bool = False, file_path: str = None):
    """Rebuild or refresh the RAG index."""
    persist_dir = os.path.join(PROJECT_ROOT, "memory", "rag_storage")
    
    if clear_storage:
        log_warning(f"CLEARING RAG storage directory: {persist_dir}")
        if os.path.exists(persist_dir):
            gitkeep_path = os.path.join(persist_dir, ".gitkeep")
            has_gitkeep = os.path.exists(gitkeep_path)
            
            shutil.rmtree(persist_dir)
            os.makedirs(persist_dir, exist_ok=True)
            
            if has_gitkeep:
                with open(gitkeep_path, 'w') as f:
                    pass
            log_success("Storage directory cleared.")
    
    log_info("Initializing KaiaRAG engine...")
    try:
        rag = KaiaRAG()
        await asyncio.to_thread(rag._load_indexed_files)
        await asyncio.to_thread(rag._initialize_indices)
        
        if file_path:
            log_action(f"Re-indexing single target file: {file_path}")
            abs_file = os.path.abspath(file_path)
            if abs_file in rag.indexed_files:
                del rag.indexed_files[abs_file]
                rag.persist_needed = True
            await rag.refresh_knowledge_base()
            log_success(f"Target file re-indexed: {file_path}")
        else:
            log_action("Starting full knowledge base refresh...")
            start_time = time.time()
            await rag.refresh_knowledge_base()
            duration = time.time() - start_time
            log_success(f"RAG rebuild complete in {duration:.2f} seconds.")
            
    except Exception as e:
        log_error(f"FATAL: RAG rebuild failed: {e}")
        traceback.print_exc()
        sys.exit(1)


def trigger_bot_reindex():
    """Touch trigger file to signal running bot to perform incremental reindex."""
    trigger_file = os.path.join(PROJECT_ROOT, "knowledge_base", ".trigger_reindex")
    Path(trigger_file).touch()
    log_success("Created .trigger_reindex file. Live bot will pick up changes on next loop.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone RAG Rebuild & Reindex Tool")
    parser.add_argument("--clear", action="store_true", help="Clear storage directory before rebuilding")
    parser.add_argument("--trigger", action="store_true", help="Signal running bot to reindex via trigger file")
    parser.add_argument("file", nargs="?", default=None, help="Optional single file path to re-index")
    args = parser.parse_args()

    if args.trigger:
        trigger_bot_reindex()
    else:
        asyncio.run(rebuild_rag(clear_storage=args.clear, file_path=args.file))
