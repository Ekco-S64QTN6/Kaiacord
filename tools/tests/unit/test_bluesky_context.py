import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from utils.social.kaia_social_responder import mock_external_mention
from utils.core.message_processor import MessageProcessor
from utils.infrastructure.logging.kaia_logger import log_info

async def test_bluesky_context_wrapping():
    log_info("Testing context wrapping in mock_external_mention...")
    
    # Mock on_message_func
    async def mock_on_message(msg):
        msg.channel.sent_messages.append("Ack")
        # Capture the formatted content
        test_bluesky_context_wrapping.captured_content = msg.content

    root_text = "This is the original post."
    parent_text = "This is the reply I'm replying to."
    user_text = "Kaia, what do you think?"
    
    await mock_external_mention(
        on_message_func=mock_on_message,
        content=user_text,
        author_name="testuser",
        author_id="123",
        platform="bluesky",
        parent_text=parent_text,
        root_text=root_text
    )
    
    content = test_bluesky_context_wrapping.captured_content
    print(f"Wrapped Content:\n{content}\n")
    
    assert "[ORIGINAL_POST]" in content
    assert root_text in content
    assert "[REPLYING_TO]" in content
    assert parent_text in content
    assert "[USER_MESSAGE]" in content
    assert user_text in content
    log_info("SUCCESS: Context wrapping verified.")

async def test_message_processor_unwrapping():
    log_info("Testing context unwrapping in MessageProcessor...")
    
    # Minimal mock for MessageProcessor dependencies
    mock_ctx = MagicMock()
    mock_ctx.bot = MagicMock()
    mock_ctx.config = MagicMock()
    mock_ctx.config.ignored_users = []
    mock_ctx.config.blacklisted_channels = []
    mock_ctx.config.whitelisted_channels = []
    mock_ctx.bot_state = MagicMock()
    mock_ctx.bot_state.boot_complete = True
    mock_ctx.rate_limiter = MagicMock()
    mock_ctx.rate_limiter.is_allowed.return_value = True
    mock_ctx.shutdown_manager = MagicMock()
    mock_ctx.shutdown_manager.shutting_down = False
    
    processor = MessageProcessor(mock_ctx, None, None, None, None, None)
    
    # Mock context_enricher
    processor.context_enricher = AsyncMock()
    
    root_text = "Original root text"
    parent_text = "Parent context text"
    user_text = "My actual message"
    
    # Simulated enriched content with tags
    enriched_raw = f"[ORIGINAL_POST]\n{root_text}\n\n[REPLYING_TO]\n{parent_text}\n\n[USER_MESSAGE]\n{user_text}"
    processor.context_enricher.enrich_content.return_value = enriched_raw
    
    # Mock sanitize_prompt
    with patch('utils.core.sanitizer.sanitize_prompt', side_effect=lambda x: x):
        # We only want to test up to context initialization
        # So we'll patch _run_intelligence_pipeline to stop there
        with patch.object(processor, '_run_intelligence_pipeline', new_callable=AsyncMock):
            mock_msg = MagicMock()
            mock_msg.platform = "bluesky"
            mock_msg.content = "kaia test"
            mock_msg.author.name = "testuser"
            mock_msg.author.id = "123"
            mock_msg.channel.id = 456
            
            # Patch MessageContext to capture the arguments
            with patch('utils.core.message_processor.MessageContext') as mock_context_class:
                await processor.process(mock_msg)
                
                # Check the arguments passed to MessageContext
                args, kwargs = mock_context_class.call_args
                passed_ctx = kwargs
                
                print(f"Unwrapped parent_context: {kwargs.get('parent_context')}")
                print(f"Unwrapped root_context: {kwargs.get('root_context')}")
                print(f"Unwrapped sanitized_content: {kwargs.get('sanitized_content')}")
                
                assert kwargs.get('parent_context') == parent_text
                assert kwargs.get('root_context') == root_text
                assert kwargs.get('sanitized_content') == user_text
    
    log_info("SUCCESS: Context unwrapping verified.")

async def test_message_processor_prompt_construction():
    log_info("Testing prompt construction in MessageProcessor...")
    
    # Mock dependencies
    mock_ctx = MagicMock()
    mock_ctx.bot = MagicMock()
    mock_ctx.config = MagicMock()
    mock_ctx.bot_state = MagicMock()
    mock_ctx.bot_state.channel_memory = {}
    mock_ctx.stats_tracker = MagicMock()
    mock_ctx.news_manager = None
    
    processor = MessageProcessor(mock_ctx, None, None, None, None, None)
    
    # Create a MessageContext with root and parent context
    mock_msg = MagicMock()
    mock_msg.author.display_name = "testuser"
    mock_msg.channel.id = 123
    
    from utils.core.message_context import MessageContext
    ctx = MessageContext(
        message=mock_msg,
        sanitized_content="User input",
        parent_context="Immediate parent post content.",
        root_context="Original thread starter content."
    )
    
    optimized = {
        'persona': "You are Kaia.",
        'rag': "Some facts.",
        'history': "Previous chat."
    }
    
    messages = processor._construct_messages(ctx, optimized)
    system_msg = messages[0]['content']
    
    print(f"System Prompt:\n{system_msg}\n")
    
    assert "[ROOT_POST]" in system_msg
    assert "Original thread starter content." in system_msg
    assert "[PARENT_CONTEXT]" in system_msg
    assert "Immediate parent post content." in system_msg
    
    # Test case where root == parent (should only show THREAD_CONTEXT)
    ctx_same = MessageContext(
        message=mock_msg,
        sanitized_content="User input",
        parent_context="Same content.",
        root_context="Same content."
    )
    
    messages_same = processor._construct_messages(ctx_same, optimized)
    system_msg_same = messages_same[0]['content']
    
    assert "[ROOT_POST]" not in system_msg_same
    assert "[THREAD_CONTEXT]" in system_msg_same
    
    log_info("SUCCESS: Prompt construction verified.")

if __name__ == "__main__":
    asyncio.run(test_bluesky_context_wrapping())
    asyncio.run(test_message_processor_unwrapping())
    asyncio.run(test_message_processor_prompt_construction())
