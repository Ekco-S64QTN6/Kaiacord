"""
Unit Tests for Timezone Helper & Newsroom Wall Resolver
======================================================
"""

import pytest
from utils.core.timezone_helper import (
    calculate_location_time,
    resolve_time_queries,
    LOCATION_TIMEZONE_MAP,
    NEWSROOM_WALL_CLOCKS
)
from utils.core.message_processor import _get_user_time_info
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


def test_location_time_calculation():
    time_str, hour, abbr = calculate_location_time("America/Chicago")
    assert isinstance(hour, int)
    assert 0 <= hour <= 23
    assert abbr in ["CST", "CDT"]
    assert "America/Chicago" not in time_str  # Formatted string

    utc_str, utc_hour, utc_abbr = calculate_location_time("UTC")
    assert utc_abbr == "UTC"
    assert "UTC" in utc_str


def test_resolve_time_queries():
    query = "what time is it in Texas right now kaia and what time is it in London kaia"
    facts = resolve_time_queries(query)

    assert "[CURRENT_TIME_FACTS]" in facts
    assert "Chicago / US Central (Texas)" in facts
    assert "London / UK" in facts
    assert "Sydney / Australia" in facts
    assert "UTC (Universal Base Time)" in facts

    # Non-time query
    no_facts = resolve_time_queries("hello kaia how are you doing today")
    assert no_facts == ""


def test_get_user_time_info_integration():
    time_str, hour, tz_name = _get_user_time_info("ekco")
    assert tz_name in ["CDT", "CST"]
    assert 0 <= hour <= 23

    fallback_str, fallback_hour, fallback_tz = _get_user_time_info(None)
    assert fallback_tz in ["CDT", "CST"]
    assert 0 <= fallback_hour <= 23


def test_newsroom_wall_clocks():
    for query in [
        "what time is it Kaia",
        "what's the time",
        "what is the time",
        "what time do you have",
        "what time is it right now",
        "do you know what time it is",
        "got the time",
    ]:
        facts = resolve_time_queries(query)
        assert "[CURRENT_TIME_FACTS]" in facts, f"Failed for query: {query}"
        assert "Chicago / US Central (Texas)" in facts
        assert "London / UK" in facts
        assert "Sydney / Australia" in facts
        assert "UTC (Universal Base Time)" in facts
        assert "12-hour" in facts.lower()


def test_get_newsroom_wall_clock_block():
    block = get_newsroom_wall_clock_block()
    assert "[GLOBAL_WALL_CLOCKS] (12-hour, computed from one instant):" in block
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
        assert "[CURRENT_TIME_FACTS]" in facts, f"Failed for query: {q}"
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
