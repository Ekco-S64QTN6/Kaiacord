"""Verify that identity injection order is CONSTITUTION → SELF-MODEL → PERSONA."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from unittest import mock

# Mock ContextEnricher to avoid bs4 dependency in test environment
sys.modules['utils.core.context_enricher'] = mock.MagicMock()

@patch('utils.core.message_processor.log_info')
@patch('utils.core.message_processor.log_debug')
@pytest.mark.asyncio
async def test_injection_order_constitution_first(mock_log_debug, mock_log_info):
    from utils.core.message_processor import MessageProcessor
    from utils.core.message_context import MessageContext

    ctx_mock = MagicMock()
    ctx_mock.bot = MagicMock()
    ctx_mock.config = MagicMock()
    ctx_mock.config.knowledge_base_dir = "/tmp"
    ctx_mock.news_manager = MagicMock()
    ctx_mock.dream_engine = MagicMock()
    ctx_mock.bot_state = MagicMock()

    processor = MessageProcessor(
        ctx=ctx_mock,
        response_optimizer=MagicMock(),
        context_optimizer=MagicMock(),
        relevance_feedback=MagicMock(),
        news_enhancer=MagicMock(),
        rag_enhancer=MagicMock()
    )

    # Seed the identity cache directly
    processor._identity_cache = {
        "self_model": "I am a reflective AI.",
        "constitution": "I operate with honesty."
    }
    processor._identity_cache_time = float('inf')  # prevent refresh

    processor.rag = MagicMock()
    processor.personalization_engine = MagicMock()
    processor.personalization_engine.adapt_prompt = lambda p, t: p  # passthrough

    # Build a minimal MessageContext
    author_mock = MagicMock()
    author_mock.id = 123
    author_mock.display_name = "tester"
    msg_mock = MagicMock()
    msg_mock.author = author_mock

    message_ctx = MessageContext(
        message=msg_mock,
        sanitized_content="hello",
        is_social=False,
        is_mention=True
    )
    message_ctx.category = "general"
    message_ctx.intent = None
    message_ctx.fast_intent_strategy = None

    # Simulate retrieval results with a persona string
    results = {
        'persona': "I am Kaia's base persona.",
        'rag': [],
        'traits': {}
    }

    await processor._process_retrieval_results(
        message_ctx, results, ask_whats_new=False, is_news_query=False, clean_query="hello"
    )

    prompt = message_ctx.system_prompt

    # Assert the order: CONSTITUTION before SELF-MODEL before PERSONA
    const_pos = prompt.find("[CONSTITUTION")
    self_pos  = prompt.find("[SELF-MODEL")
    persona_pos = prompt.find("I am Kaia's base persona.")

    assert const_pos != -1,  f"Constitution not found in prompt: {prompt[:300]}"
    assert self_pos  != -1,  f"Self-model not found in prompt: {prompt[:300]}"
    assert persona_pos != -1, f"Persona not found in prompt: {prompt[:300]}"

    assert const_pos < self_pos < persona_pos, (
        f"Wrong injection order! "
        f"CONSTITUTION@{const_pos}, SELF-MODEL@{self_pos}, PERSONA@{persona_pos}\n"
        f"Prompt preview: {prompt[:400]}"
    )
