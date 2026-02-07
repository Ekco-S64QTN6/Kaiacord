
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from utils.core.kaia_dream import DreamEngine

class MockConfig:
    def __init__(self):
        self.paths = {'knowledge_base': './knowledge_base'}
        self.models = {'chat': 'mock_model'}
        self.dream_mode = {'dream_age_min_days': 0, 'dreams_per_scan': 100} # Scan many to be sure

async def verify_no_injections():
    print("Initializing DreamEngine...")
    engine = DreamEngine(MockConfig())
    
    print("Scanning Knowledge Base...")
    categorized_files = engine.scan_knowledge_base(min_days=0)
    
    injected_count = 0
    total_files = 0
    
    for cat, files in categorized_files.items():
        for f in files:
            total_files += 1
            if "injected" in f.name.lower():
                print(f"FAIL: Found injected file: {f}")
                injected_count += 1
    
    print(f"\nTotal Files Scanned: {total_files}")
    print(f"Injected Files Found: {injected_count}")
    
    if injected_count == 0:
        print("SUCCESS: No injected files found in scan.")
    else:
        print("FAILURE: Injected files are still present.")

if __name__ == "__main__":
    asyncio.run(verify_no_injections())
