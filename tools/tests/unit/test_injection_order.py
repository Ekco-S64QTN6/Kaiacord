"""Verify that identity injection order is CONSTITUTION → SELF-MODEL → PERSONA."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from unittest import mock



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


# ── Prompt ordering and the KV prefix cache ──────────────────────────

def test_the_stable_persona_precedes_every_volatile_block():
    """llama.cpp reuses the KV cache for the longest token prefix shared with
    the previous request, and the persona is ~7.5k of this prompt's ~12.9k
    tokens.

    Both constraint blocks used to sit in front of it. Each is empty on an
    ordinary turn and appears only for a recap or knowledge-base query, so
    asking one of those questions shifted every subsequent token and discarded
    the cached prefix — on that turn, and again on the next when the block went
    away. Measured against a live gemma3:12b on an 8.4k-token prompt, the
    prompt-eval on the changed turn was 6.76s with the volatile block leading
    and 0.59s with it trailing.
    """
    from pathlib import Path
    src = Path("utils/core/message_processor.py").read_text(encoding="utf-8")

    start = src.index("full_system_prompt = (")
    block = src[start:src.index(")", start)]

    order = [name for name in (
        "system_prompt", "kb_constraint_block", "recap_constraint_block",
        "rag_block", "metadata_block", "safeguard_block", "instruction",
    ) if name in block]

    assert order[0] == "system_prompt", (
        f"the persona must lead the prompt or the cached prefix is worthless; "
        f"found {order[0]!r} first")
    for volatile in ("kb_constraint_block", "recap_constraint_block", "rag_block"):
        assert block.index("system_prompt") < block.index(volatile), (
            f"{volatile} precedes the persona and invalidates the prefix cache")


def test_the_constraints_still_precede_the_rag_nodes_they_describe():
    """Both blocks say "the RAG context nodes below". Moving them off the front
    must not move them past what they are talking about."""
    from pathlib import Path
    src = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    start = src.index("full_system_prompt = (")
    block = src[start:src.index(")", start)]
    assert block.index("kb_constraint_block") < block.index("rag_block")
    assert block.index("recap_constraint_block") < block.index("rag_block")


def test_the_behavioural_instruction_stays_last():
    """The anti-botspeak ruleset is at the end deliberately — recency is what
    makes it stick. The cache reordering must not have disturbed that."""
    from pathlib import Path
    src = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    start = src.index("full_system_prompt = (")
    block = src[start:src.index(")", start)]
    assert block.rstrip().endswith('f"{instruction}"')
