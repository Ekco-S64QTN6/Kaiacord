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

    assert "[DETERMINISTIC_TIME_FACTS]" in facts
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
        assert "[DETERMINISTIC_TIME_FACTS]" in facts, f"Failed for query: {query}"
        assert "Chicago / US Central (Texas)" in facts
        assert "London / UK" in facts
        assert "Sydney / Australia" in facts
        assert "UTC (Universal Base Time)" in facts
        assert "12-Hour Format" in facts
