#!/usr/bin/env python3
"""
Kaia Qwen 3.5 Pre-Migration Validation Tool
===========================================
Checks environment readiness for the Qwen 3.5 9B upgrade.
"""

import os
import sys
import json
import asyncio
import aiohttp
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error, log_action
from utils.infrastructure.system.yaml_config import config

async def check_ollama_version():
    log_action("Checking Ollama version...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags") as resp:
                if resp.status == 200:
                    # Note: Ollama doesn't always expose version in /api/tags
                    # But we can check if it responds at all
                    log_success("Ollama is running.")
                    return True
                else:
                    log_error(f"Ollama returned status {resp.status}")
                    return False
    except Exception as e:
        log_error(f"Could not connect to Ollama: {e}")
        return False

async def check_models():
    log_action("Checking required models...")
    required = [config.chat_model, config.embedding_model]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags") as resp:
                data = await resp.json()
                local_models = [m['name'] for m in data.get('models', [])]
                
                all_present = True
                for model in required:
                    if any(model in m for m in local_models):
                        log_success(f"Model present: {model}")
                    else:
                        log_warning(f"Model missing: {model}. Run 'ollama pull {model}'")
                        all_present = False
                return all_present
    except Exception as e:
        log_error(f"Failed to check models: {e}")
        return False

def check_config_consistency():
    log_action("Checking configuration consistency...")
    # Check if legacy config exists
    legacy_path = Path("utils/infrastructure/system/config_base.py")
    if legacy_path.exists():
        log_warning("Legacy config_base.py still exists. It should be removed.")
    else:
        log_success("Legacy config_base.py removed.")

    # Check embedding instructions
    if config.rag_query_instruction == "search_query: " and "qwen" in config.embedding_model.lower():
        log_warning("Using Nomic instructions with a Qwen embedding model. Update default_config.yaml.")
    
    log_info(f"Target Chat Model: {config.chat_model}")
    log_info(f"Target Embedding Model: {config.embedding_model}")
    log_info(f"Context Limit: {config.max_context_tokens} tokens")

    if config.max_context_tokens > 32768:
        log_warning(f"Context limit of {config.max_context_tokens} might be too high for 12GB VRAM. Consider 32k.")

async def main():
    print("\n--- KAIA QWEN 3.5 PRE-MIGRATION CHECK ---\n")
    
    ollama_ok = await check_ollama_version()
    models_ok = await check_models()
    check_config_consistency()
    
    # Check RAG storage size
    rag_dir = Path("memory/rag_storage")
    if rag_dir.exists():
        size = sum(f.stat().st_size for f in rag_dir.glob('**/*') if f.is_file()) / (1024 * 1024)
        log_info(f"Existing RAG Storage Size: {size:.2f} MB")
        if "qwen" in config.embedding_model.lower() and size > 0:
             log_warning("RAG storage contains data from a different model. Migration will require deletion.")

    print("\n------------------------------------------\n")
    if ollama_ok and models_ok:
        log_success("Environment is READY for Phase 1 (Chat Migration).")
    else:
        log_error("Environment is NOT fully ready. See warnings above.")

if __name__ == "__main__":
    asyncio.run(main())
