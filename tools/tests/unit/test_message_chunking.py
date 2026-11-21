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
