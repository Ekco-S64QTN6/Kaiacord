"""
Deterministic Global Newsroom Wall Clocks Resolver
===================================================

Provides deterministic, zoneinfo-based timezone arithmetic for Kaiacord,
injecting verified 12-hour real-time facts for 4 primary global timezones
(Chicago/Texas, London, Sydney, UTC) + any mentioned locations directly into
system prompt context. Prevents LLM mental-math hallucinations, handles Daylight
Saving Time (DST) transitions, and accounts for leap years via standard IANA.
"""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List, Tuple

from utils.infrastructure.logging.kaia_logger import log_error

# Primary 4 Global Newsroom Wall Clocks (12-Hour Format)
NEWSROOM_WALL_CLOCKS: List[Tuple[str, str]] = [
    ("America/Chicago", "Chicago / US Central (Texas)"),
    ("Europe/London", "London / UK"),
    ("Australia/Sydney", "Sydney / Australia"),
    ("UTC", "UTC (Universal Base Time)"),
]

# Location & Region aliases -> (IANA Timezone, Display Name)
LOCATION_TIMEZONE_MAP: Dict[str, Tuple[str, str]] = {
    "texas": ("America/Chicago", "Texas, USA"),
    "tx": ("America/Chicago", "Texas, USA"),
    "london": ("Europe/London", "London, UK"),
    "uk": ("Europe/London", "United Kingdom"),
    "england": ("Europe/London", "England"),
    "britain": ("Europe/London", "Great Britain"),
    "sydney": ("Australia/Sydney", "Sydney, Australia"),
    "australia": ("Australia/Sydney", "Australia (Sydney)"),
    "aussie": ("Australia/Sydney", "Australia (Sydney)"),
    "tokyo": ("Asia/Tokyo", "Tokyo, Japan"),
    "japan": ("Asia/Tokyo", "Japan"),
    "new york": ("America/New_York", "New York, USA"),
    "nyc": ("America/New_York", "New York City, USA"),
    "ny": ("America/New_York", "New York, USA"),
    "los angeles": ("America/Los_Angeles", "Los Angeles, USA"),
    "la": ("America/Los_Angeles", "Los Angeles, USA"),
    "california": ("America/Los_Angeles", "California, USA"),
    "ca": ("America/Los_Angeles", "California, USA"),
    "chicago": ("America/Chicago", "Chicago, USA"),
    "paris": ("Europe/Paris", "Paris, France"),
    "france": ("Europe/Paris", "France"),
    "berlin": ("Europe/Berlin", "Berlin, Germany"),
    "germany": ("Europe/Berlin", "Germany"),
    "utc": ("UTC", "Coordinated Universal Time"),
    "gmt": ("UTC", "Greenwich Mean Time"),
}

_TIME_QUERY_PATTERNS = [
    re.compile(r"what\s+time\s+is\s+it", re.IGNORECASE),
    re.compile(r"current\s+time", re.IGNORECASE),
    re.compile(r"time\s+in\s+([a-zA-Z\s_]+)", re.IGNORECASE),
    re.compile(r"time\s+for\s+([a-zA-Z\s_]+)", re.IGNORECASE),
    re.compile(r"what\s+time\s+does\s+([a-zA-Z\s_]+)\s+have", re.IGNORECASE),
]


def calculate_location_time(tz_name: str) -> Tuple[str, int, str]:
    """
    Calculate formatted 12-hour time for an IANA timezone string.
    Automatically accounts for Daylight Saving Time (DST) and Leap Years via zoneinfo/IANA.
    Returns: (formatted_time_str, hour_int, timezone_abbr)
    """
    now_utc = datetime.now(timezone.utc)
    try:
        tz = ZoneInfo(tz_name)
        dt = now_utc.astimezone(tz)
        abbr = dt.strftime('%Z')
        # 12-hour format with AM/PM (e.g., "8:10 PM CDT")
        time_12h = dt.strftime('%I:%M %p').lstrip('0')
        date_str = dt.strftime('%A, %B %d, %Y')
        full_str = f"{date_str} | {time_12h} {abbr}"
        return full_str, dt.hour, abbr
    except Exception as e:
        log_error(f"Error calculating timezone {tz_name}: {e}")
        time_12h = now_utc.strftime('%I:%M %p').lstrip('0')
        date_str = now_utc.strftime('%A, %B %d, %Y')
        return f"{date_str} | {time_12h} UTC", now_utc.hour, "UTC"


def resolve_time_queries(text: str) -> str:
    """
    Detect time queries in text and produce deterministic 12-hour real-time facts
    for the 4 primary Global Newsroom Wall Clocks + any specific target location requested.
    Returns empty string if no time query detected.
    """
    if not text:
        return ""

    text_lower = text.lower()
    is_time_query = any(pat.search(text_lower) for pat in _TIME_QUERY_PATTERNS)
    if not is_time_query:
        return ""

    facts: List[str] = []
    seen_tz: set = set()

    # 1. Always include the 4 Global Newsroom Wall Clocks (Chicago, London, Sydney, UTC)
    for tz_name, label in NEWSROOM_WALL_CLOCKS:
        time_str, _, abbr = calculate_location_time(tz_name)
        seen_tz.add(tz_name)
        facts.append(f"- {label}: {time_str}")

    # 2. Add specific mentioned location aliases if not already in wall clocks
    for loc_key, (tz_name, display_name) in LOCATION_TIMEZONE_MAP.items():
        if re.search(r'\b' + re.escape(loc_key) + r'\b', text_lower):
            if tz_name not in seen_tz:
                seen_tz.add(tz_name)
                time_str, _, abbr = calculate_location_time(tz_name)
                facts.append(f"- {display_name}: {time_str}")

    fact_block = (
        "[DETERMINISTIC_TIME_FACTS]: Verified Real-Time Global Wall Clocks (12-Hour Format):\n" +
        "\n".join(facts) + "\n" +
        "CRITICAL INSTRUCTION: Respond using 12-hour time format (e.g. 8:10 PM). Use these exact computed real-time values when stating current times."
    )
    return fact_block
