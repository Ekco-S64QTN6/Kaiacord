
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
        self.dream_mode = {'dream_age_min_days': 0, 'dreams_per_scan': 20}

async def dry_run_dream_selection():
    print("Initializing DreamEngine with MockConfig...")
    engine = DreamEngine(MockConfig())
    
    print("\nScanning Knowledge Base...")
    # Mocking time.time to ensure we get files (setting min_days=0 in config helps, 
    # but we might need to ensure scan_knowledge_base picks them up)
    
    # Actually, let's just inspect what scan_knowledge_base returns
    categorized_files = engine.scan_knowledge_base(min_days=0)
    
    print(f"\nFound files by category:")
    for cat, files in categorized_files.items():
        print(f"  {cat}: {len(files)} files")
        
    # Now simulate the selection logic from nightly_dream_processing
    print("\nSimulating Selection Logic (20 slots):")
    
    import random
    from collections import defaultdict
    
    dreams_per_scan = 20
    sample_files = []
    
    # A. User Quota
    user_logs = categorized_files.get('user_logs', [])
    target_user_dreams = int(dreams_per_scan * 0.4)
    if target_user_dreams < 1: target_user_dreams = 1
    
    print(f"  Target User Dreams: {target_user_dreams}")
    
    if user_logs:
        user_map = defaultdict(list)
        for f in user_logs:
            user_map[f.parent.name].append(f)
        
        users = list(user_map.keys())
        print(f"  Unique Users Found: {len(users)} ({', '.join(users)})")
        
        for i in range(target_user_dreams):
            selected_user = random.choice(users)
            selected_file = random.choice(user_map[selected_user])
            sample_files.append(selected_file)
            print(f"    Slot {i+1}: Selected {selected_file.name} (User: {selected_user})")

    # B. General Content Quota
    other_files = []
    for cat in ['Books', 'news', 'documents']:
        other_files.extend(categorized_files.get(cat, []))
        
    remaining_slots = dreams_per_scan - len(sample_files)
    print(f"  Remaining Slots for General Content: {remaining_slots}")
    
    if remaining_slots > 0 and other_files:
        count = min(len(other_files), remaining_slots)
        selected_others = random.sample(other_files, count)
        sample_files.extend(selected_others)
        for f in selected_others:
            print(f"    General: {f.name} ({f.parent.name})")

    print(f"\nTotal Selected: {len(sample_files)}")
    
    # Check for Ekco
    ekco_selected = any("Ekco" in f.parent.name or "ekco" in f.parent.name for f in sample_files)
    print(f"\nWas Ekco selected? {'YES' if ekco_selected else 'NO'}")

if __name__ == "__main__":
    asyncio.run(dry_run_dream_selection())
