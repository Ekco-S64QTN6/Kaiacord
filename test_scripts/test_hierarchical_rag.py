import sys
import os
import asyncio
import time
from unittest.mock import MagicMock

# Add parent directory to path to import kaia_rag
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

async def test_hierarchical_rag():
    print("\n--- Testing Hierarchical RAG (Kaia 2.0) ---")
    
    # Use a temporary storage dir for testing
    test_storage = "./test_storage_hierarchical"
    if not os.path.exists(test_storage):
        os.makedirs(test_storage)
        
    rag = KaiaRAG(persist_dir=test_storage)
    
    # 1. Verify indices were initialized
    print("\n1. Verifying indices...")
    expected_indices = ['persona', 'user_profiles', 'conversations', 'knowledge', 'logs']
    for itype in expected_indices:
        assert itype in rag.indices
        print(f"✓ Index '{itype}' initialized.")
        
    # 2. Test Routing
    print("\n2. Testing Routing...")
    
    # Mock some content in persona index
    from llama_index.core import Document
    persona_doc = Document(text="Kaia is a blunt AI assistant.", metadata={"source": "persona", "user_id": "KAIA_SYSTEM"})
    rag.indices['persona'].insert(persona_doc)
    
    # Mock some content in user_profiles index
    profile_doc = Document(text="User Ekco is a developer.", metadata={"source": "user_logs", "user_id": "123", "user_name": "Ekco"})
    rag.indices['user_profiles'].insert(profile_doc)
    
    # Test Kaia query
    print("Querying: 'Who is Kaia?'")
    results = rag.retrieve("Who is Kaia?")
    assert any("Kaia" in r for r in results)
    print("✓ Correctly routed to persona index.")
    
    # Test User query
    print("Querying: 'Who am I?' for user Ekco")
    results = rag.retrieve("Who am I?", user_id=123, user_name="Ekco")
    assert any("Ekco" in r for r in results)
    print("✓ Correctly routed to user_profiles index.")
    
    # 3. Test Smart Chunking (Indirectly)
    print("\n3. Testing Smart Chunking (Refresh)...")
    # Create a dummy knowledge file
    kb_dir = "./test_kb"
    if not os.path.exists(kb_dir): os.makedirs(kb_dir)
    with open(os.path.join(kb_dir, "test.txt"), "w") as f:
        f.write("This is a test knowledge document. " * 100)
        
    rag.knowledge_base_dir = kb_dir
    rag.refresh_knowledge_base()
    
    # Verify it went into 'knowledge' index
    print("Querying: 'tell me about the test knowledge document'")
    results = rag.retrieve("tell me about the test knowledge document")
    assert any("test knowledge" in r.lower() for r in results)
    print("✓ Successfully indexed and retrieved from knowledge index.")

    print("\n✨ Hierarchical RAG tests passed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_hierarchical_rag())
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        import shutil
        if os.path.exists("./test_storage_hierarchical"):
            shutil.rmtree("./test_storage_hierarchical")
        if os.path.exists("./test_kb"):
            shutil.rmtree("./test_kb")
