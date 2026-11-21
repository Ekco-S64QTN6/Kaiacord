"""Moved tests."""
import pytest
import re
from utils.infrastructure.system.messaging import _split_text_into_safe_chunks
from utils.core.timezone_helper import (
    get_newsroom_wall_clock_block,
    calculate_location_time,
    resolve_time_queries,
    LOCATION_TIMEZONE_MAP,
    NEWSROOM_WALL_CLOCKS
)
from utils.core.message_processor import _is_kb_query


def test_is_kb_query_detection():
    # Direct KB queries
    assert _is_kb_query("Kaia summarize everything in your knowledge_base") is True
    assert _is_kb_query("Find something in your knowledge base that's interesting") is True
    assert _is_kb_query("what is in your knowledge base") is True
    assert _is_kb_query("tell me about files in your corpus") is True
    assert _is_kb_query("search something in your knowledge_base") is True
    assert _is_kb_query("what do you have in your documents") is True
    assert _is_kb_query("list all books in your knowledge base") is True
    assert _is_kb_query("pick an article in your knowledge_base") is True
    assert _is_kb_query("show me a file in your archive") is True
    assert _is_kb_query("what articles do you have") is True
    assert _is_kb_query("what documents do you store") is True
    assert _is_kb_query("explore your knowledge base") is True
    assert _is_kb_query("tell me about what's in your files") is True
    
    # Negative cases (small talk, casual questions)
    assert _is_kb_query("how are you doing today") is False
    assert _is_kb_query("what is the weather in Chicago") is False
    assert _is_kb_query("who is pixel") is False
    assert _is_kb_query("can you help me with Python code") is False
    assert _is_kb_query("tell me a story about a dragon") is False
    assert _is_kb_query("what did starkind say yesterday") is False
