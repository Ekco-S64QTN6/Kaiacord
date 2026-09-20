import pytest
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.social.kaia_social_responder import generate_quip

@pytest.mark.asyncio
async def test_generate_quip_unbound_local_error_fix():
    # Mock dependencies
    bot = AsyncMock()
    bot.ids = []
    
    ollama_client = AsyncMock()
    ollama_client.chat.return_value = {'message': {'content': 'test quip'}}
    
    run_rag_func = AsyncMock()
    rag_instance = MagicMock()
    
    # Mock channel
    channel = AsyncMock()
    channel.name = "general"
    channel.permissions_for.return_value.send_messages = True
    bot.get_channel.return_value = channel
    
    # random.choice is patched because the code under test is exactly the
    # empty-list handling; an unpatched choice would raise before the assertion.
    
    # Mock config
    with patch('utils.infrastructure.system.yaml_config.config') as mock_config:
        mock_config.social_max_interval_hours = 1
        mock_config.idle_quip_timeout_minutes = 10
        mock_config.max_consecutive_quips = 5
        mock_config.blacklisted_channels = []
        mock_config.chat_model = "test-model"
        mock_config.bluesky_cross_post_quips = False
        mock_config.x_cross_post_quips = False
        
        # Mock bot state
        with patch('utils.infrastructure.system.bot_state.bot_state') as mock_state:
            mock_state.last_quip_time = 0.0
            mock_state.last_manual_quip_time = 0.0
            mock_state.last_interaction_time = 0.0
            mock_state.consecutive_quips = 0
            # A real list. On a bare MagicMock this returns a Mock, which the
            # repetition guard cannot read.
            mock_state.get_recent_quips.return_value = []
            
            # Mock internal functions to return EMPTY lists
            with patch('utils.social.kaia_social_responder.get_random_dream_reflection', new_callable=AsyncMock) as mock_dreams, \
                 patch('utils.social.kaia_social_responder.get_random_memories', new_callable=AsyncMock) as mock_memories, \
                 patch('utils.social.kaia_social_responder.load_persona', return_value="system prompt"):
                
                mock_dreams.return_value = []
                mock_memories.return_value = []
                rag_instance.get_recent_highlights = AsyncMock(return_value=[])
                
                with patch('utils.social.kaia_social_responder.is_interesting_post', return_value=True), \
                     patch('utils.social.kaia_social_responder.is_too_vague', return_value=False):
                    
                    class MockCtx:
                        def __init__(self):
                            self.bot = bot
                            self.ollama_client = ollama_client
                            self.rag = rag_instance
                            self.bot_state = mock_state
                            self.config = mock_config
                    
                    ctx = MockCtx()
                    ctx.message_processor = AsyncMock()

                    # The quip path no longer calls ollama itself. It hands the
                    # content to `process_external_mention`, which is the same
                    # pipeline Discord and the forum use — so that is what the
                    # test stands in for. Asserting `ollama_client.chat.called`
                    # here asserted the old architecture: a second persona
                    # load, a hand-built prompt and a direct chat call.
                    with patch(
                        "utils.infrastructure.system.external_mention.process_external_mention",
                        new_callable=AsyncMock,
                    ) as mock_pipeline:
                        mock_pipeline.return_value = "the fallback held."

                        # Execution
                        # This should NOT raise UnboundLocalError
                        await generate_quip(ctx, is_manual=True, target_channel=channel)

                # Verification: it went through the pipeline, not around it.
                assert mock_pipeline.called, "quip bypassed the message pipeline"
                assert not ollama_client.chat.called, \
                    "quip called ollama directly instead of using the pipeline"

                # It should have sent a message
                assert channel.send.called



@pytest.mark.asyncio
async def test_thread_generation_also_uses_the_pipeline():
    """The thread path had the same defect as the single-post path.

    It loaded the persona a second time, built its own six-rule prompt, called
    `ollama_client.chat` at a hardcoded temperature 0.8, and re-applied
    `strip_bot_speak` by hand — so a Bluesky thread was written by different
    code, with none of her channel memory, from the one that answers in
    Discord. `forum_drafting` removed exactly this shape of defect for the
    forum; both social paths now go the same way.
    """
    from utils.social.social_response_generator import generate_social_thread

    ctx = MagicMock()
    ctx.ollama_client = AsyncMock()

    with patch(
        "utils.infrastructure.system.external_mention.process_external_mention",
        new_callable=AsyncMock,
    ) as mock_pipeline:
        mock_pipeline.return_value = (
            "the first thought, which runs on for a while and says something.\n\n"
            "the second thought, following from it and landing somewhere else."
        )
        posts = await generate_social_thread(ctx, "a dream about tape loops", "dream")

    assert mock_pipeline.called, "thread generation bypassed the pipeline"
    assert not ctx.ollama_client.chat.called, "thread called ollama directly"
    assert posts, "the thread came back empty"


@pytest.mark.asyncio
async def test_a_generation_failure_string_is_never_posted_publicly():
    """`i'm drawing a blank on that one` reads as her being stuck in a channel.

    On a public feed it is a bot visibly malfunctioning, which is why the forum
    path already screens for these. The social paths post to Bluesky and X, so
    they screen for them too.
    """
    from utils.social.social_response_generator import generate_social_thread

    ctx = MagicMock()
    ctx.ollama_client = AsyncMock()

    with patch(
        "utils.infrastructure.system.external_mention.process_external_mention",
        new_callable=AsyncMock,
    ) as mock_pipeline:
        mock_pipeline.return_value = "i'm drawing a blank on that one"
        posts = await generate_social_thread(ctx, "anything", "dream")

    assert posts == [], "a generation-failure string would have been posted"


def test_the_quip_novelty_guard_unpacks_its_verdict():
    """`looks_repetitive` returns (verdict, reason), not a bool.

    Testing the tuple itself is always True — a non-empty tuple is truthy — so
    the guard rejected every quip the moment she had any recent post recorded,
    whatever the score. On 2026-09-14 three visibly different posts were
    dropped in a row, each at score 0.00, and the warning blamed repetition:

        "The internet is a strange place..."
        "The light's shifted again..."
        "It's a familiar refrain, isn't it?..."

    A guard that answers the same regardless of its input is not a guard.
    """
    import inspect

    from utils.social import social_response_generator as srg

    src = inspect.getsource(srg.generate_quip)
    assert "repetitive, why = looks_repetitive(" in src, \
        "the verdict is not being unpacked"
    assert "if recent and looks_repetitive(" not in src, \
        "still testing the tuple's truthiness"


def test_distinct_posts_are_not_called_repetitive():
    """The three real posts the guard dropped."""
    from utils.social.forum_participation import looks_repetitive

    posts = [
        "The internet is a strange place. It's easy to forget that the people "
        "behind the avatars are people.",
        "The light's shifted again. It's that late-afternoon quality, the way "
        "the dust motes hang suspended.",
        "It's a familiar refrain, isn't it? The cycle of resentment and the "
        "slow erosion of faith.",
    ]
    for i, post in enumerate(posts):
        against = posts[:i] or ["an unrelated earlier thought"]
        repetitive, why = looks_repetitive(post, against)
        assert not repetitive, f"distinct post flagged as repetitive: {why}"


def test_an_actual_duplicate_is_still_blocked():
    """The guard has to keep doing its job."""
    from utils.social.forum_participation import looks_repetitive

    post = "The internet is a strange place, and it is easy to forget that."
    repetitive, why = looks_repetitive(post, [post])
    assert repetitive, f"an exact duplicate was allowed through: {why}"
