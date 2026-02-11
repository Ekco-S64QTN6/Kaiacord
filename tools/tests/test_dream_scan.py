import asyncio
import os
import sys
from pathlib import Path
import time

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.core.kaia_dream import DreamEngine
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.logging.kaia_logger import log_info, log_success

async def test_dream_scan():
    log_info("Testing Dreaming Scan with Fallback...")
    
    # Initialize engine
    # We don't need a real RAG for scanning
    engine = DreamEngine(config)
    
    # 1. Test with a very high min_days to force fallback
    log_info("Scanning with min_days=9999 (should trigger fallback)...")
    results = engine.scan_knowledge_base(min_days=9999)
    
    total_files = sum(len(f) for f in results.values())
    log_info(f"Total files found: {total_files}")
    
    if total_files > 0:
        log_success("Fallback worked: Found files despite high age threshold.")
    else:
        log_error("Fallback failed: No files found.")

    # 2. Test with normal min_days
    log_info("Scanning with min_days=2...")
    results_normal = engine.scan_knowledge_base(min_days=2)
    total_normal = sum(len(f) for f in results_normal.values())
    log_info(f"Normal scan found: {total_normal} files.")
    
    log_success("Dream scan testing complete.")

if __name__ == "__main__":
    asyncio.run(test_dream_scan())
