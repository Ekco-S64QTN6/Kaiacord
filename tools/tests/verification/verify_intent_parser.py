
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_intelligence import IntentParser, Intent, ContextCtx
from utils.core.kaia_rag import KaiaRAG
from utils.core.message_context import MessageContext

async def test_intent_parser():
    print("Testing IntentParser...")
    parser = IntentParser(model="test_model")
    
    # Test Fast Trigger
    intent = parser.fast_parse("Hello Kaia")
    if intent and intent.suggested_strategy == "SOCIAL_GREETING":
        print(f"✅ Fast Trigger Success: {intent.suggested_strategy}")
    else:
        print(f"❌ Fast Trigger Failed: {intent}")

    # Test Intent Object creation
    test_intent = Intent(
        explicit_intent="test",
        implied_needs=[],
        emotional_context="neutral",
        temporal_focus="present",
        relational_context="test",
        suggested_strategy="PRECISE_RECALL",
        confidence=1.0
    )
    print(f"✅ Intent Object Created: {test_intent}")

async def test_rag_import():
    print("\nTesting KaiaRAG Import...")
    try:
        # Just check if retrieve accepts intent argument by inspecting signature
        import inspect
        sig = inspect.signature(KaiaRAG.retrieve)
        if 'intent' in sig.parameters:
            print("✅ KaiaRAG.retrieve accepts 'intent' argument.")
        else:
            print("❌ KaiaRAG.retrieve missing 'intent' argument.")
    except Exception as e:
        print(f"❌ KaiaRAG Import Failed: {e}")

async def main():
    await test_intent_parser()
    await test_rag_import()

if __name__ == "__main__":
    asyncio.run(main())
