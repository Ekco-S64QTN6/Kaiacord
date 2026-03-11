import pytest
import sys
import os
import re
from unittest.mock import MagicMock, patch

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from utils.core.message_processor import _extract_recap_hours, _is_observational_query

def test_extract_recap_hours():
    assert _extract_recap_hours("last 3 hours") == 3
    assert _extract_recap_hours("last 2 days") == 48
    assert _extract_recap_hours("past 6 hours") == 6
    assert _extract_recap_hours("recap of the day") == 24
    assert _extract_recap_hours("3 hr recap") == 3
    assert _extract_recap_hours("no time mentioned") == 24
    assert _extract_recap_hours("last 1 day") == 24

def test_is_observational_query_recap_match():
    # Verify that some recap queries DO match observational patterns
    # (recap|summary|overview)\s+(of\s+)?(today'?s?|recent|the\s+last|past)\s+(chat|interactions?|activity|conversations?)
    assert _is_observational_query("recap of past interactions") == True
    assert _is_observational_query("summary of today's chat") == True

@patch('utils.core.message_processor.log_info')
@patch('utils.core.message_processor.asyncio.create_task')
@patch('utils.core.message_processor.load_persona_async')
@pytest.mark.asyncio
async def test_setup_retrieval_tasks_recap_routing(mock_load_persona, mock_create_task, mock_log_info):
    from utils.core.message_processor import MessageProcessor
    from utils.core.message_context import MessageContext
    
    # Mock dependencies
    ctx_mock = MagicMock()
    ctx_mock.bot = MagicMock()
    ctx_mock.config = MagicMock()
    ctx_mock.config.rag_top_k = 10
    ctx_mock.config.rag_retrieval_timeout = 5
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
    
    # Mock RAG
    processor.rag = MagicMock()
    processor.personalization_engine = MagicMock()
    
    # Test case: RECAP_QUERY
    author_mock = MagicMock()
    author_mock.id = 123
    author_mock.display_name = "testuser"
    
    msg_mock = MagicMock()
    msg_mock.author = author_mock
    
    message_ctx = MessageContext(
        message=msg_mock,
        sanitized_content="recap the last 5 hours",
        is_social=False,
        is_mention=True
    )
    message_ctx.intent = MagicMock()
    message_ctx.intent.suggested_strategy = "RECAP_QUERY"
    message_ctx.category = "general"
    
    await processor._setup_retrieval_tasks(message_ctx)
    
    # Check log_info for correct routing and hour extraction
    log_calls = [call.args[0] for call in mock_log_info.call_args_list]
    assert any("RECAP query — routing to search_recent_events (hours=5)" in s for s in log_calls)
