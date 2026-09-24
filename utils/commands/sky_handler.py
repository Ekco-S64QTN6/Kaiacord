"""
!iss           — where the space station is, and who is in orbit
!nasa          — NASA's picture of the day, and who the Deep Space Network is talking to now
!earth         — the whole sunlit Earth, from DSCOVR at L1
!spaceweather  — the sun, geomagnetic activity, and how HF radio is holding up
!rocks         — asteroids passing close in the next month
!launch        — the next rockets
!quake         — significant earthquakes in the last day

Every number is computed in Python from the feed (utils/sky/feeds.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from utils.commands import nightshift
from utils.commands.embed_style import COLOR_ERROR, add_field, box, clean
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.radio.fetch import FeedError
from utils.sky import feeds

COLOR_SKY = 0x2E4A7A


def _foot(key: str, source: str) -> str:
    return f"{source}\n{nightshift.others(key)}"


def _map(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.2f}&mlon={lon:.2f}#map=3/{lat:.2f}/{lon:.2f}"


def _latlon(lat: float, lon: float) -> str:
    return f"{abs(lat):.1f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.1f}°{'E' if lon >= 0 else 'W'}"


async def _run(msg, key: str, title: str, build):
    log_action(f"!{key} for {msg.author}")
    if not config.get("sky.enabled", True):
        await msg.channel.send(embed=box(title, "The sky feeds are switched off (`sky.enabled`).", COLOR_ERROR))
        return
    try:
        embed = await build()
        await msg.channel.send(embed=embed)
    except FeedError as e:
        log_warning(f"[sky] {key}: {e}")
        await msg.channel.send(embed=box(title, f"The source didn't answer as expected — {clean(str(e), 200)}",
                                         COLOR_ERROR, footer=nightshift.others(key)))
    except Exception as e:
        log_error(f"[sky] !{key} failed: {e}")
        await msg.channel.send(embed=box(title, "Something went wrong. It's in the log.", COLOR_ERROR))


# ── !iss ───────────────────────────────────────────────────────────────────

async def iss_embed():
    pos = await feeds.iss_position()
    crew = await feeds.people_in_space()
    lat, lon = float(pos["latitude"]), float(pos["longitude"])
    lit = "in sunlight" if pos.get("visibility") == "daylight" else "in Earth's shadow"
    embed = box("🛰️  The International Space Station",
                f"Over **[{_latlon(lat, lon)}]({_map(lat, lon)})**, {float(pos['altitude']):.0f} km up, "
                f"doing {float(pos['velocity']):,.0f} km/h — {lit}. It goes round every ~92 minutes.",
                COLOR_SKY, footer=_foot("iss", "via wheretheiss.at · crew via Launch Library 2"))
    people = crew.get("people") or {}
    total = sum(len(v) for v in people.values())
    if people:
        add_field(embed, f"In orbit right now · {total}", "\n".join(
            f"**{agency}** — {', '.join(names)}" for agency, names in sorted(people.items())))
    if crew.get("other"):
        add_field(embed, "Also up there", "Starman, still driving his Roadster round the sun.")
    from utils.sky import passes
    here = passes.observer()
    if here is None:
        add_field(embed, "Next pass over you", "Set `sky.location` (a city's `lat, lon`) and I'll work it out.")
    else:
        nxt = await passes.next_visible_pass(here)
        add_field(embed, "Next visible pass", passes.describe(nxt) if nxt else "none bright enough in the next few days.")
    return embed


async def handle_iss_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "iss", "🛰️  ISS", iss_embed)


# ── !nasa ──────────────────────────────────────────────────────────────────

def _rate(bps) -> str:
    if not bps:
        return ""
    return f"{bps / 1e6:.1f} Mb/s" if bps >= 1e6 else f"{bps / 1e3:.1f} kb/s" if bps >= 1e3 else f"{bps:.0f} b/s"


async def nasa_embed():
    a = await feeds.apod()
    links = await feeds.dsn()
    embed = box(f"🔭  {clean(a.get('title', 'Astronomy Picture of the Day'), 200)}",
                clean(a.get("explanation", ""), 700), COLOR_SKY,
                footer=_foot("nasa", f"APOD {a.get('date', '')}" + (f" · © {clean(a['copyright'], 60)}" if a.get("copyright") else "")
                             + " · DSN Now via eyes.nasa.gov"))
    if a.get("media_type") == "image" and a.get("url"):
        embed.set_image(url=a["url"])
    elif a.get("url"):
        add_field(embed, "Today it's a video", a["url"])
    if links:
        seen, lines = set(), []
        for l in sorted(links, key=lambda l: -(l.range_km or 0)):
            if l.spacecraft in seen:
                continue
            seen.add(l.spacecraft)
            bits = [f"**{clean(l.name, 50)}**", f"{l.station} {l.dish}"]
            if l.light_time:
                bits.append(l.light_time + " away")
            if l.down_bps:
                bits.append(_rate(l.down_bps))
            lines.append(" · ".join(bits))
        add_field(embed, "The Deep Space Network, right now", "\n".join(lines[:10]))
    return embed


async def handle_nasa_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "nasa", "🔭  NASA", nasa_embed)


async def earth_embed():
    item = await feeds.epic_latest()
    lat = item.get("centroid_coordinates", {}).get("lat")
    lon = item.get("centroid_coordinates", {}).get("lon")
    centre = f" Centred on {_latlon(lat, lon)}." if lat is not None else ""
    embed = box("🌍  Earth, whole", f"From DSCOVR's EPIC camera at L1, about 1.5 million km sunward, "
                f"{item.get('date', '')} UTC.{centre}", COLOR_SKY,
                footer=_foot("earth", "NASA EPIC"))
    embed.set_image(url=feeds.epic_image_url(item))
    return embed


async def handle_earth_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "earth", "🌍  Earth", earth_embed)


# ── !spaceweather ──────────────────────────────────────────────────────────

async def spaceweather_embed():
    w = await feeds.space_weather()
    flare = w.get("flare") or {}
    lines = [f"**Kp {w['kp']:.1f}** — {feeds.kp_words(w['kp'])}",
             f"Solar flux **{w.get('solar_flux') or '?'}**, sunspots **{w.get('sunspots') or '?'}**, X-ray **{w.get('xray') or '?'}**"]
    if flare.get("max_class"):
        lines.append(f"Latest flare: **{flare['max_class']}** peaking {flare.get('max_time', '')[:16].replace('T', ' ')}Z")
    embed = box("☀️  Space weather", "\n".join(lines), COLOR_SKY,
                footer=_foot("spaceweather", "NOAA SWPC · band estimates via HamQSL"))
    bands = w.get("bands") or {}
    if bands:
        day = [f"{k.rsplit(' ', 1)[0]} {v}" for k, v in bands.items() if k.endswith("day")]
        night = [f"{k.rsplit(' ', 1)[0]} {v}" for k, v in bands.items() if k.endswith("night")]
        add_field(embed, "HF by day", " · ".join(day), inline=True)
        add_field(embed, "HF by night", " · ".join(night), inline=True)
    if w.get("noise"):
        add_field(embed, "Noise floor", w["noise"], inline=True)
    return embed


async def handle_spaceweather_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "spaceweather", "☀️  Space weather", spaceweather_embed)


# ── !rocks, !launch, !quake ────────────────────────────────────────────────

async def rocks_embed():
    rows = await feeds.close_approaches()
    if not rows:
        return box("☄️  Close approaches", "Nothing inside 0.05 AU in the next 30 days.", COLOR_SKY,
                   footer=_foot("rocks", "JPL SBDB close-approach data"))
    lines = []
    for r in rows[:10]:
        inside = " — **closer than the Moon**" if r["ld"] < 1 else ""
        size = feeds.size_from_h(r["h"])
        lines.append(f"`{r['name']}` · {r['when']} UTC · {r['ld']:.1f} lunar distances"
                     f"{f' · {size}' if size else ''} · {r['km_s']:.1f} km/s{inside}")
    return box("☄️  Close approaches — next 30 days", "\n".join(lines), COLOR_SKY,
               footer=_foot("rocks", "JPL SBDB · sizes estimated from brightness"))


async def handle_rocks_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "rocks", "☄️  Asteroids", rocks_embed)


def _countdown(when: datetime) -> str:
    secs = (when - datetime.now(timezone.utc)).total_seconds()
    if secs < 0:
        return "any moment"
    h, m = int(secs // 3600), int(secs % 3600 // 60)
    return f"in {h // 24}d {h % 24}h" if h >= 24 else f"in {h}h {m:02d}m"


async def launch_embed():
    rows = await feeds.launches()
    lines = [f"**{clean(r['name'], 80)}** · {r['net']:%d %b %H:%M}Z ({_countdown(r['net'])}) · "
             f"{clean(r['where'], 60)}{' · ' + r['status'] if r['status'] and r['status'] != 'Go' else ''}"
             for r in rows]
    return box("🚀  Next launches", "\n".join(lines) or "Nothing scheduled.", COLOR_SKY,
               footer=_foot("launch", "via Launch Library 2 (The Space Devs)"))


async def handle_launch_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "launch", "🚀  Launches", launch_embed)


async def quake_embed():
    rows = await feeds.quakes()
    lines = []
    for q in rows:
        flags = (" · 🌊 tsunami possible" if q["tsunami"] else "") + (f" · alert {q['alert']}" if q["alert"] else "")
        lines.append(f"**M{q['mag']:.1f}** · [{clean(q['place'], 70)}]({q['url']}) · {q['when']:%d %b %H:%M}Z · "
                     f"{q['depth_km']:.0f} km deep{flags}")
    return box("🌐  Earthquakes, magnitude 4.5+, last 24 hours", "\n".join(lines) or "None above 4.5 today.",
               COLOR_SKY, footer=_foot("quake", "via USGS"))


async def handle_quake_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "quake", "🌐  Earthquakes", quake_embed)


# ── !sky ───────────────────────────────────────────────────────────────────

async def sky_embed():
    from utils.sky import passes
    here = passes.observer()
    if here is None:
        return box("🌌  Tonight", "I need to know roughly where you are: set `sky.location` to a city's "
                   "`lat, lon` in `config/kaia.yaml` (e.g. London is `51.5, -0.1`).", COLOR_SKY,
                   footer=nightshift.others("sky"))
    t = await passes.tonight(here)
    moon = f"**{passes.phase_name(t['phase_deg']).capitalize()}**, {t['illumination']:.0%} lit"
    moves = [f"{what} {passes.local(when):%H:%M}" for what, when in t["moon"]]
    embed = box("🌌  Tonight overhead", moon + (f" — {', '.join(moves)}" if moves else ""), COLOR_SKY,
                footer=_foot("sky", "computed locally (Skyfield, JPL DE421) · times are local"))
    add_field(embed, "Planets up after dark",
              " · ".join(f"**{n}** (to {a}°)" for n, a in t["planets"]) or "none well placed tonight")
    for name, peak, zhr, delta in t["showers"]:
        when = "peaks tonight" if delta == 0 else (f"peaks in {-delta} days" if delta < 0 else f"peaked {delta} days ago")
        add_field(embed, f"☄️ {name}", f"{when} · up to ~{zhr} an hour at its best, under dark skies", inline=True)
    nxt = await passes.next_visible_pass(here)
    add_field(embed, "Next visible ISS pass", passes.describe(nxt) if nxt else "none bright enough in the next few days.")
    return embed


async def handle_sky_command(ctx, msg, send_kaia_response=None):
    await _run(msg, "sky", "🌌  Tonight", sky_embed)


nightshift.register("iss", "nasa", "earth", "spaceweather", "rocks", "launch", "quake", "sky")
