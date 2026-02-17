import sys
import os
from pathlib import Path
import asyncio

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.knowledge_boundary import KnowledgeBoundary
from utils.core.kaia_intelligence import ContextOptimizer
from utils.infrastructure.system.yaml_config import config

async def test_refinements():
    kb_path = config.knowledge_base_dir
    boundary = KnowledgeBoundary(kb_path)
    
    print("--- 1. Testing KnowledgeBoundary Entity Extraction ---")
    boundary.load_known_entities()
    print(f"Known entities: {list(boundary.known_entities)[:10]}...")
    
    # Test unknown entity
    check = boundary.check_known_entities("Tell me about Zorgon the Destroyer", "")
    print(f"Unknown entities in query: {check['unknown_in_context']}")
    assert "Zorgon" in check['unknown_in_context']
    
    print("\nVerification Passed!")

if __name__ == "__main__":
    asyncio.run(test_refinements())
