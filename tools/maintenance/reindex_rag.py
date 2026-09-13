"""
Standalone RAG Rebuild & Reindex Tool
=======================================

Rebuilds BM25 and vector RAG indices standalone or signals the live bot to perform an incremental refresh.
"""

import os
import sys
import shutil
import subprocess
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


def _bot_running() -> bool:
    """True if a Kaiacord process is holding the GPU."""
    try:
        out = subprocess.run(["pgrep", "-f", "Kaiacord.py"],
                             capture_output=True, text=True, timeout=5)
        return bool(out.stdout.strip())
    except Exception:
        return True          # unknown: assume it is, and leave VRAM alone


async def rebuild_rag(clear_storage: bool = False, file_path: str = None,
                      force_cpu_embed: bool = False, force: bool = False):
    """Rebuild or refresh the RAG index."""
    persist_dir = os.path.join(PROJECT_ROOT, "memory", "rag_storage")

    # The kaia-tools menu asks before wiping the index under a live bot
    # (confirm_offline_rebuild), but running this script directly bypassed that
    # entirely and went straight to shutil.rmtree on a directory the bot holds
    # open. Two processes writing one persist directory is not hypothetical:
    # a second KaiaRAG opened against it during this session found no manifest,
    # repopulated from scratch and overwrote the running bot's file_manifest.json.
    # That one happened to produce an identical manifest. It did not have to.
    if _bot_running() and not force:
        if clear_storage:
            log_error("Kaia is running. Refusing to clear memory/rag_storage from "
                      "under her — stop the bot first, or pass --force if you are "
                      "certain this is what you want.")
            return False
        log_warning("Kaia is running. She owns memory/rag_storage, and writing it "
                    "from a second process can corrupt the manifest. Use the trigger "
                    "instead: tools/maintenance/reindex_rag.py --trigger")
    
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
    
    # Embeddings default to CPU so a running bot keeps the 12b chat model in
    # VRAM. Nothing is holding that VRAM during an offline rebuild, and the job
    # is tens of thousands of embeddings, so use the GPU when the bot is not
    # running. `--cpu-embed` forces the old behaviour.
    bot_up = _bot_running()
    if bot_up:
        log_info("Bot is running — embedding on CPU so the chat model keeps its VRAM.")
    elif force_cpu_embed:
        log_info("--cpu-embed given — embedding on CPU despite the bot being stopped.")
    else:
        os.environ["KAIA_EMBED_GPU"] = "1"
        log_info("No bot process detected — embedding on GPU for this rebuild.")

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
    parser.add_argument("--force", action="store_true",
                        help="Proceed even though the bot is running (can corrupt the index)")
    parser.add_argument("--cpu-embed", action="store_true",
                        help="Keep embeddings on CPU even with the bot stopped "
                             "(the default while it is running, to protect its VRAM)")
    args = parser.parse_args()

    if args.trigger:
        trigger_bot_reindex()
    else:
        asyncio.run(rebuild_rag(clear_storage=args.clear, file_path=args.file,
                                force_cpu_embed=args.cpu_embed, force=args.force))
