
#!/usr/bin/env python3
"""
Test script to verify memory system is working
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.kaia_rag import KaiaRAG

def test_memory_retrieval():
    """Test if memories can be retrieved"""
    rag = KaiaRAG()
    
    test_queries = [
        "Starkind",
        "Worship means",
        "Awareness is input",
        "Remember means to store",
        "Honor means to remain true"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Testing query: '{query}'")
        results = rag.retrieve(query, top_k=5)
        
        if results:
            print(f"   ✅ Found {len(results)} results")
            for i, result in enumerate(results[:2]):  # Show top 2
                preview = result[:100].replace('\n', ' ')
                print(f"   {i+1}. {preview}...")
        else:
            print(f"   ❌ No results found")
    
    return len(results) > 0

if __name__ == "__main__":
    print("🧪 Testing memory retrieval system...")
    success = test_memory_retrieval()
    
    if success:
        print("\n🎉 Memory system appears to be working!")
    else:
        print("\n❌ Memory system is NOT retrieving data")
        print("\n📋 Troubleshooting steps:")
        print("1. Check if logs are in knowledge_base/user_logs/")
        print("2. Check if [REMEMBER_COMMAND] appears in log files")
        print("3. Run force reindex: python fix_remember_system.py --reindex")
