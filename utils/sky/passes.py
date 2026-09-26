"""Where things are in *your* sky: ISS passes, the moon, the planets.

Computed locally with Skyfield from CelesTrak's orbit for the ISS and JPL's
DE421 ephemeris for the moon and planets (fetched once into assets/skyfield/).
It needs an observer: `sky.location` in config, "lat, lon" — a city is
plenty. Nothing here guesses where anyone lives; without it these answers
say how to set one.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils.infrastructure.system.yaml_config import config
from utils.radio.fetch import FeedError, get_json, is_stale, read_cache, write_cache

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "assets" / "skyfield"
TLE_CACHE = "sky_iss_orbit"
TLE_MAX_AGE_S = 12 * 3600


@dataclass
class Observer:
    lat: float
    lon: float


def observer() -> Optional[Observer]:
    raw = config.get("sky.location", None)
    if not raw:
        return None
    try:
        lat, lon = (float(v) for v in str(raw).replace(" ", "").split(",")[:2])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return Observer(lat, lon)


def _loader():
    from skyfield.api import Loader
    DATA.mkdir(parents=True, exist_ok=True)
    return Loader(str(DATA), verbose=False)


async def _iss_elements() -> dict:
    cache = read_cache(TLE_CACHE)
    if cache.get("data") and not is_stale(cache, TLE_MAX_AGE_S):
        return cache["data"]
    d = await get_json("https://celestrak.org/NORAD/elements/gp.php", {"CATNR": "25544", "FORMAT": "json"})
    if not isinstance(d, list) or not d or "MEAN_MOTION" not in d[0]:
        raise FeedError("CelesTrak no longer answers in the expected shape")
    write_cache(TLE_CACHE, {"data": d[0]})
    return d[0]


@dataclass
class Pass:
    rise: datetime
    peak: datetime
    set: datetime
    max_alt: float
    visible: bool          # sunlit station, dark sky

    @property
    def duration_min(self) -> float:
        return (self.set - self.rise).total_seconds() / 60


def _passes(elements: dict, here: Observer, days: float) -> list[Pass]:
    from skyfield.api import EarthSatellite, wgs84
    load = _loader()
    ts = load.timescale()
    eph = load("de421.bsp")
    sat = EarthSatellite.from_omm(ts, elements)
    place = wgs84.latlon(here.lat, here.lon)
    t0 = ts.now()
    t1 = ts.tt_jd(t0.tt + days)
    times, events = sat.find_events(place, t0, t1, altitude_degrees=10.0)
    out, cur = [], {}
    for t, e in zip(times, events):
        if e == 0:
            cur = {"rise": t}
        elif e == 1 and "rise" in cur:
            cur["peak"] = t
        elif e == 2 and "peak" in cur:
            peak = cur["peak"]
            alt = (sat - place).at(peak).altaz()[0].degrees
            sunlit = sat.at(peak).is_sunlit(eph)
            sun_alt = (eph["earth"] + place).at(peak).observe(eph["sun"]).apparent().altaz()[0].degrees
            out.append(Pass(cur["rise"].utc_datetime(), peak.utc_datetime(), t.utc_datetime(), alt,
                            bool(sunlit) and sun_alt < -6))
            cur = {}
    return out


async def next_visible_pass(here: Observer, days: float = 5) -> Optional[Pass]:
    elements = await _iss_elements()
    passes = await asyncio.to_thread(_passes, elements, here, days)
    return next((p for p in passes if p.visible), None)


def local(dt: datetime) -> datetime:
    return dt.astimezone()


def describe(p: Pass) -> str:
    when = local(p.rise)
    return (f"**{when:%a %d %b, %H:%M}** local — up to {p.max_alt:.0f}° high, "
            f"{p.duration_min:.0f} min across the sky")


# ── tonight ────────────────────────────────────────────────────────────────

PLANETS = ("mercury", "venus", "mars", "jupiter barycenter", "saturn barycenter")
SHOWERS = [  # name, peak (month, day), active window (days either side), ZHR
    ("Quadrantids", (1, 3), 3, 110), ("Lyrids", (4, 22), 4, 18), ("Eta Aquariids", (5, 6), 6, 50),
    ("Perseids", (8, 12), 10, 100), ("Draconids", (10, 8), 2, 10), ("Orionids", (10, 21), 6, 20),
    ("Leonids", (11, 17), 3, 15), ("Geminids", (12, 14), 4, 150), ("Ursids", (12, 22), 2, 10),
]


def _tonight(here: Observer) -> dict:
    from skyfield import almanac
    from skyfield.api import wgs84
    load = _loader()
    ts = load.timescale()
    eph = load("de421.bsp")
    place = wgs84.latlon(here.lat, here.lon)
    now = ts.now()
    earth = eph["earth"] + place
    phase = almanac.moon_phase(eph, now).degrees
    illum = almanac.fraction_illuminated(eph, "moon", now)
    t0, t1 = now, ts.tt_jd(now.tt + 1)
    f = almanac.risings_and_settings(eph, eph["moon"], place)
    times, ups = almanac.find_discrete(t0, t1, f)
    moon_events = [("rises" if u else "sets", t.utc_datetime()) for t, u in zip(times, ups)]
    # Planets: above 10° at some point in the next 24 h while the sky is dark.
    visible = []
    for name in PLANETS:
        best = -90.0
        for h in range(0, 24, 1):
            t = ts.tt_jd(now.tt + h / 24)
            sun_alt = earth.at(t).observe(eph["sun"]).apparent().altaz()[0].degrees
            if sun_alt > -12:
                continue
            alt = earth.at(t).observe(eph[name]).apparent().altaz()[0].degrees
            best = max(best, alt)
        if best > 10:
            visible.append((name.replace(" barycenter", "").title(), round(best)))
    today = datetime.now(timezone.utc)
    showers = []
    for name, (m, d), window, zhr in SHOWERS:
        # The nearest year's peak: the Quadrantids peak on 3 Jan and are
        # already active on 31 Dec, which this year's peak put 362 days away.
        peaks = [today.replace(year=today.year + k, month=m, day=d, hour=0, minute=0, second=0, microsecond=0)
                 for k in (-1, 0, 1)]
        peak = min(peaks, key=lambda p: abs((today - p).days))
        delta = (today - peak).days
        if abs(delta) <= window:
            showers.append((name, peak, zhr, delta))
    return {"phase_deg": phase, "illumination": float(illum), "moon": moon_events,
            "planets": visible, "showers": showers}


def phase_name(deg: float) -> str:
    names = ["new moon", "waxing crescent", "first quarter", "waxing gibbous",
             "full moon", "waning gibbous", "last quarter", "waning crescent"]
    return names[int(((deg % 360) + 22.5) // 45) % 8]


async def tonight(here: Observer) -> dict:
    return await asyncio.to_thread(_tonight, here)
