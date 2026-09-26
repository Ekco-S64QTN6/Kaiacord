"""Live sky facts for a chat turn that asks about them.

Asked "space weather?", she described a G3 storm and CMEs arriving in 36–48
hours while NOAA said Kp 4 and B-class flares: chat never saw the data the
`!spaceweather`, `!launch`, `!rocks`, `!quake` and `!iss` commands read. When
the speaker's own words name one of those topics, the numbers go into the
prompt. Pure Python over the commands' own feeds and caches; a stale cache is
refreshed with a short timeout and used as it is if that fails.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from typing import Optional

REFRESH_TIMEOUT_S = 6.0

TOPICS = {
    "space_weather": re.compile(
        r"\b(?:space\s*weather|solar\s+(?:flare|storm|wind|activity|cycle)|flares?|aurora[sl]?|"
        r"northern\s+lights|geomagnetic|kp(?:\s*index)?|cmes?|coronal|sunspots?|"
        r"propagation|band\s+conditions)\b", re.I),
    "launches": re.compile(r"\b(?:(?:rocket|next|upcoming|space|satellite|any|recent|tonight'?s|today'?s)\s+launch(?:es)?|launch\s+(?:window|pad|schedule)|"
                           r"starship|falcon\s*9|lift-?off)\b", re.I),
    # "NEO" only in capitals: lowercase it is the Matrix.
    "asteroids": re.compile(r"\b(?:[Aa]steroids?|[Nn]ear[- ][Ee]arth|[Cc]lose\s+approach|NEOs?)\b"),
    "quakes": re.compile(r"\b(?:earthquakes?|quakes?|seismic|tremors?)\b", re.I),
    "iss": re.compile(r"\b(?:iss|space\s+station|astronauts?|people(?:\s+\w+){0,2}\s+in\s+(?:space|orbit))\b", re.I),
}


def topics(own_words: str) -> list[str]:
    return [name for name, rx in TOPICS.items() if rx.search(own_words or "")]


async def _fresh(fetch, cache_name: str):
    """The feed's value, refreshed if stale; the cached copy if the refresh
    fails or is slow. Returns (value, age in seconds) or (None, None)."""
    from utils.radio.fetch import read_cache
    try:
        value = await asyncio.wait_for(fetch(), REFRESH_TIMEOUT_S)
        cache = read_cache(cache_name)
    except Exception:
        cache = read_cache(cache_name)
        if "data" not in cache:
            return None, None
        value = None
    age = time.time() - float(cache.get("fetched_at") or time.time())
    return value, age


def _age(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    return "just now" if seconds < 120 else f"{seconds / 60:.0f} min ago" if seconds < 7200 else f"{seconds / 3600:.0f} h ago"


async def _space_weather() -> Optional[str]:
    from utils.radio.fetch import read_cache
    from utils.sky import feeds
    value, age = await _fresh(feeds.space_weather, "sky_swpc")
    data = value or read_cache("sky_swpc").get("data")
    if not data:
        return None
    parts = [f"Kp {data['kp']:.1f} ({feeds.kp_words(data['kp'])})"]
    flare = data.get("flare") or {}
    if flare.get("max_class"):
        parts.append(f"latest flare {flare['max_class']} peaking {flare.get('max_time', '')[:16].replace('T', ' ')}Z")
    if data.get("xray"):
        parts.append(f"X-ray background {data['xray']}")
    if data.get("solar_flux"):
        parts.append(f"solar flux {data['solar_flux']}, sunspot number {data.get('sunspots', '?')}")
    return f"Space weather (NOAA SWPC, {_age(age)}): " + "; ".join(parts) + "."


async def _launches() -> Optional[str]:
    from utils.sky import feeds
    try:
        rows = await asyncio.wait_for(feeds.launches(3), REFRESH_TIMEOUT_S)
    except Exception:
        return None
    if not rows:
        return "Upcoming launches (Launch Library 2): none listed."
    items = [f"{r['name']} ({r['provider']}) NET {r['net']:%d %b %H:%M}Z, {r['status'] or 'status unknown'}" for r in rows]
    return "Upcoming launches (Launch Library 2): " + "; ".join(items) + "."


async def _asteroids() -> Optional[str]:
    from utils.sky import feeds
    try:
        rows = await asyncio.wait_for(feeds.close_approaches(), REFRESH_TIMEOUT_S)
    except Exception:
        return None
    if not rows:
        return "Close approaches in the next 30 days (JPL): none within 0.05 AU."
    items = [f"{r['name']} on {r['when']}, {r['ld']:.1f} lunar distances, {feeds.size_from_h(r['h'])}" for r in rows[:3]]
    return "Close approaches in the next 30 days (JPL): " + "; ".join(items) + "."


async def _quakes() -> Optional[str]:
    from utils.sky import feeds
    try:
        rows = await asyncio.wait_for(feeds.quakes(4), REFRESH_TIMEOUT_S)
    except Exception:
        return None
    if not rows:
        return "Earthquakes M4.5+ in the last day (USGS): none."
    items = [f"M{r.get('mag', '?')} {r.get('place', '?')}" for r in rows[:4]]
    return "Earthquakes M4.5+ in the last day (USGS): " + "; ".join(items) + "."


async def _iss() -> Optional[str]:
    from utils.sky import feeds
    try:
        crew = await asyncio.wait_for(feeds.people_in_space(), REFRESH_TIMEOUT_S)
    except Exception:
        return None
    people = (crew or {}).get("people") or {}
    if not people:
        return None
    total = sum(len(v) for v in people.values())
    by = ", ".join(f"{agency} {len(names)}" for agency, names in people.items())
    return f"People in space right now (Launch Library 2): {total} ({by})."


_BUILDERS = {"space_weather": _space_weather, "launches": _launches, "asteroids": _asteroids,
             "quakes": _quakes, "iss": _iss}


async def note_for(own_words: str) -> str:
    """A prompt block with the live numbers for the topics the speaker named,
    or '' when they named none or no feed answered."""
    wanted = topics(own_words)
    if not wanted:
        return ""
    async def _one(name):
        try:
            return await _BUILDERS[name]()
        except Exception:
            return None
    # Concurrently: each feed has its own timeout, and the turn waits for the slowest, not the sum.
    lines = [f"- {line}" for line in await asyncio.gather(*(_one(n) for n in wanted)) if line]
    if not lines:
        return ""
    return ("[LIVE DATA — the real current readings for what was just asked. State these; "
            "do not add storms, forecasts, events or numbers that are not here. "
            f"Now: {datetime.now(timezone.utc):%d %b %H:%M}Z]\n" + "\n".join(lines))
