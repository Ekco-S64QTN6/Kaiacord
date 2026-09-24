"""Number-station schedule from Priyom.org.

Priyom's schedule page reads an undocumented calendar endpoint:

    https://calendar2.priyom.org/events?timeMin=<ISO>&timeMax=<ISO>
    → {"items": [{"summary": "E11 13470kHz USB", "start": {"dateTime": "...Z"}}, ...]}

One fetch covers a day and a half, so a poll every few hours always has the
next several hours in hand. Each entry is parsed into station, frequency and
mode; the listen link is the same tuned UTwente WebSDR link Priyom's own page
builds (`?tune=<kHz><mode>`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.radio.fetch import FeedError, get_json, is_stale, read_cache, write_cache

CALENDAR = "https://calendar2.priyom.org/events"
CACHE = "priyom_schedule"
WEBSDR = "http://websdr.ewi.utwente.nl:8901/?tune="
WINDOW = timedelta(hours=36)

# "E11 13470kHz USB", "F06a 17536kHz RTTY", "XPA2 Search", "F03 Search (May not always transmit)"
_ENTRY = re.compile(r"^\s*(?P<station>[A-Z]{1,4}\d{0,3}[a-z]?)\s+(?:(?P<khz>\d{3,5}(?:\.\d+)?)\s*kHz\s*(?P<mode>[A-Za-z0-9-]+)?)?(?P<rest>.*)$")

#: What a station family is, for people who have never heard one.
FAMILY = {
    "E": "English voice", "G": "German voice", "S": "Slavic voice", "V": "other-language voice",
    "M": "Morse", "F": "digital", "X": "digital / noise", "H": "digital", "P": "digital",
}
NAMES = {"E11": "“Oracle”", "S06": "“Russian Man”", "XPA": "“Russian Polytone”"}
VOICE_MODES = {"USB", "LSB", "AM"}


@dataclass
class Transmission:
    station: str
    start: datetime
    khz: Optional[float]
    mode: str
    note: str

    @property
    def family(self) -> str:
        if self.station in NAMES:
            return NAMES[self.station]
        return FAMILY.get(self.station[:1], "")

    @property
    def listen_url(self) -> Optional[str]:
        """Priyom's tuned WebSDR link. UTwente covers up to ~29 MHz."""
        if not self.khz or self.khz > 29000:
            return None
        mode = self.mode.lower() if self.mode.upper() in {"USB", "LSB", "AM", "CW", "FM"} else "usb"
        return f"{WEBSDR}{self.khz:g}{mode}"


def parse(item: dict) -> Optional[Transmission]:
    summary = str((item or {}).get("summary") or "").strip()
    start = ((item or {}).get("start") or {}).get("dateTime")
    if not summary or not start:
        return None
    try:
        when = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except ValueError:
        return None
    hit = _ENTRY.match(summary)
    if not hit:
        return Transmission(station=summary.split()[0], start=when, khz=None, mode="", note=summary)
    khz = float(hit["khz"]) if hit["khz"] else None
    return Transmission(station=hit["station"], start=when, khz=khz,
                        mode=(hit["mode"] or "").upper(), note=hit["rest"].strip(" ()"))


async def refresh(max_age_s: float, force: bool = False, now: Optional[datetime] = None) -> dict:
    cache = read_cache(CACHE)
    if not force and cache.get("items") is not None and not is_stale(cache, max_age_s):
        return cache
    now = now or datetime.now(timezone.utc)
    params = {"timeMin": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
              "timeMax": (now + WINDOW).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    payload = await get_json(CALENDAR, params)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise FeedError("Priyom's calendar no longer answers in the expected shape")
    write_cache(CACHE, {"items": payload["items"]})
    return read_cache(CACHE)


def upcoming(cache: dict, hours: float = 6, now: Optional[datetime] = None,
             station: Optional[str] = None) -> list[Transmission]:
    now = now or datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)
    out = []
    for item in cache.get("items") or []:
        t = parse(item)
        if not t or not (now - timedelta(minutes=5) <= t.start <= end):
            continue
        if station and t.station.lower() != station.lower() and not t.station.lower().startswith(station.lower()):
            continue
        out.append(t)
    out.sort(key=lambda t: t.start)
    return out
