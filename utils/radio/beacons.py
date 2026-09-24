"""The NCDXF/IARU International Beacon Project, heard by Kaia.

Eighteen beacons on six continents take turns on five bands, ten seconds
each, on a fixed three-minute cycle synchronised to UTC. On 14.100 MHz the
beacon in slot n (0–17) of the cycle is BEACONS[n]; each higher band runs
one slot behind the one below. So who is transmitting is arithmetic, and
listening to one full cycle on one band says which parts of the world are
reachable from the receiver right now: real propagation, measured.

Each transmission is the callsign in Morse, then four one-second dashes at
100 W, 10 W, 1 W and 0.1 W. We read the receiver's S-meter through the
cycle — not audio loudness, which the receiver's AGC flattens — and compare
each slot's peak with the cycle's own quietest slots.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from utils.radio import kiwi
from utils.radio.fetch import FeedError, read_cache, write_cache

BANDS_KHZ = (14100.0, 18110.0, 21150.0, 24930.0, 28200.0)
CYCLE_S = 180
SLOT_S = 10
CACHE = "beacons_heard"
FRESH_S = 30 * 60
HEARD_DB = 6.0          # this far above the quiet slots counts as heard

#: (callsign, where) in transmission order.
BEACONS = [
    ("4U1UN", "United Nations, New York"), ("VE8AT", "Nunavut, Canada"), ("W6WX", "California, USA"),
    ("KH6RS", "Hawaii"), ("ZL6B", "New Zealand"), ("VK6RBP", "Western Australia"),
    ("JA2IGY", "Japan"), ("RR9O", "Novosibirsk, Russia"), ("VR2B", "Hong Kong"),
    ("4S7B", "Sri Lanka"), ("ZS6DN", "South Africa"), ("5Z4B", "Kenya"),
    ("4X6TU", "Israel"), ("OH2B", "Finland"), ("CS3B", "Madeira"),
    ("LU4AA", "Argentina"), ("OA4B", "Peru"), ("YV5B", "Venezuela"),
]


def on_air(when: datetime, band_index: int = 0) -> int:
    """Index into BEACONS of the beacon transmitting on a band at `when`."""
    slot = int(when.timestamp()) % CYCLE_S // SLOT_S
    return (slot - band_index) % len(BEACONS)


def now_on_air(when: Optional[datetime] = None) -> list[tuple[float, str, str]]:
    when = when or datetime.now(timezone.utc)
    return [(khz, *BEACONS[on_air(when, i)]) for i, khz in enumerate(BANDS_KHZ)]


@dataclass
class Heard:
    call: str
    where: str
    db: float

    @property
    def heard(self) -> bool:
        return self.db >= HEARD_DB


def slot_levels(readings: list[tuple], band_index: int = 0) -> dict[int, float]:
    """Peak signal strength (dBm) per beacon, from timestamped RSSI readings.
    The first and last second of each slot are skipped: timestamps are whole
    seconds and slot edges wander with receiver latency."""
    by_beacon: dict[int, list[float]] = {}
    for when, dbm in readings:
        into = int(when.timestamp()) % SLOT_S
        if into < 1 or into > SLOT_S - 2:
            continue
        by_beacon.setdefault(on_air(when, band_index), []).append(dbm)
    return {k: max(v) for k, v in by_beacon.items() if len(v) >= 5}


def judge(levels: dict[int, float]) -> list[Heard]:
    """dB above the cycle's quiet slots (levels are already dBm)."""
    if len(levels) < 6:
        raise FeedError("the listen was too short to cover the beacon cycle")
    quiet = float(np.median(sorted(levels.values())[: max(3, len(levels) // 3)]))
    return [Heard(BEACONS[i][0], BEACONS[i][1], levels[i] - quiet) for i in sorted(levels)]


_lock = asyncio.Lock()


async def listen(band_index: int = 0, region: str = "na") -> dict:
    """Read the S-meter through one full cycle on a band and judge every beacon. ~3 minutes."""
    async with _lock:
        khz = BANDS_KHZ[band_index]
        for r in kiwi.choose(await kiwi.directory(), khz, region):
            try:
                readings = await kiwi.smeter(r, khz, "cw", CYCLE_S + 10)
                results = judge(slot_levels(readings, band_index))
            except FeedError:
                continue
            out = {"khz": khz, "receiver": r.location or r.host, "at": readings[0][0].isoformat(),
                   "beacons": [(h.call, h.where, round(h.db, 1)) for h in results]}
            write_cache(CACHE, out)
            return read_cache(CACHE)
        raise FeedError(f"no receiver on {khz:g} kHz gave a clean listen")


def recent() -> Optional[dict]:
    cache = read_cache(CACHE)
    if not cache.get("beacons"):
        return None
    return cache
