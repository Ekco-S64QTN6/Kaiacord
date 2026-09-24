"""The EAM relay planes, from adsb.lol's open ADS-B data.

The E-6B Mercury (TACAMO, "Take Charge And Move Out") relays Emergency Action
Messages to ballistic-missile submarines over a trailing-wire VLF antenna; the
E-4B Nightwatch is the airborne command post. adsb.lol publishes aircraft by
ICAO type (ODbL, no key):

    https://api.adsb.lol/v2/type/E6      E-6B
    https://api.adsb.lol/v2/type/E4B     E-4B

These aircraft often fly with ADS-B off. An empty answer means none are
*broadcasting*, never that none are flying, and every reply says so.

Fetched when asked, cached ten minutes; every sighting is remembered in
memory/radio/tacamo_seen.json so "last seen" can be answered later.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from utils.radio.fetch import FeedError, get_json, is_stale, read_cache, write_cache

BASE = "https://api.adsb.lol/v2/type/"
TYPES = {"E6": "E-6B Mercury (TACAMO)", "E4B": "E-4B Nightwatch"}
CACHE = "tacamo"
SEEN = "tacamo_seen"
MAX_AGE_S = 600


@dataclass
class Sighting:
    kind: str
    hex: str
    callsign: str
    registration: str
    lat: Optional[float]
    lon: Optional[float]
    altitude_ft: Optional[int]
    speed_kt: Optional[float]
    track: Optional[float]
    squawk: str
    seen_at: float

    @property
    def label(self) -> str:
        return TYPES.get(self.kind, self.kind)

    @property
    def map_url(self) -> str:
        return f"https://adsb.lol/?icao={self.hex}"


def parse(kind: str, ac: dict, now: float) -> Sighting:
    alt = ac.get("alt_baro")
    return Sighting(
        kind=kind, hex=str(ac.get("hex") or ""), callsign=str(ac.get("flight") or "").strip(),
        registration=str(ac.get("r") or ""),
        lat=ac.get("lat"), lon=ac.get("lon"),
        altitude_ft=int(alt) if isinstance(alt, (int, float)) else None,   # "ground" on the ground
        speed_kt=ac.get("gs"), track=ac.get("track"), squawk=str(ac.get("squawk") or ""),
        seen_at=now - float(ac.get("seen") or 0),
    )


async def refresh(force: bool = False) -> dict:
    cache = read_cache(CACHE)
    if not force and "aircraft" in cache and not is_stale(cache, MAX_AGE_S):
        return cache
    aircraft = []
    for kind in TYPES:
        payload = await get_json(BASE + kind)
        if not isinstance(payload, dict) or not isinstance(payload.get("ac"), list):
            raise FeedError("adsb.lol no longer answers in the expected shape")
        aircraft += [{"kind": kind, **ac} for ac in payload["ac"]]
    write_cache(CACHE, {"aircraft": aircraft})
    cache = read_cache(CACHE)
    _remember(sightings(cache))
    return cache


def sightings(cache: dict) -> list[Sighting]:
    now = float(cache.get("fetched_at") or time.time())
    return [parse(a["kind"], a, now) for a in cache.get("aircraft") or []]


def _remember(found: list[Sighting]) -> None:
    if not found:
        return
    seen = read_cache(SEEN).get("last") or {}
    for s in found:
        if s.seen_at < (seen.get(s.kind) or {}).get("at", 0):
            continue                    # two of a kind in one answer: keep the most recent
        seen[s.kind] = {"at": s.seen_at, "callsign": s.callsign, "registration": s.registration,
                        "lat": s.lat, "lon": s.lon, "altitude_ft": s.altitude_ft}
    write_cache(SEEN, {"last": seen})


def last_seen() -> dict:
    return read_cache(SEEN).get("last") or {}


def ago(ts: float, now: Optional[float] = None) -> str:
    secs = (now or time.time()) - ts
    if secs < 3600:
        return f"{max(1, int(secs // 60))} min ago"
    if secs < 172800:
        return f"{int(secs // 3600)} h ago"
    return f"{int(secs // 86400)} days ago"
