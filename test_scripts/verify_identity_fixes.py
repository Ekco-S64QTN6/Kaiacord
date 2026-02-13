import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import RelevanceFeedback, Intent
from utils.infrastructure.system.shutdown_fixed import CleanShutdown

async def test_bot_log_prevention():
    print("\n--- Testing Bot Log Prevention ---")
    rag = KaiaRAG()
    rag._bot_user_id = 12345
    
    # Test with bot ID
    result = rag.log_user_interaction(user_id=12345, user_name="Kaia", message_content="test", bot_response="hi")
    print(f"Bot ID skip result: {result} (Should be True, but skip disk write)")
    
    # Test with bot Name
    result = rag.log_user_interaction(user_id=67890, user_name="Kaia", message_content="test", bot_response="hi")
    print(f"Bot Name skip result: {result} (Should be True, but skip disk write)")

    # Test with real user
    # (Mocking lock to avoid side effects)
    with patch.object(rag, '_lock'):
        result = rag.log_user_interaction(user_id=999, user_name="RealUser", message_content="test", bot_response="hi")
    print(f"Real User log result: {result} (Should proceed to lock)")

async def test_rag_filter_removal():
    print("\n--- Testing RAG Filter Removal ---")
    rag = KaiaRAG()
    # Mock retrieve inner logic or check the source code logic as implemented.
    # We can't easily run a full retrieval without a loaded index, but we can inspect the retrieve method's filtering logic.
    print("Checking retrieve method's decommissioned block...")
    import inspect
    source = inspect.getsource(rag.retrieve)
    if "User Isolation & Hallucination Guard (DECOMMISSIONED)" in source:
        print("✅ Filter removal block found in source.")
    else:
        print("❌ Filter removal block NOT found in source.")

async def test_feedback_metadata():
    print("\n--- Testing Feedback Metadata ---")
    rag = MagicMock()
    feedback = RelevanceFeedback(rag)
    
    await feedback.log_interaction(query="What is Kaiacord?", response="A Discord bot.", user_id=111, user_name="Tester")
    
    # Check the feedback_log
    entry = feedback.feedback_log[0]
    print(f"Feedback entry user_name: {entry.get('user_name')} (Should be 'Tester')")
    
    # Mock process_feedback and Document
    with patch('llama_index.core.Document') as MockDoc:
        await feedback.process_feedback()
        # Verify Document metadata
        for call in MockDoc.call_args_list:
            metadata = call.kwargs.get('metadata', {})
            print(f"Synthetic Doc metadata: {metadata}")
            if metadata.get('user_name') == 'Tester':
                print("✅ user_name metadata correctly passed to Document.")
            else:
                print(f"❌ user_name metadata missing: {metadata}")

async def test_shutdown_ollama_safety():
    print("\n--- Testing Shutdown Ollama Safety ---")
    shutdown = CleanShutdown()
    
    # Mock imports and dependencies
    with patch('psutil.process_iter') as mock_process_iter:
        await shutdown.async_shutdown()
        # Verify if psutil.process_iter was called (it shouldn't be, if I replaced it with 'pass')
        # Wait, I replaced the block with 'pass', so it shouldn't even call psutil.process_iter.
        if mock_process_iter.called:
             print("❌ psutil.process_iter was still called!")
        else:
             print("✅ psutil.process_iter was NOT called (Ollama killing disabled).")

if __name__ == "__main__":
    asyncio.run(test_bot_log_prevention())
    asyncio.run(test_rag_filter_removal())
    asyncio.run(test_feedback_metadata())
    asyncio.run(test_shutdown_ollama_safety())
