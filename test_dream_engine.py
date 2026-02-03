import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_dream import DreamEngine
# Mock config class
class MockConfig:
    def __init__(self):
        self.paths = {
            'knowledge_base': './knowledge_base',
            'dream_cache': './memory/dream_cache.json'
        }
        self.models = {'chat': 'gemma3:12b'}
        self.dream_mode = {
            'max_dreams_cached': 50,
            'dreams_per_scan': 2,
            'dream_age_min_days': 2
        }
    def get(self, key, default=None):
        parts = key.split('.')
        current = self
        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

async def test_dream_generation():
    print("--- Starting Dream Engine Test ---")
    
    # Mock config
    mock_config = MockConfig()
    
    # Initialize engine with mock config
    engine = DreamEngine(mock_config)
    
    # Mock persona
    persona = "You are Kaia, a blunt, observant AI. You prefer physical books over digital fluff."
    
    print(f"Knowledge Base: {engine.kb_dir}")
    print(f"Dream Cache: {engine.cache_path}")
    
    # Run a manual scan and generation
    # We'll limit it to 2 dreams for testing speed
    mock_config.dream_mode['dreams_per_scan'] = 2
    
    print("Running nightly_dream_processing task...")
    await engine.nightly_dream_processing(persona)
    
    # Check cache
    dreams = engine.load_cache()
    print(f"\nTotal dreams in cache: {len(dreams)}")
    
    # Check KB directory
    print(f"\nChecking KB directory: {engine.dreams_kb_dir}")
    if engine.dreams_kb_dir.exists():
        dream_files = list(engine.dreams_kb_dir.glob("*.md"))
        print(f"Total dream files in KB: {len(dream_files)}")
        for i, df in enumerate(dream_files[:2]):
            print(f"\n--- Dream File {i+1}: {df.name} ---")
            content = df.read_text()
            print(content[:500] + "...")
    else:
        print("ERROR: Dreams KB directory does not exist!")

if __name__ == "__main__":
    asyncio.run(test_dream_generation())
