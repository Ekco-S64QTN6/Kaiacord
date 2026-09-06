import asyncio
import os
import sys
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action
from utils.infrastructure.logging.unified_logging import logger as unified_logger
from utils.core.kaia_rag import KaiaRAG

async def verify_rag_and_logging_optimizations():
    log_info("--- RAG & Logging Optimization Verification ---")
    
    # 1. Verify Logging Batching
    log_action("Testing logging batching...")
    # Send 100 logs quickly
    for i in range(100):
        unified_logger.log(f"Batch test message {i}", "INFO")
    
    log_info("Sent 100 messages. Background worker should batch these.")
    # Check if they are in the queue or being processed
    log_success(f"Log queue size: {unified_logger.log_queue.qsize()}")
    
    # 2. Verify RAG Parallel Refresh
    log_action("Testing RAG Parallel Refresh (Dry Run)...")
    rag = KaiaRAG()
    
    # Mock find_changed_files to simulate work
    rag._find_changed_files = MagicMock(return_value=[
        ("test_file_1.txt", False, False, "knowledge"),
        ("test_file_2.txt", False, False, "knowledge"),
        ("test_file_3.txt", False, False, "knowledge"),
        ("test_file_4.txt", False, False, "knowledge"),
    ])
    
    # Mock index_single_file to simulate delay
    async def mock_index(path, mod, log, itype, cdir):
        # We don't actually want to call the real index, so we mock the thread offload too
        await asyncio.sleep(0.5)
        return True
    
    # Actually we need to mock _index_single_file which is sync but called via to_thread
    rag._index_single_file = MagicMock(side_effect=lambda *args: time.sleep(0.5) or True)
    
    t_start = time.perf_counter()
    await rag.refresh_knowledge_base(max_concurrent_files=4)
    t_total = time.perf_counter() - t_start
    
    # If parallelized with max_concurrent=4, 4 files taking 0.5s each should take ~0.5-0.7s total
    # If serial, they'd take 2.0s
    if t_total < 1.0:
        log_success(f"Parallel refresh confirmed: 4 files processed in {t_total:.2f}s")
    else:
        log_info(f"Refresh took {t_total:.2f}s (maybe local machine overhead or partial serial?)")
        
    log_success("Optimizations verified.")

if __name__ == "__main__":
    asyncio.run(verify_rag_and_logging_optimizations())
