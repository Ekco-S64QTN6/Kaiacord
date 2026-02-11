#!/usr/bin/env python3
"""
Test script for memory retrieval
"""
import sys
import pytest
import os

import asyncio
from unittest.mock import MagicMock

# Add parent directory to path
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from utils.core.kaia_rag import KaiaRAG, Document


@pytest.mark.asyncio
async def test_memory_retrieval():

    print("🧪 Testing Memory Retrieval...")
    
    rag = KaiaRAG()
    
    # Mock index for testing without full initialization
    # We'll just test the retrieve logic if possible, or integration test
    # Since RAG initialization is heavy, let's check if we can verify the code changes
    # by inspecting the class methods or running a small integration test.
    
    # Let's try to add a memory and retrieve it
    user_id = 123456789
    user_name = "TestUser"
    memory_text = "Worship means to place the highest value on the guidance of"
    
    print(f"📝 Adding memory for {user_name}: '{memory_text}'")
    success = rag.add_memory(user_id, user_name, memory_text)
    
    if success:
        print("✅ Memory added successfully")
    else:
        print("❌ Failed to add memory")
        return False
        
    # Now try to retrieve it
    print("🔍 Retrieving memory...")
    # We need to wait a bit for indexing? add_memory is synchronous in terms of inserting to index
    
    results = rag.retrieve("What is Worship?", user_id=user_id, user_name=user_name)
    
    found = False
    for res in results:
        if "Worship" in res:
            found = True
            print(f"✅ Found memory in results: {res[:100]}...")
            break
            
    if not found:
        print("❌ Memory not found in retrieval results")
        print("Results were:")
        for res in results:
            print(f"- {res[:100]}...")
            
    return found

if __name__ == "__main__":
    try:
        asyncio.run(test_memory_retrieval())
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
