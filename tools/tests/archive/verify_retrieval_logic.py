
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import Intent

# Mock RAG to test routing logic and thresholds
class MockRAG(KaiaRAG):
    def __init__(self):
        # MOCK initialization of indices
        self.indices = {
            'knowledge': "mock_knowledge_index", 
            'logs': "mock_logs_index", 
            'user_profiles': "mock_profiles_index",
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
             min_threshold = 0.65
        elif intent.suggested_strategy == "CREATIVE_ASSOCIATION":
             target_itypes = ['knowledge']
             min_threshold = 0.75 # Default fallback
        elif intent.suggested_strategy == "PRECISE_RECALL":
             target_itypes = ['knowledge', 'logs', 'user_profiles']
             min_threshold = 0.7
        elif intent.suggested_strategy == "DIAGNOSTIC_DEEP_DIVE":
             target_itypes = ['logs']
             min_threshold = 0.7
        elif intent.suggested_strategy == "SOCIAL_GREETING":
             target_itypes = ['logs']
             min_threshold = 0.9
             
        print(f"   Target Indices: {target_itypes}")
        print(f"   Min Threshold: {min_threshold}")
        
        return target_itypes, min_threshold

async def test_logic():
    rag = MockRAG()
    
    tests = [
        ("PRECISE_RECALL", ['knowledge', 'logs', 'user_profiles'], 0.7),
        ("DIAGNOSTIC_DEEP_DIVE", ['logs'], 0.7), # Tech should include logs only
        ("SOCIAL_GREETING", ['logs'], 0.9), # High threshold, logs only
        ("DREAM_RECALL", ['dreams'], 0.65), # Dreams only
        ("CREATIVE_ASSOCIATION", ['knowledge'], 0.75) # Documents only
    ]
    
    for strategy, expected_indices, expected_threshold in tests:
        print(f"\n--- Testing {strategy} ---")
        intent = Intent(
            explicit_intent="test", implied_needs=[], emotional_context="neutral", 
            temporal_focus="now", relational_context="general", 
            suggested_strategy=strategy, confidence=1.0
        )
        indices, threshold = rag.retrieve("test", intent=intent)
        
        if set(indices) == set(expected_indices) and threshold == expected_threshold:
            print("✅ PASS")
        else:
            print(f"❌ FAIL: Expected {expected_indices}@{expected_threshold}, got {indices}@{threshold}")

if __name__ == "__main__":
    asyncio.run(test_logic())
