"""The sky feeds behind !iss, !nasa, !earth, !spaceweather, !rocks, !launch, !quake.

All public; fetched when someone asks and cached per feed (a live position for
seconds, a daily picture for hours), through the same polite fetcher as the
radio feeds. A reply in an unexpected shape raises FeedError — the command
says the source misbehaved rather than showing nothing.

Python does every number here (distances, lunar distances, light-time);
Kaia only ever reports them.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.radio.fetch import FeedError, get_json, is_stale, read_cache, write_cache

AU_KM = 149_597_870.7
LD_KM = 384_400.0            # mean Earth–Moon distance
LIGHT_KM_S = 299_792.458


def nasa_key() -> str:
    return os.getenv("NASA_API_KEY") or "DEMO_KEY"


async def _cached(name: str, max_age_s: float, fetch, force: bool = False) -> dict:
    cache = read_cache(name)
    if not force and "data" in cache and not is_stale(cache, max_age_s):
        return cache
    data = await fetch()
    write_cache(name, {"data": data})
    return read_cache(name)


async def _text(url: str) -> str:
    import aiohttp
    from utils.core.sanitizer import public_only_connector, read_capped
    from utils.radio.fetch import USER_AGENT
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20), headers={"User-Agent": USER_AGENT},
                                         connector=public_only_connector()) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    raise FeedError(f"{url} answered HTTP {r.status}")
                return (await read_capped(r, 2_000_000)).decode("utf-8", "replace")
    except FeedError:
        raise
    except Exception as e:
        raise FeedError(f"{url}: {type(e).__name__}: {e}") from e


def _need(cond: bool, what: str) -> None:
    if not cond:
        raise FeedError(f"{what} no longer answers in the expected shape")


# ── ISS ────────────────────────────────────────────────────────────────────

async def iss_position() -> dict:
    async def f():
        d = await get_json("https://api.wheretheiss.at/v1/satellites/25544")
        _need(isinstance(d, dict) and "latitude" in d, "wheretheiss.at")
        return d
    return (await _cached("sky_iss", 30, f))["data"]


async def people_in_space() -> dict:
    """Who is in orbit, by agency. open-notify's astros.json looks like the
    obvious source and is not: its crew list stopped being updated in 2024.
    Launch Library 2 is current. It also lists Starman — the mannequin in the
    Tesla Roadster SpaceX launched in 2018 — who is kept apart from the humans."""
    async def f():
        d = await get_json("https://ll.thespacedevs.com/2.2.0/astronaut/", {"in_space": "true", "limit": "50", "mode": "list"})
        _need(isinstance(d, dict) and isinstance(d.get("results"), list), "Launch Library 2 astronauts")
        people, other = {}, []
        for a in d["results"]:
            agency = a.get("agency")
            agency = agency.get("abbrev") or agency.get("name") if isinstance(agency, dict) else (agency or "?")
            if (a.get("name") or "").lower() == "starman":
                other.append(a["name"])
                continue
            people.setdefault(agency, []).append(a.get("name", "?"))
        return {"people": people, "other": other}
    return (await _cached("sky_astros", 6 * 3600, f))["data"]


# ── NASA ───────────────────────────────────────────────────────────────────

async def apod() -> dict:
    async def f():
        d = await get_json(f"https://api.nasa.gov/planetary/apod?api_key={nasa_key()}")
        _need(isinstance(d, dict) and "title" in d, "NASA APOD")
        return d
    return (await _cached("sky_apod", 6 * 3600, f))["data"]


@dataclass
class DSNLink:
    station: str
    dish: str
    spacecraft: str
    name: str
    range_km: Optional[float]
    rtlt_s: Optional[float]
    down_bps: Optional[float]
    band: str

    @property
    def light_time(self) -> str:
        if not self.range_km or self.range_km <= 0:
            return ""
        s = self.range_km / LIGHT_KM_S
        if s < 60:
            return f"{s:.1f} light-seconds"
        if s < 3600:
            return f"{s / 60:.1f} light-minutes"
        return f"{s / 3600:.1f} light-hours"


def parse_dsn(xml_text: str, names: dict[str, str]) -> list[DSNLink]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise FeedError("DSN Now did not return XML") from e
    links, station = [], ""
    for el in root:
        if el.tag == "station":
            station = el.get("friendlyName") or el.get("name", "")
        elif el.tag == "dish":
            for tgt in el.findall("target"):
                code = (tgt.get("name") or "").upper()
                if not code or code in ("DSN", "TEST", "DSS"):
                    continue
                downs = [d for d in el.findall("downSignal") if (d.get("spacecraft") or "").upper() == code]
                rate = max((float(d.get("dataRate") or 0) for d in downs if d.get("active") == "true"), default=None)
                band = next((d.get("band", "") for d in downs if d.get("active") == "true"), "")
                rng = float(tgt.get("downlegRange") or -1)
                links.append(DSNLink(station=station, dish=el.get("name", ""), spacecraft=code,
                                     name=names.get(code.lower(), code), range_km=rng if rng > 0 else None,
                                     rtlt_s=float(tgt.get("rtlt") or -1), down_bps=rate, band=band))
    return links


async def dsn() -> list[DSNLink]:
    async def names():
        text = await _text("https://eyes.nasa.gov/dsn/config.xml")
        return {m.group(1).lower(): m.group(2)
                for m in re.finditer(r'<spacecraft name="([^"]+)"[^>]*friendlyName="([^"]+)"', text)}
    async def now():
        return await _text("https://eyes.nasa.gov/dsn/data/dsn.xml")
    lookup = (await _cached("sky_dsn_names", 7 * 86400, names))["data"]
    return parse_dsn((await _cached("sky_dsn", 300, now))["data"], lookup)


async def epic_latest() -> dict:
    async def f():
        d = await get_json(f"https://api.nasa.gov/EPIC/api/natural?api_key={nasa_key()}")
        _need(isinstance(d, list) and d and "image" in d[0], "NASA EPIC")
        return d[-1]
    return (await _cached("sky_epic", 6 * 3600, f))["data"]


def epic_image_url(item: dict) -> str:
    when = datetime.strptime(item["date"], "%Y-%m-%d %H:%M:%S")
    return f"https://epic.gsfc.nasa.gov/archive/natural/{when:%Y/%m/%d}/jpg/{item['image']}.jpg"


# ── space weather ──────────────────────────────────────────────────────────

async def space_weather() -> dict:
    async def f():
        kp = await get_json("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
        flares = await get_json("https://services.swpc.noaa.gov/json/goes/primary/xray-flares-latest.json")
        _need(isinstance(kp, list) and kp, "NOAA SWPC Kp")
        latest_kp = kp[-1] if isinstance(kp[-1], dict) else dict(zip(kp[0], kp[-1]))
        solar = await _text("https://www.hamqsl.com/solarxml.php")
        def tag(t):
            m = re.search(rf"<{t}>\s*([^<]*)", solar)
            return m.group(1).strip() if m else ""
        bands = {f"{m.group(1)} {m.group(2)}": m.group(3).strip()
                 for m in re.finditer(r'<band name="([^"]+)" time="([^"]+)">([^<]+)', solar)}
        return {"kp": float(latest_kp.get("Kp") or latest_kp.get("kp_index") or 0),
                "kp_time": latest_kp.get("time_tag", ""),
                "flare": flares[0] if isinstance(flares, list) and flares else {},
                "solar_flux": tag("solarflux"), "sunspots": tag("sunspots"), "xray": tag("xray"),
                "noise": tag("signalnoise"), "bands": bands}
    return (await _cached("sky_swpc", 3600, f))["data"]


def kp_words(kp: float) -> str:
    if kp >= 7:
        return "a severe geomagnetic storm"
    if kp >= 5:
        return "a geomagnetic storm — aurora well south of usual"
    if kp >= 4:
        return "unsettled — aurora possible at high latitudes"
    return "quiet"


# ── asteroids, launches, earthquakes ────────────────────────────────────────

async def close_approaches(days: int = 30, max_au: float = 0.05) -> list[dict]:
    async def f():
        d = await get_json("https://ssd-api.jpl.nasa.gov/cad.api",
                           {"dist-max": str(max_au), "date-min": "now", "date-max": f"+{days}", "sort": "dist"})
        _need(isinstance(d, dict) and "fields" in d, "JPL close-approach API")
        rows = [dict(zip(d["fields"], r)) for r in d.get("data") or []]
        return rows
    rows = (await _cached("sky_cad", 6 * 3600, f))["data"]
    out = []
    for r in rows:
        au = float(r["dist"])
        out.append({"name": r["des"], "when": r["cd"], "au": au, "ld": au * AU_KM / LD_KM,
                    "km_s": float(r.get("v_rel") or 0), "h": r.get("h")})
    return out


def size_from_h(h) -> str:
    """Rough diameter from absolute magnitude, assuming albedo 0.14."""
    try:
        d_km = 1329 / (0.14 ** 0.5) * 10 ** (-float(h) / 5)
    except (TypeError, ValueError):
        return ""
    return f"~{d_km * 1000:.0f} m" if d_km < 1 else f"~{d_km:.1f} km"


async def launches(n: int = 5) -> list[dict]:
    async def f():
        d = await get_json("https://ll.thespacedevs.com/2.2.0/launch/upcoming/", {"limit": "12", "mode": "list"})
        _need(isinstance(d, dict) and isinstance(d.get("results"), list), "Launch Library 2")
        return d["results"]
    rows = (await _cached("sky_launches", 3600, f))["data"]
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        try:
            net = datetime.fromisoformat(r["net"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        status = (r.get("status") or {}).get("abbrev", "")
        if net < now - timedelta(hours=1) or status in ("Success", "Failure", "Partial Failure"):
            continue
        out.append({"name": r.get("name", "?"), "net": net, "status": status,
                    "where": r.get("location") or r.get("pad") or "", "provider": r.get("lsp_name", "")})
    return out[:n]


async def quakes(n: int = 8) -> list[dict]:
    async def f():
        d = await get_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
        _need(isinstance(d, dict) and isinstance(d.get("features"), list), "USGS")
        return d["features"]
    feats = (await _cached("sky_quakes", 1800, f))["data"]
    out = []
    for ft in feats:
        p, g = ft.get("properties") or {}, (ft.get("geometry") or {}).get("coordinates") or [None, None, None]
        out.append({"mag": p.get("mag"), "place": p.get("place", ""), "when": datetime.fromtimestamp(p["time"] / 1000, timezone.utc),
                    "depth_km": g[2], "tsunami": bool(p.get("tsunami")), "url": p.get("url", ""), "alert": p.get("alert")})
    out.sort(key=lambda q: q["mag"] or 0, reverse=True)
    return out[:n]
