#!/usr/bin/env python3
"""
scratch/test_tech_news_retrieval.py
Verifies that the new tech digests and historical backfilled reference profiles
are successfully indexed and retrieved by the KaiaRAG engine.
"""
import os
import sys
import asyncio
from pathlib import Path

# Ensure project root is in sys.path
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error

async def verify_retrieval():
    log_info("Initializing KaiaRAG...")
    rag = KaiaRAG()
    await rag.initialize_async()
    
    # Test queries
    queries = [
        "Google Antigravity",
        "DeepSeek-R1 reinforcement learning",
        "Gemini 3.5 Flash default model",
        "tech digest news updates"
    ]
    
    for q in queries:
        log_info(f"\n🔍 Querying: '{q}'")
        # Run standard retrieve (include_news=False, strict_identity=False)
        nodes = await rag.retrieve(q, include_news=False, strict_identity=False)
        
        if not nodes:
            log_error("  ❌ No nodes retrieved.")
            continue
            
        log_success(f"  ✅ Retrieved {len(nodes)} nodes:")
        for idx, node in enumerate(nodes, 1):
            metadata = node.get("metadata", {})
            path = metadata.get("file_path", "unknown")
            rel_path = os.path.relpath(path) if os.path.isabs(path) else path
            score = node.get("score", 0.0)
            text_snippet = node.get("content", "")[:120].replace('\n', ' ')
            print(f"    [{idx}] Score: {score:.4f} | Path: {rel_path}")
            print(f"        Snippet: {text_snippet}...")

if __name__ == "__main__":
    if not os.path.exists("knowledge_base"):
        print("Error: Run from project root.")
        sys.exit(1)
        
    asyncio.run(verify_retrieval())
