
import sys
import unittest
from unittest.mock import MagicMock

# FORCE MOCKING of all heavy dependencies
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
sys.modules['llama_index'] = MagicMock()
sys.modules['llama_index.core'] = MagicMock()
sys.modules['llama_index.core.retrievers'] = MagicMock()
sys.modules['llama_index.core.schema'] = MagicMock()
sys.modules['llama_index.readers'] = MagicMock()
sys.modules['ollama'] = MagicMock()
sys.modules['pypdf'] = MagicMock()

import os
import asyncio

# Now inject project path
sys.path.append(os.getcwd())

# Import RAG class - with mocks in place, it should load fine
try:
    from utils.core.kaia_rag import KaiaRAG
    from utils.core.kaia_intelligence import Intent
except Exception as e:
    print(f"Failed to import KaiaRAG or Intent: {e}")
    sys.exit(1)

async def run_verification():
    print("🚀 Starting Isolated RAG Verification...")

    # Instantiate RAG
    # We might need to mock __init__ if it does heavy lifting, but KaiaRAG init seems mostly config which is mocked or safe
    # Actually KaiaRAG init calls _initialize_indices which does disk I/O. We should mock that.
    with unittest.mock.patch('utils.core.kaia_rag.KaiaRAG._initialize_indices') as mock_init_indices:
        rag = KaiaRAG()
    
    # Manually setup indices as Mocks
    rag.indices = {
        'knowledge': MagicMock(),
        'logs': MagicMock(),
        'user_profiles': MagicMock(),
        'dreams': MagicMock()
    }
    
    # Mock retrievers logic
    for k, v in rag.indices.items():
        v.storage_context.docstore.docs.values.return_value = []
        retriever_mock = MagicMock()
        retriever_mock.retrieve.return_value = [] 
        v.as_retriever.return_value = retriever_mock
        
    rag.bm25_cache = {}

    # Helper to check routing
    def check_routing(query_text, intent_obj):
        # Reset mocks
        for v in rag.indices.values():
            v.as_retriever.reset_mock()
            
        print(f"\n🧪 Testing Query: '{query_text}' | Strategy: {intent_obj.suggested_strategy}")
        
        # Run retrieval
        rag.retrieve(query_text, intent=intent_obj)
        
        # Check which indices were touched
        touched = []
        for name, mock_idx in rag.indices.items():
            if mock_idx.as_retriever.called:
                touched.append(name)
        
        print(f"   -> Indices Accessed: {touched}")
        return touched

    # User Test Case 1: "What did you dream about?" -> Dreams Only
    intent1 = Intent(
        explicit_intent="dream query", implied_needs=[], emotional_context="neutral", 
        temporal_focus="past", relational_context="general", 
        suggested_strategy="DREAM_RECALL", confidence=1.0
    )
    routes1 = check_routing("What did you dream about?", intent1)
    if set(routes1) == {'dreams'}:
        print("   ✅ PASS: Dreams Index ONLY")
    else:
        print(f"   ❌ FAIL: Expected ['dreams'], got {routes1}")

    # User Test Case 2: "Show me error logs" -> Logs Only
    intent2 = Intent(
        explicit_intent="debug", implied_needs=[], emotional_context="neutral", 
        temporal_focus="now", relational_context="admin", 
        suggested_strategy="DIAGNOSTIC_DEEP_DIVE", confidence=1.0
    )
    routes2 = check_routing("Show me error logs", intent2)
    if set(routes2) == {'logs'}:
        print("   ✅ PASS: Logs Index ONLY")
    else:
        print(f"   ❌ FAIL: Expected ['logs'], got {routes2}")

    # User Test Case 3: "Explain how AI works" -> Knowledge Only
    intent3 = Intent(
        explicit_intent="explain", implied_needs=[], emotional_context="neutral", 
        temporal_focus="general", relational_context="general", 
        suggested_strategy="CREATIVE_ASSOCIATION", confidence=1.0
    )
    routes3 = check_routing("Explain how AI works", intent3)
    if set(routes3) == {'knowledge'}:
        print("   ✅ PASS: Knowledge Index ONLY")
    else:
        print(f"   ❌ FAIL: Expected ['knowledge'], got {routes3}")

    # User Test Case 4: "status" (Short Query) -> Logs Only (Diagnostic)
    intent4 = Intent(
        explicit_intent="status check", implied_needs=[], emotional_context="neutral", 
        temporal_focus="now", relational_context="admin", 
        suggested_strategy="DIAGNOSTIC_DEEP_DIVE", confidence=1.0
    )
    routes4 = check_routing("status", intent4)
    if set(routes4) == {'logs'}:
        print("   ✅ PASS: Logs Index ONLY (Short query not ignored)")
    else:
        print(f"   ❌ FAIL: Expected ['logs'], got {routes4}")

    # Casual Greeting -> Logs Only
    intent5 = Intent(
        explicit_intent="hi", implied_needs=[], emotional_context="neutral", 
        temporal_focus="now", relational_context="social", 
        suggested_strategy="SOCIAL_GREETING", confidence=1.0
    )
    routes5 = check_routing("hi", intent5)
    if set(routes5) == {'logs'}:
         print("   ✅ PASS: Social Greeting -> Logs Only")

import unittest.mock
if __name__ == "__main__":
    asyncio.run(run_verification())
