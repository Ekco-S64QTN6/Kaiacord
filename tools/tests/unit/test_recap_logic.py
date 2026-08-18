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
    assert _extract_recap_hours("Kaia can I get a summary of the past 24 hours of <#1462239450691145924> and <#1013809281994338398> chatter") == 24
    assert _extract_recap_hours("Kaia can you give me a summary of user interactions over the past 12 hours") == 12
    assert _extract_recap_hours("past 18 hrs of chatter") == 18

def test_is_observational_query_recap_match():
    # Verify that recap queries and user summary queries match observational patterns
    assert _is_observational_query("recap of past interactions") == True
    assert _is_observational_query("summary of today's chat") == True
    assert _is_observational_query("Kaia can I get a summary of the past 24 hours of <#1462239450691145924> and <#1013809281994338398> chatter") == True
    assert _is_observational_query("Kaia can you give me a summary of user interactions over the past 12 hours") == True
    assert _is_observational_query("can I get a summary of the past 24 hours of #general and #kaia-opolis chatter") == True

def test_intent_parser_fast_parse_recap():
    from utils.core.intent_classifier import IntentParser
    ip = IntentParser()
    
    intent1 = ip.fast_parse("Kaia can I get a summary of the past 24 hours of <#1462239450691145924> and <#1013809281994338398> chatter")
    assert intent1 is not None
    assert intent1.suggested_strategy == "RECAP_QUERY"

    intent2 = ip.fast_parse("Kaia can you give me a summary of user interactions over the past 12 hours")
    assert intent2 is not None
    assert intent2.suggested_strategy == "RECAP_QUERY"

    intent3 = ip.fast_parse("summary of #general chatter over the last 6 hours")
    assert intent3 is not None
    assert intent3.suggested_strategy == "RECAP_QUERY"

def test_context_enricher_resolve_channel_mentions():
    from utils.core.context_enricher import ContextEnricher
    import asyncio
    
    class DummyChannel:
        name = "kaia-opolis"

    bot_mock = MagicMock()
    bot_mock.get_channel.return_value = DummyChannel()
    
    async def _dummy_fetch(ch_id):
        return DummyChannel()
        
    bot_mock.fetch_channel = _dummy_fetch
    
    async def _dummy_fetch_user(user_id):
        return None
    bot_mock.fetch_user = _dummy_fetch_user
    
    enricher = ContextEnricher(bot_mock)
    msg_mock = MagicMock()
    msg_mock.guild = None
    msg_mock.mentions = []
    
    raw_text = "Kaia can I get a summary of the past 24 hours of <#1462239450691145924> and <#1013809281994338398> chatter"
    resolved = asyncio.run(enricher.resolve_mentions(raw_text, msg_mock))
    assert "<#" not in resolved
    assert "#kaia-opolis" in resolved

def test_safety_pipeline_channel_recall_fabrication_guard():
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline
    
    fake_output = (
        "summary follows:\n\n"
        "channel #1462239450691145924 :\n"
        "the dominant theme revolved around persistent issues with resource allocation for a distributed rendering farm.\n"
        "channel #1013809281994338398 :\n"
        "the conversation largely centered on starkind's cognitive architecture."
    )
    
    cleaned, reason = PostGenerationSafetyPipeline.process_attempt(
        content=fake_output,
        attempt=1,
        query="summary of past 24 hours",
        is_channel_recall=True,
        channel_refs=["1462239450691145924", "1013809281994338398"]
    )
    
    assert cleaned is not None
    assert "i don't have clear records from those channels right now" in cleaned

@patch('utils.core.message_processor.log_info')
@patch('utils.core.message_processor.asyncio.create_task')
@patch('utils.core.message_processor.load_persona_async')
def test_setup_retrieval_tasks_recap_routing(mock_load_persona, mock_create_task, mock_log_info):
    import asyncio
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
    message_ctx.fast_intent_strategy = "RECAP_QUERY"
    message_ctx.category = "general"
    
    asyncio.run(processor._setup_retrieval_tasks(message_ctx))
    
    # Check log_info for correct routing and hour extraction
    log_calls = [call.args[0] for call in mock_log_info.call_args_list]
    assert any("RECAP routing confirmed — strategy=RECAP_QUERY" in s for s in log_calls)
    assert any("RECAP query — routing to search_recent_events (hours=5)" in s for s in log_calls)
