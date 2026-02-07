
import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.kaia_intelligence import ContextWeaver, IntentParser, Intent

async def test_context_weaver():
    print("Testing ContextWeaver...")
    
    # Mock channel memory
    memory = [
        {'role': 'user', 'content': 'Hello Kaia'},
        {'role': 'assistant', 'content': 'Hi there!'},
        {'role': 'user', 'content': 'My name is Ekco'}
    ]
    
    context = ContextWeaver.weave(memory)
    print(f"✅ Context Created: Last Turns: {context.last_turns}")
    
    if len(context.last_turns) == 3:
        print("✅ Context Turn Count Correct")
    else:
        print(f"❌ Context Turn Count Incorrect: {len(context.last_turns)}")

async def test_intent_with_context():
    print("\nTesting IntentParser with Context...")
    parser = IntentParser(model="test_model")
    
    # Mock context
    memory = [{'role': 'user', 'content': 'system status'}]
    context = ContextWeaver.weave(memory)
    
    # Fast parse check
    intent = parser.fast_parse("status")
    if intent and intent.suggested_strategy == "COMMAND_EXECUTION":
        print(f"✅ Fast Trigger with Context (Implicit check): {intent.suggested_strategy}")

async def main():
    await test_context_weaver()
    # await test_intent_with_context() # Requires LLM or mock, skipping for now as we test logic

if __name__ == "__main__":
    asyncio.run(main())
