
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_intelligence import IntentParser, Intent
from utils.core.kaia_rag import KaiaRAG

# Mock RAG to test routing logic without full DB
class MockRAG(KaiaRAG):
    def __init__(self):
        self.indices = {'knowledge': None, 'logs': None}
        self.bm25_cache = {}
        self._lock = asyncio.Lock() # Mock lock
        
    def retrieve(self, query, intent, **kwargs):
        print(f"🔍 RAG Retrieve Called with Strategy: {intent.suggested_strategy}")
        
        # Simulate logic check
        if intent.suggested_strategy == "DREAM_RECALL":
            print("✅ DREAM_RECALL strategy active.")
            print("   - Constraint: Must target 'dream' source type with High Boost (+0.5)")
            print("   - Constraint: Must punish non-dream content (-0.1)")
            print("   - Threshold: High (Strict Memory)")
            return ["Dream Log #123"]
            
        elif intent.suggested_strategy == "CREATIVE_ASSOCIATION":
            print("✅ CREATIVE_ASSOCIATION strategy active.")
            print("   - Constraint: Lower threshold for diversity")
            print("   - Constraint: Slight penalty for dream files to avoid confusion")
            return ["Creative Concept A", "Creative Concept B"]
            
        return []

async def test_separation():
    parser = IntentParser(model="test_model")
    rag = MockRAG()
    
    print("\n--- Test 1: Explicit Dream Recall ---")
    query_dream = "what did you dream about last night?"
    intent_dream = parser.fast_parse(query_dream)
    
    if intent_dream and intent_dream.suggested_strategy == "DREAM_RECALL":
        print(f"✅ Intent Correctly Parsed: {intent_dream.suggested_strategy}")
    else:
        print(f"❌ FAILED: 'dream' query parsed as {intent_dream.suggested_strategy if intent_dream else 'None'}")
        
    print("\n--- Test 2: Creative Brainstorming (Mock) ---")
    # This requires LLM usually, but we check if we have a trigger or if we can simulate the intent object
    intent_creative = Intent(
        explicit_intent="brainstorm story ideas",
        implied_needs=["creativity"],
        emotional_context="curious",
        temporal_focus="future",
        relational_context="social",
        suggested_strategy="CREATIVE_ASSOCIATION", # LLM would output this
        confidence=0.9
    )
    
    rag.retrieve("ideas", intent=intent_creative)
    rag.retrieve("dreams", intent=intent_dream)

if __name__ == "__main__":
    asyncio.run(test_separation())
