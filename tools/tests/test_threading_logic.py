import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.social.kaia_bluesky import _split_into_thread, needs_thread_expansion

def test_split_into_thread_basic():
    text = "This is a short post."
    chunks = _split_into_thread(text)
    assert chunks == [text]

def test_split_into_thread_long():
    text = "Sentence one. " * 30 # ~420 chars
    chunks = _split_into_thread(text, max_chars=300)
    assert len(chunks) == 2
    assert len(chunks[0]) <= 300
    assert chunks[0].endswith(".")
    assert chunks[1].startswith("Sentence one.")

def test_split_into_thread_multi_punctuation():
    text = "Is this a question? Yes! And an exclamation! Fine."
    chunks = _split_into_thread(text, max_chars=20)
    # "Is this a question?" (19)
    # "Yes! And an" (11) -> actually "Yes!" (4) "And an exclamation!" (19)
    # "exclamation!" (12)
    # "Fine." (5)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 20

def test_split_into_thread_no_sentence_boundary():
    text = "word " * 100 # No periods
    chunks = _split_into_thread(text, max_chars=100)
    assert len(chunks) > 4
    for c in chunks[:-1]:
        assert c.endswith("...")
        assert len(c) <= 100

def test_needs_thread_expansion():
    # Long post that splits into [~300, ~50]
    long_text = "A" * 290 + ". " + "B" * 50
    needs, remainder = needs_thread_expansion(long_text, min_second_chunk=100)
    assert needs is True
    assert remainder == "B" * 50

    # Long post that splits into [~300, ~150]
    long_text_2 = "A" * 290 + ". " + "B" * 150
    needs, remainder = needs_thread_expansion(long_text_2, min_second_chunk=100)
    assert needs is False

@pytest.mark.asyncio
async def test_generate_quip_expansion_preserves_middle_chunks():
    """Mock test for the critical bug: preserving middle chunks during expansion."""
    from utils.social.kaia_social_responder import generate_quip
    
    # We need text that splits into chunks where the last one is < 100 chars
    # Max len 300.
    # Chunk 1: 300 chars.
    # Chunk 2: 300 chars.
    # Chunk 3: 50 chars.
    # Total: 650 chars.
    # "A" * 300 + " " + "B" * 300 + " " + "C" * 50
    quip_text = "A" * 300 + " " + "B" * 300 + " " + "C" * 50
    
    mock_bot = Mock()
    mock_bot.user.id = 123
    mock_bot.user.name = "kaia"
    mock_bot.get_channel = Mock(return_value=AsyncMock())
    
    mock_ollama = AsyncMock()
    mock_rag = Mock()
    mock_rag.log_user_interaction = Mock()
    mock_rag.get_recent_highlights = AsyncMock(return_value=[])
    
    # Mock config
    mock_config = Mock()
    mock_config.bluesky_cross_post_quips = True
    mock_config.x_cross_post_quips = False
    mock_config.social_max_interval_hours = 3
    mock_config.idle_quip_timeout_minutes = 30
    mock_config.max_consecutive_quips = 5
    mock_config.chat_model = "gemma3:12b"
    
    # Mock bot_state
    mock_state = Mock()
    mock_state.last_quip_time = 0
    mock_state.last_interaction_time = 0
    mock_state.consecutive_quips = 0
    mock_state.last_active_channel_id = 456
    
    # Mock response structure for ollama_client.chat
    mock_ollama.chat.return_value = {
        'message': {
            'content': quip_text
        }
    }
    
    async def mock_on_message(msg):
        msg.channel.sent_messages.append("expanded text")
    
    with patch('utils.infrastructure.system.bot_state.bot_state', mock_state), \
         patch('utils.infrastructure.system.yaml_config.config', mock_config), \
         patch('utils.social.kaia_social_responder.random.random', return_value=0.9), \
         patch('utils.social.kaia_social_responder.get_random_dream_reflection', AsyncMock(return_value=[])), \
         patch('utils.social.kaia_social_responder.get_random_memories', AsyncMock(return_value=[])), \
         patch('utils.social.kaia_social_responder.mock_external_mention', AsyncMock(return_value="expanded text")), \
         patch('utils.social.kaia_social_responder.clean_quip', lambda q, **kwargs: q), \
         patch('utils.social.kaia_social_responder.is_interesting_post', return_value=True), \
         patch('utils.social.kaia_social_responder.is_too_vague', return_value=False), \
         patch('utils.social.kaia_bluesky.post_thread_to_bluesky', AsyncMock(return_value=(True, "mock_uri"))) as mock_post_thread:


        
        class MockCtx:
            def __init__(self):
                self.bot = mock_bot
                self.ollama_client = mock_ollama
                self.rag = mock_rag
                self.bot_state = mock_state
                self.config = mock_config
                
        ctx = MockCtx()
        await generate_quip(ctx, is_manual=True, on_message_func=mock_on_message)
        
        # Verify mock_post_thread was called (meaning expansion happened)
        if not mock_post_thread.called:
             # Debug info if it failed
             print(f"Mock post thread not called. Post quip called: {mock_post_quip.called}")
             assert False, "Expansion did not trigger"

        called_chunks = mock_post_thread.call_args[0][0]
        # With the constructed text:
        # 1. "A"*300 (300 chars) -> Chunk 1
        # 2. "B"*300 (300 chars) -> Chunk 2
        # 3. "C"*50 (50 chars) -> Chunk 3 (Remainder, < 100)
        # Expansion should happen on Chunk 3.
        # Result thread: Chunk 1, Chunk 2, Expanded(Chunk 3)
        
        assert len(called_chunks) == 3
        # Check content roughly
        assert "A" * 10 in called_chunks[0]
        assert "B" * 10 in called_chunks[1]
        assert "expanded text" in called_chunks[2]


