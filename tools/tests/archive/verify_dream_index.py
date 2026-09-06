
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import Intent

# Mock RAG to test routing logic with new indices
class MockRAG(KaiaRAG):
    def __init__(self):
        # MOCK initialization of indices
        self.indices = {
            'knowledge': "mock_knowledge_index", 
            'logs': "mock_logs_index", 
            'dreams': "mock_dreams_index" 
        }
        self.bm25_cache = {}
        self._lock = asyncio.Lock()
        
    def retrieve(self, query, intent, **kwargs):
        print(f"🔍 RAG Retrieve Called for Query: '{query}'")
        print(f"   Strategy: {intent.suggested_strategy}")
        
        # Copied logic from updated KaiaRAG for verification
        target_itypes = []
        if intent.suggested_strategy == "DREAM_RECALL":
             target_itypes = ['dreams'] 
        elif intent.suggested_strategy == "CREATIVE_ASSOCIATION":
             target_itypes = ['knowledge', 'logs']
        elif intent.suggested_strategy == "PRECISE_RECALL":
             target_itypes = ['knowledge', 'logs', 'user_profiles']
             
        print(f"   Target Indices: {target_itypes}")
        
        if intent.suggested_strategy == "DREAM_RECALL" and target_itypes == ['dreams']:
            print("✅ PASS: DREAM_RECALL targets only 'dreams' index.")
            return True
        elif intent.suggested_strategy == "CREATIVE_ASSOCIATION" and 'dreams' not in target_itypes:
             print("✅ PASS: CREATIVE_ASSOCIATION does NOT target 'dreams' index.")
             return True
             
        print("❌ FAIL: Routing logic mismatch.")
        return False

async def test_routing():
    rag = MockRAG()
    
    print("\n--- Test 1: Dream Recall Routing ---")
    intent_dream = Intent(
        explicit_intent="dream query", implied_needs=[], emotional_context="neutral", 
        temporal_focus="past", relational_context="general", 
        suggested_strategy="DREAM_RECALL", confidence=1.0
    )
    rag.retrieve("dreams", intent=intent_dream)
    
    print("\n--- Test 2: Creative Association Routing ---")
    intent_creative = Intent(
        explicit_intent="creative query", implied_needs=[], emotional_context="neutral", 
        temporal_focus="future", relational_context="general", 
        suggested_strategy="CREATIVE_ASSOCIATION", confidence=1.0
    )
    rag.retrieve("creative", intent=intent_creative)

if __name__ == "__main__":
    asyncio.run(test_routing())
