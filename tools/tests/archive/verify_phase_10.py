import asyncio
import os
import shutil
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from utils.core.kaia_intelligence import PersonalizationEngine, PersistentStateManager

async def verify_persistence():
    print("\n--- Persistence Verification ---")
    state_dir = "./test_memory_state"
    if os.path.exists(state_dir):
        shutil.rmtree(state_dir)
    
    personalization = PersonalizationEngine(max_profiles=5)
    manager = PersistentStateManager(state_dir=state_dir)
    
    # 1. Create some profiles
    # user_0 to user_9. With max_profiles=5 and 10% pruning (0.5 -> 0), 
    # it might just stay at 5 or drop 1.
    for i in range(10): 
        # Pruning logic: if len > max, delete 10%
        await personalization.learn_from_interaction(f"user_{i}", "hi", "hello")
    
    print(f"Profiles in memory after pruning: {len(personalization.user_profiles)}")
    
    # 2. Save
    class MockMonitor:
        def __init__(self): self.metrics = {}
    
    monitor = MockMonitor()
    manager.save_state(personalization, monitor)
    
    # 3. Verify files
    profiles_dir = os.path.join(state_dir, "profiles")
    if os.path.exists(profiles_dir):
        files = os.listdir(profiles_dir)
        print(f"Files in {profiles_dir}: {len(files)}")
        for f in sorted(files):
            print(f" - {f}")
    else:
        print("ERROR: Profiles directory not created!")

    # 4. Load back
    new_personalization = PersonalizationEngine()
    manager.load_state(new_personalization, monitor)
    print(f"Profiles loaded back: {len(new_personalization.user_profiles)}")
    
    # Cleanup
    if os.path.exists(state_dir):
        shutil.rmtree(state_dir)

if __name__ == "__main__":
    asyncio.run(verify_persistence())
