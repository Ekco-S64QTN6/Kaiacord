#!/usr/bin/env python3
"""
GPU-Accelerated RAG Rebuild
============================

Use this ONLY when the bot is NOT running.
When the bot is off, the GPU is free — this script uses it for ~5-10x faster embedding.

Usage:
    python tools/rebuild_rag_gpu.py --clear     # Wipe + full rebuild on GPU
    python tools/rebuild_rag_gpu.py             # Incremental rebuild on GPU
"""

import os
import shutil
import sys
import argparse
import time
import traceback
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_action, log_warning, log_debug
from utils.infrastructure.logging.unified_logging import logger as global_logger
from utils.infrastructure.system.yaml_config import config


async def rebuild_rag_gpu(clear_storage=False, concurrency=4):
    """
    Rebuild RAG using GPU-accelerated embeddings.
    Monkey-patches KaiaRAG's embed_model to use num_gpu=99 instead of 0.
    """
    persist_dir = "./memory/rag_storage"

    if clear_storage:
        log_warning(f"CLEARING storage directory: {persist_dir}")
        if os.path.exists(persist_dir):
            gitkeep_path = os.path.join(persist_dir, ".gitkeep")
            has_gitkeep = os.path.exists(gitkeep_path)
            shutil.rmtree(persist_dir)
            os.makedirs(persist_dir)
            if has_gitkeep:
                open(gitkeep_path, 'w').close()
            log_success("Storage directory cleared.")

    log_info("Initializing KaiaRAG...")
    try:
        from utils.core.kaia_rag import KaiaRAG
        rag = KaiaRAG()

        # ── GPU Override ────────────────────────────────────────────
        # KaiaRAG.__init__ sets num_gpu=0 (CPU-only) to save VRAM
        # while the bot's chat model is loaded. Since the bot is OFF,
        # we patch the embed model to use the GPU for faster embedding.
        log_action("Overriding embedding model to use GPU (num_gpu=99)...")
        from llama_index.embeddings.ollama import OllamaEmbedding
        rag.embed_model = OllamaEmbedding(
            model_name=config.embedding_model,
            base_url="http://localhost:11434",
            query_instruction=config.rag_query_instruction,
            text_instruction=config.rag_text_instruction,
            ollama_additional_kwargs={
                "num_gpu": 99,       # Full GPU offload
                "num_thread": 4,
                "num_ctx": config.embedding_context_tokens
            },
            client_kwargs={"timeout": config.embedding_request_seconds}
        )

        # Also update the global Settings so any LlamaIndex internals use GPU
        from llama_index.core import Settings
        Settings.embed_model = rag.embed_model
        log_success(f"Embedding model: {config.embedding_model} (GPU-accelerated)")

        # ── Bump concurrency ────────────────────────────────────────
        # The default refresh uses max=2 concurrent workers. With GPU,
        # we can safely do more since Ollama batches GPU embeddings.
        if hasattr(rag, '_max_concurrent_embeds'):
            rag._max_concurrent_embeds = concurrency
        log_info(f"Concurrency: {concurrency} parallel workers")

        # ── Initialize and rebuild ──────────────────────────────────
        await asyncio.to_thread(rag._load_indexed_files)
        await asyncio.to_thread(rag._initialize_indices)

        log_action("Starting full knowledge base refresh (GPU)...")
        start_time = time.time()
        await rag.refresh_knowledge_base()
        duration = time.time() - start_time

        log_success(f"GPU RAG rebuild complete in {duration:.1f}s "
                    f"({len(rag.indexed_files)} files indexed)")

    except Exception as e:
        log_error(f"FATAL: GPU RAG rebuild failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU-Accelerated RAG Rebuild (offline use only)")
    parser.add_argument("--clear", action="store_true",
                        help="Clear storage before rebuilding")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Parallel embedding workers (default: 4)")
    args = parser.parse_args()

    import subprocess
    try:
        # 1. Robust process detection:
        # Search for 'python' or 'python3' processes and check their arguments for 'Kaiacord.py'.
        # This avoids matching terminal window titles or shell command strings.
        running_pids = []
        my_pid = os.getpid()
        
        # Get all python processes with their full command line
        ps_cmd = ["ps", "-C", "python,python3", "-o", "pid,args", "--no-headers"]
        result = subprocess.run(ps_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.strip().split(None, 1)
                if len(parts) < 2:
                    continue
                pid_str, args_str = parts
                pid = int(pid_str)
                
                # Check if it's the bot script and not ourselves
                if pid != my_pid and "Kaiacord.py" in args_str:
                    # Double check that Kaiacord.py is a distinct argument, not part of a path
                    # (unless it's the script being run)
                    if any(arg.endswith("Kaiacord.py") or arg == "Kaiacord.py" for arg in args_str.split()):
                        running_pids.append(pid_str)

        if running_pids:
            log_warning(f"⚠️  Kaiacord.py appears to be running (PIDs: {', '.join(running_pids)})!")
            log_warning("   GPU rebuild will compete for VRAM and may cause the bot to crash.")
            log_warning("   Stop the bot first, or use the regular CPU rebuild: python tools/rebuild_rag.py --clear")
            
            # Flush loggers before interactive input to prevent terminal corruption
            sys.stdout.flush()
            sys.stderr.flush()

            try:
                print("\n" + "="*50)
                response = input("PROMPT: Continue anyway? [y/N]: ").strip().lower()
                print("="*50 + "\n")
                
                if not (response == 'y' or response == 'yes'):
                    log_info("Aborting at user request.")
                    global_logger.stop()
                    sys.exit(0)
            except EOFError:
                log_error("No interactive terminal detected. Aborting for safety.")
                global_logger.stop()
                sys.exit(1)
            except KeyboardInterrupt:
                print()
                log_info("Aborting.")
                global_logger.stop()
                sys.exit(0)
    except subprocess.TimeoutExpired:
        log_debug("pgrep check timed out, skipping safety check.")
    except Exception as e:
        log_debug(f"pgrep safety check skipped: {e}")

    # Check Ollama
    log_info("Checking Ollama status...")
    import requests
    try:
        requests.get("http://localhost:11434/api/tags", timeout=5)
        log_success("Ollama is online.")
    except Exception:
        log_error("Ollama is offline. Start it first: ollama serve")
        sys.exit(1)

    asyncio.run(rebuild_rag_gpu(clear_storage=args.clear, concurrency=args.concurrency))
