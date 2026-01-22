import sys
import os
import asyncio
import time
import shutil

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG
from Kaiacord import start_watcher
from utils.kaia_logger import log_success, log_info, log_error

async def test_watchdog():
    log_info("Starting Watchdog Test...")
    
    # Create a temporary knowledge base directory
    tmp_kb = "/tmp/kaia_test_kb"
    if os.path.exists(tmp_kb):
        shutil.rmtree(tmp_kb)
    os.makedirs(tmp_kb)
    
    rag = KaiaRAG()
    rag.knowledge_base_dir = tmp_kb
    
    loop = asyncio.get_running_loop()
    
    # Start watcher
    observer = start_watcher(rag, loop)
    
    try:
        # Create a new file in knowledge base
        test_file = os.path.join(tmp_kb, "watchdog_test.txt")
        log_info(f"Creating test file: {test_file}")
        with open(test_file, "w") as f:
            f.write("This is a test file for the watchdog.")
            
        log_info("Waiting for watchdog to trigger refresh (should take ~2-5 seconds)...")
        # Watchdog has a 2s debounce
        await asyncio.sleep(5)
        
        # Check if file is indexed
        norm_path = os.path.abspath(test_file)
        if norm_path in rag.indexed_files:
            log_success("Watchdog correctly triggered RAG refresh and indexed the new file!")
        else:
            log_error(f"Watchdog failed to index the new file. Indexed files: {list(rag.indexed_files.keys())}")
            
        # Modify the file
        log_info(f"Modifying test file: {test_file}")
        with open(test_file, "a") as f:
            f.write("\nUpdated content.")
            
        log_info("Waiting for watchdog to trigger refresh again...")
        await asyncio.sleep(5)
        
        # Clean up
        shutil.rmtree(tmp_kb)
        log_info("Temporary knowledge base removed.")
        
    finally:
        observer.stop()
        observer.join()
        log_info("Watchdog stopped.")

if __name__ == "__main__":
    asyncio.run(test_watchdog())
