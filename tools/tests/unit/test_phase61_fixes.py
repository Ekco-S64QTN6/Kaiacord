"""
Unit Tests for Phase 61 Fixes
=============================
Comprehensive tests for:
- Messaging safe text splitting and length clamping (multiline & unbroken token safety)
- Timezone universal newsroom wall clocks (12-hour format, AM/PM, multizone lookup, DST stability)
- Knowledge Base query grounding detection (positive matches, edge cases, negative small-talk filters)
"""

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


def test_split_text_into_safe_chunks_basic():
    short_text = "hello world this is a test"
    chunks = _split_text_into_safe_chunks(short_text, limit=1990)
    assert len(chunks) == 1
    assert chunks[0] == short_text


def test_split_text_into_safe_chunks_long_multiline():
    lines = [f"Line {i}: " + "x" * 200 for i in range(20)]
    long_text = "\n".join(lines)
    chunks = _split_text_into_safe_chunks(long_text, limit=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1000
        assert len(chunk.strip()) > 0


def test_split_text_into_safe_chunks_super_long_unbroken_line():
    # 3500 chars with no newlines
    long_line = "word " * 700
    chunks = _split_text_into_safe_chunks(long_line, limit=1990)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 1990

    # 3000 chars unbroken single token (no spaces)
    giant_token = "a" * 3000
    token_chunks = _split_text_into_safe_chunks(giant_token, limit=1000)
    assert len(token_chunks) == 3
    for chunk in token_chunks:
        assert len(chunk) <= 1000


def test_get_newsroom_wall_clock_block():
    block = get_newsroom_wall_clock_block()
    assert "[GLOBAL_WALL_CLOCKS (12-Hour Verified Real-Time)]:" in block
    assert "Chicago / US Central (Texas):" in block
    assert "London / UK:" in block
    assert "Sydney / Australia:" in block
    assert "UTC (Universal Base Time):" in block

    # Verify 12-hour format with AM/PM pattern
    # e.g., "Friday, August 21, 2026 | 6:30 PM CDT"
    time_pattern = re.compile(r'\b(1[0-2]|[1-9]):[0-5][0-9]\s+(AM|PM)\b')
    for line in block.split('\n'):
        if line.startswith("- "):
            assert time_pattern.search(line), f"Line lacks valid 12-hour AM/PM time: {line}"


def test_multizone_clock_calculations():
    # Test specific global regions in LOCATION_TIMEZONE_MAP
    test_locations = [
        "America/Chicago",
        "Europe/London",
        "Australia/Sydney",
        "Asia/Tokyo",
        "America/New_York",
        "America/Los_Angeles",
        "America/Denver",
        "Europe/Paris",
        "Europe/Berlin",
        "Europe/Dublin",
        "America/Toronto",
        "Pacific/Auckland",
        "Asia/Singapore",
        "Asia/Hong_Kong",
        "Asia/Seoul",
        "Pacific/Honolulu",
        "UTC"
    ]
    for tz in test_locations:
        formatted_str, hour_int, abbr = calculate_location_time(tz)
        assert isinstance(hour_int, int)
        assert 0 <= hour_int <= 23
        assert len(abbr) >= 2
        assert ("AM" in formatted_str or "PM" in formatted_str)
        # Ensure year 2026+ is present
        assert "202" in formatted_str


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


def test_expanded_time_patterns():
    queries = [
        "time check",
        "what day is it",
        "what is today's date",
        "current date",
        "today's date",
        "what time",
        "what time is it in Tokyo",
        "time in London",
        "what time does Paris have",
        "what time are you on",
        "what is your local time",
        "time at your location",
        "what time is it in New York",
        "what time is it in Sydney",
        "what time is it in Denver",
        "what time is it in Honolulu",
        "what time is it in Auckland",
        "what time is it in Toronto",
    ]
    for q in queries:
        facts = resolve_time_queries(q)
        assert "[DETERMINISTIC_TIME_FACTS]" in facts, f"Failed for query: {q}"
        assert "Chicago / US Central (Texas)" in facts
        assert "London / UK" in facts
        assert "Sydney / Australia" in facts
        assert "UTC (Universal Base Time)" in facts


def test_specific_location_extraction_in_time_query():
    # When asking about Tokyo, Tokyo time facts should be appended to the block
    tokyo_facts = resolve_time_queries("what time is it in Tokyo right now")
    assert "Tokyo, Japan:" in tokyo_facts
    assert "JST" in tokyo_facts

    # When asking about Paris
    paris_facts = resolve_time_queries("what time is it in Paris")
    assert "Paris, France:" in paris_facts

    # When asking about New York
    ny_facts = resolve_time_queries("what time is it in NYC")
    assert "New York City, USA:" in ny_facts

    # When asking about Honolulu / Hawaii
    hawaii_facts = resolve_time_queries("what time is it in Hawaii")
    assert "Hawaii, USA:" in hawaii_facts
    assert "HST" in hawaii_facts
