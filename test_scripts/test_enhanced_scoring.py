import sys
import os
import asyncio
import time
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG
from utils.kaia_logger import log_success, log_info, log_error

async def test_enhanced_scoring():
    log_info("Starting Enhanced Scoring Test...")
    rag = KaiaRAG()
    
    # Create some test documents with different metadata
    from llama_index.core import Document
    
    # 1. Recent user profile
    doc1 = Document(
        text="Ekco likes coffee and coding.",
        metadata={
            'source': 'user_profile',
            'user_id': '123',
            'user_name': 'Ekco',
            'timestamp': datetime.now().isoformat(),
            'file_path': 'knowledge_base/user_logs/Ekco_123/user_profile.md'
        }
    )
    
    # 2. Old user profile
    doc2 = Document(
        text="Ekco used to like tea.",
        metadata={
            'source': 'user_profile',
            'user_id': '123',
            'user_name': 'Ekco',
            'timestamp': (datetime(2020, 1, 1)).isoformat(),
            'file_path': 'knowledge_base/user_logs/Ekco_123/user_profile_old.md'
        }
    )
    
    # 3. Different user profile
    doc3 = Document(
        text="Starkond likes gaming.",
        metadata={
            'source': 'user_profile',
            'user_id': '456',
            'user_name': 'Starkond',
            'timestamp': datetime.now().isoformat(),
            'file_path': 'knowledge_base/user_logs/Starkond_456/user_profile.md'
        }
    )
    
    # Insert into a temporary index for testing
    # We'll use the user_profiles index
    log_info("Inserting test nodes...")
    rag.indices['user_profiles'].insert(doc1)
    rag.indices['user_profiles'].insert(doc2)
    rag.indices['user_profiles'].insert(doc3)
    
    # Test retrieval for Ekco (user_id 123)
    log_info("Retrieving for Ekco (user_id 123)...")
    results = await asyncio.to_thread(rag.retrieve, "Who am I?", user_id=123, user_name="Ekco")
    
    log_info("Top results:")
    for i, res in enumerate(results):
        log_info(f"{i+1}: {res[:100]}...")
        
    # Verify that doc1 (recent, same user) is first
    if "likes coffee" in results[0]:
        log_success("Correctly prioritized recent profile for the same user!")
    else:
        log_error("Failed to prioritize recent profile for the same user.")

if __name__ == "__main__":
    asyncio.run(test_enhanced_scoring())
