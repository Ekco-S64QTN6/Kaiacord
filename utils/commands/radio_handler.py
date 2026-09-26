"""
!skyking            — the latest Emergency Action Messages from the HFGCS net (eam.watch)
!skyking N          — message N in full: preamble, body, repeats, recording
!skyking classic    — a message from the Skyking archive, read the way it sounded
!numbers [station]  — number stations on the air in the next few hours (Priyom)
!radio …            — what Kaia has heard, and live listening in voice (KiwiSDR)

Skyking itself is defunct; the command is named for it as an homage, and shows
what the net sends now. Feeds are read from the on-disk cache the radio task
refreshes every few hours; a command only fetches when there is no cache yet.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from utils.commands.embed_style import COLOR_ERROR, add_field, box, clean, clean_block
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.radio import eam_watch, priyom
from utils.radio.fetch import FeedError

COLOR_RADIO = 0x3B8B5A
DEFAULT_POLL_HOURS = 6

from utils.commands import nightshift

_SUB_HINTS = {
    "skyking": "!skyking <n> · !skyking classic",
    "detail": "!skyking — the list · !skyking classic",
    "classic": "!skyking — the latest",
}


def _others(key: str, *_ignored: str) -> str:
    """Footer: this command's own variants, if any, then the pointer to !nightshift."""
    main = "skyking" if key in ("detail", "classic") else key
    hint = _SUB_HINTS.get(key)
    rest = nightshift.others(main)
    return f"{hint} · {rest}" if hint else rest


def poll_seconds() -> float:
    return float(config.get("radio.poll_hours", DEFAULT_POLL_HOURS)) * 3600


def radio_enabled() -> bool:
    return bool(config.get("radio.enabled", True))


def _when(dt: datetime | None) -> str:
    return f"{dt:%d %b %H:%M}Z" if dt else "time unknown"


def _age(cache: dict) -> str:
    fetched = cache.get("fetched_at")
    if not fetched:
        return ""
    hours = (time.time() - float(fetched)) / 3600
    return "checked just now" if hours < 0.1 else f"checked {hours:.0f}h ago" if hours >= 1 else f"checked {hours * 60:.0f}m ago"


def _message_line(i: int, m: eam_watch.Message) -> str:
    code = f"`{m.preamble} {m.body}`" if m.preamble else f"`{m.body}`"
    audio = " 🔊" if m.recordings else ""
    return f"**{i}** · {_when(m.time)} · **{clean(m.sender, 40)}** {code}{audio}"


def overview_embed(msgs: list[eam_watch.Message], cache: dict):
    eams = eam_watch.latest_eams(msgs)
    embed = box("📻  Emergency Action Messages",
                f"*{eam_watch.observation(msgs)}*" if eams else "No EAMs in the latest log page.",
                COLOR_RADIO,
                footer=f"HFGCS · 8992 / 11175 kHz USB · via eam.watch · {_age(cache)}\n"
                       f"{_others('skyking')}")
    if eams:
        add_field(embed, "Latest", "\n".join(_message_line(i, m) for i, m in enumerate(eams, 1)))
    other = eam_watch.net_traffic(msgs)
    if other:
        add_field(embed, "Also on the net", "\n".join(
            f"• {_when(m.time)} · **{clean(m.sender, 40)}** {m.label}" for m in other))
    add_field(embed, "", "*encrypted — nobody outside the chain of command can read these.*")
    return embed


def detail_embed(msgs: list[eam_watch.Message], number: int):
    eams = eam_watch.latest_eams(msgs)
    if not 1 <= number <= len(eams):
        return box("📻  Emergency Action Messages",
                   f"There are {len(eams)} in the list — pick one from `!skyking`.", COLOR_ERROR)
    m = eams[number - 1]
    embed = box(f"📻  EAM from {clean(m.sender, 60)}", f"`{m.text}`", COLOR_RADIO,
                footer=f"via eam.watch · {m.url}\n{_others('detail')}")
    add_field(embed, "Heard", _when(m.time), inline=True)
    if m.preamble:
        add_field(embed, "Preamble", f"`{m.preamble}`", inline=True)
    add_field(embed, "Length", f"{len(m.body)} characters", inline=True)
    if m.repeats:
        add_field(embed, "Repeats", str(m.repeats), inline=True)
    if m.comments:
        add_field(embed, "Comments", f"{m.comments} on eam.watch", inline=True)
    if m.recordings:
        add_field(embed, "Recording", "\n".join(f"[listen]({u})" for u in m.recordings[:3]))
    return embed


def classic_embed(m: eam_watch.Message):
    embed = box("📻  Skyking, from the archive",
                f"*{clean(eam_watch.skyking_broadcast(m), 400)}*", COLOR_RADIO,
                footer=f"{_when(m.time)} · {m.sender} · Skyking broadcasts are no longer heard · via eam.watch\n"
                       f"{_others('classic', 'detail')}")
    if m.recordings:
        add_field(embed, "Recording", f"[listen]({m.recordings[0]})")
    return embed


def numbers_embed(items: list[priyom.Transmission], cache: dict, hours: float, station: str | None):
    title = f"🔢  Number stations — next {hours:g} hours (UTC)" if not station else f"🔢  {station.upper()} — next {hours:g} hours"
    if not items:
        return box(title, "Nothing on Priyom's schedule in that window." if not station
                   else f"No {station.upper()} transmissions scheduled in that window.",
                   COLOR_RADIO, footer=f"via priyom.org · {_age(cache)}\n{_others('numbers', 'detail')}")
    lines = []
    for t in items[:15]:
        freq = f"{t.khz:g} kHz {t.mode}".strip() if t.khz else (t.note or "search")
        family = f" · {t.family}" if t.family else ""
        link = f" · [listen]({t.listen_url})" if t.listen_url else ""
        lines.append(f"`{t.start:%H:%M}` **{t.station}** {freq}{family}{link}")
    return box(title, "\n".join(lines), COLOR_RADIO,
               footer=f"schedule via priyom.org · listen links open the UTwente WebSDR tuned · {_age(cache)}\n"
                      f"{_others('numbers', 'detail')}")


async def _eam_cache():
    return await eam_watch.refresh(poll_seconds())


async def handle_skyking_command(ctx, msg, send_kaia_response=None):
    parts = msg.content.strip().split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    log_action(f"!skyking {arg} for {msg.author}")
    if not radio_enabled():
        await msg.channel.send(embed=box("📻  Skyking", "The radio feeds are switched off (`radio.enabled`).", COLOR_ERROR))
        return
    try:
        if arg in ("classic", "archive", "old"):
            await msg.channel.send(embed=classic_embed(await eam_watch.classic()))
            return
        cache = await _eam_cache()
        msgs = eam_watch.messages(cache)
        if arg.isdigit():
            await msg.channel.send(embed=detail_embed(msgs, int(arg)))
        else:
            await msg.channel.send(embed=overview_embed(msgs, cache))
    except FeedError as e:
        log_warning(f"[radio] eam.watch: {e}")
        await msg.channel.send(embed=box("📻  Skyking", f"eam.watch didn't answer as expected — {clean(str(e), 200)}",
                                         COLOR_ERROR))
    except Exception as e:
        log_error(f"[radio] !skyking failed: {e}")
        await msg.channel.send(embed=box("📻  Skyking", "Something went wrong reading the net. It's in the log.", COLOR_ERROR))


async def handle_numbers_command(ctx, msg, send_kaia_response=None):
    parts = msg.content.strip().split()
    station, hours = None, 6.0
    for p in parts[1:]:
        if p.rstrip("h").replace(".", "", 1).isdigit():
            hours = max(1.0, min(24.0, float(p.rstrip("h"))))
        else:
            station = p
    log_action(f"!numbers {station or ''} {hours:g}h for {msg.author}")
    if not radio_enabled():
        await msg.channel.send(embed=box("🔢  Numbers", "The radio feeds are switched off (`radio.enabled`).", COLOR_ERROR))
        return
    try:
        cache = await priyom.refresh(poll_seconds())
        items = priyom.upcoming(cache, hours if not station else 24, station=station)
        await msg.channel.send(embed=numbers_embed(items, cache, hours if not station else 24, station))
    except FeedError as e:
        log_warning(f"[radio] priyom: {e}")
        await msg.channel.send(embed=box("🔢  Numbers", f"Priyom didn't answer as expected — {clean(str(e), 200)}", COLOR_ERROR))
    except Exception as e:
        log_error(f"[radio] !numbers failed: {e}")
        await msg.channel.send(embed=box("🔢  Numbers", "Something went wrong reading the schedule. It's in the log.", COLOR_ERROR))


# ── !radio ──────────────────────────────────────────────────────────────────

LIVE_PRESETS = {
    "buzzer": (4625.0, "usb", "eu", "UVB-76"),
    "uvb76": (4625.0, "usb", "eu", "UVB-76"),
    "4625": (4625.0, "usb", "eu", "UVB-76"),
    "hfgcs": (8992.0, "usb", "na", "HFGCS"),
    "8992": (8992.0, "usb", "na", "HFGCS"),
    "11175": (11175.0, "usb", "na", "HFGCS"),
}


MODES = ("usb", "lsb", "am", "amn", "cw", "cwn", "nbfm")
RADIO_USAGE = ("`!radio hfgcs` · `!radio buzzer` · `!radio <kHz> [usb|lsb|am|cw]` · "
               "`!radio <station>` for a number station on `!numbers` · `!radio log` · `!radio listen` · `!radio off`")


def _transcript(e: dict) -> str:
    """Entries logged before number stations stopped being transcribed carry
    Whisper's loops; those are not shown."""
    return "" if e.get("kind") == "numbers" else (e.get("transcript") or "")


def _entry_line(i: int, e: dict) -> str:
    when = datetime.fromisoformat(e["started"])
    parsed = e.get("parsed") or {}
    what = (f"`{parsed['message']}`" if parsed.get("message")
            else clean(_transcript(e), 90) if _transcript(e) else f"recorded {e['seconds'] / 60:.0f} min")
    who = parsed.get("callsign") or e.get("station", "")
    check = e.get("check")
    mark = f" · ✔ {check['accuracy']:.0%}" if check else ""
    return f"**{i}** · {when:%d %b %H:%M}Z · {e['khz']:g} kHz · **{clean(who, 30)}** {what}{mark}"


def status_embed(entries: list[dict]):
    from utils.radio import kiwi, transcribe, watch
    from utils.radio import priyom as pr
    lines = []
    windows = config.get("radio.hfgcs_windows_utc", watch.DEFAULT_WINDOWS)
    now = datetime.now(timezone.utc)
    upcoming = sorted(
        (now.replace(hour=int(w.split(":")[0]), minute=int(w.split(":")[1]), second=0, microsecond=0)
         for w in windows), key=lambda t: (t < now, t))
    if upcoming:
        lines.append(f"Next HFGCS watch: **{upcoming[0]:%H:%M}Z** on 8992 kHz")
    follow = config.get("radio.follow", watch.DEFAULT_FOLLOW)
    nxt = [t for t in pr.upcoming(read_cache_safe(pr.CACHE), 24)
           if t.station.upper() in {f.upper() for f in follow} and t.khz]
    if nxt:
        lines.append(f"Next {nxt[0].station}: **{nxt[0].start:%H:%M}Z** on {nxt[0].khz:g} kHz")
    missing = []
    if not kiwi.available():
        missing.append("kiwiclient")
    if not transcribe.available():
        missing.append("faster-whisper")
    if missing:
        lines.append(f"⚠️ not installed: {', '.join(missing)} — `tools/maintenance/fetch_radio_assets.py`")
    embed = box("📡  What Kaia has heard", "\n".join(lines), COLOR_RADIO,
                footer=f"receivers: the public KiwiSDR network · !radio log <n> · !radio listen\n{_others('radio')}")
    if entries:
        add_field(embed, "Latest", "\n".join(_entry_line(i, e) for i, e in enumerate(entries[:6], 1)))
        checks = [e["check"]["accuracy"] for e in entries if e.get("check")]
        if checks:
            add_field(embed, "Against eam.watch's copies",
                      f"{len(checks)} checked · {sum(checks) / len(checks):.0%} of characters right on average")
    else:
        add_field(embed, "Latest", "Nothing yet — the first scheduled watch will fill this in.")
    return embed


def read_cache_safe(name):
    from utils.radio.fetch import read_cache
    return read_cache(name)


def entry_embed(e: dict):
    parsed = e.get("parsed") or {}
    title = f"📡  {e['station']} · {e['khz']:g} kHz {e['mode'].upper()}"
    desc = f"`{parsed['message']}`" if parsed.get("message") else clean(_transcript(e), 1500)
    if not desc:
        desc = (f"I recorded {e['seconds'] / 60:.0f} minutes of {e['station']} — the clip is attached. "
                "Number stations read digit groups through HF fading, and I can't transcribe that "
                "reliably, so I don't try." if e.get("kind") == "numbers" else "(no transcript)")
    embed = box(title, desc, COLOR_RADIO,
                footer=f"via {e.get('receiver_location') or e['receiver']} (KiwiSDR) · `?` = not sure\n{_others('radio')}")
    add_field(embed, "Heard", f"{datetime.fromisoformat(e['started']):%d %b %H:%M}Z", inline=True)
    add_field(embed, "Length", f"{e['seconds']:.0f} s", inline=True)
    if parsed.get("callsign"):
        add_field(embed, "Callsign", parsed["callsign"], inline=True)
    if parsed.get("preamble"):
        add_field(embed, "Preamble", f"`{parsed['preamble']}`", inline=True)
    check = e.get("check")
    if check:
        add_field(embed, "eam.watch's copy", f"`{check['truth']}` — {check['accuracy']:.0%} match")
    if parsed.get("message") and e.get("transcript"):
        add_field(embed, "What I heard", clean(e["transcript"], 900))
    return embed


def clip_file(e: dict):
    import discord
    from utils.radio import log as radio_log
    path = radio_log.clips_dir() / e.get("clip", "")
    return discord.File(str(path), filename=path.name) if e.get("clip") and path.is_file() else None


async def post_entry(bot, e: dict) -> bool:
    """Post a catch to the review channel (radio.post_channel, #kaia-opolis)."""
    import discord
    if not config.get("radio.post_clips", True):
        return False
    name = config.get("radio.post_channel", "kaia-opolis")
    channel = discord.utils.get(bot.get_all_channels(), name=name)
    if channel is None:
        log_warning(f"[radio] #{name} not found; not posting {e['id']}")
        return False
    f = clip_file(e)
    await channel.send(embed=entry_embed(e), **({"file": f} if f else {}))
    return True


async def handle_radio_command(ctx, msg, send_kaia_response=None):
    from utils.radio import kiwi, live, log as radio_log, watch
    parts = msg.content.strip().split()
    verb = parts[1].lower() if len(parts) > 1 else "status"
    log_action(f"!radio {' '.join(parts[1:])} for {msg.author}")
    if not radio_enabled():
        await msg.channel.send(embed=box("📡  Radio", "The radio feeds are switched off (`radio.enabled`).", COLOR_ERROR))
        return
    try:
        if verb in ("status", "heard"):
            await msg.channel.send(embed=status_embed(radio_log.entries()))
            return
        if verb == "log":
            entries = radio_log.entries()
            if len(parts) > 2 and parts[2].isdigit():
                n = int(parts[2])
                if not 1 <= n <= len(entries):
                    await msg.channel.send(embed=box("📡  Radio", f"There are {len(entries)} in the log.", COLOR_ERROR))
                    return
                e = entries[n - 1]
                f = clip_file(e)
                await msg.channel.send(embed=entry_embed(e), **({"file": f} if f else {}))
                return
            embed = box("📡  Radio log", "\n".join(_entry_line(i, e) for i, e in enumerate(entries[:12], 1))
                        or "Nothing recorded yet.", COLOR_RADIO,
                        footer=f"!radio log <n> — one in full, with the recording\n{_others('radio')}")
            await msg.channel.send(embed=embed)
            return
        if verb == "off":
            stopped = msg.guild and await live.stop(msg.guild.id)
            await msg.channel.send(embed=box("📡  Radio", "off the air." if stopped else "nothing was playing.", COLOR_RADIO))
            return
        if verb == "listen":
            if not kiwi.available():
                await msg.channel.send(embed=box("📡  Radio", "kiwiclient isn't installed — "
                                                 "`tools/maintenance/fetch_radio_assets.py`.", COLOR_ERROR))
                return
            minutes = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
            minutes = max(2, min(30, minutes))
            job = {"key": f"manual:{datetime.now(timezone.utc):%Y%m%dT%H%M}", "kind": "hfgcs", "station": "HFGCS",
                   "khz": watch.HFGCS_KHZ, "mode": "usb", "seconds": minutes * 60, "region": "na",
                   "squelch": watch.SQUELCH_DB}
            bot = getattr(ctx, "bot", None)
            import asyncio
            from utils.infrastructure.monitoring.async_task_registry import task_registry
            task_registry.register(f"radio_listen_{int(time.time())}", asyncio.create_task(
                watch.run_job(job, (lambda e: post_entry(bot, e)) if bot else None)))
            await msg.channel.send(embed=box("📡  Listening", f"on 8992 kHz for {minutes} minutes. Anything that "
                                             "sounds like an EAM goes to the log and #kaia-opolis.", COLOR_RADIO,
                                             footer=_others('radio')))
            return

        # Live: a preset, a station, or a frequency in kHz.
        if verb in LIVE_PRESETS:
            khz, mode, region, label = LIVE_PRESETS[verb]
        elif verb.replace(".", "", 1).isdigit():
            khz, region, label = float(verb), "na", f"{float(verb):g} kHz"
            mode = parts[2].lower() if len(parts) > 2 else "usb"
            if mode not in MODES or not 10 <= khz <= 30000:
                await msg.channel.send(embed=box("📡  Radio", "KiwiSDRs cover 10–30,000 kHz in "
                                                 f"{', '.join(MODES)}.\n\n{RADIO_USAGE}", COLOR_ERROR,
                                                 footer=_others('radio')))
                return
        else:
            cache = await priyom.refresh(poll_seconds())
            items = [t for t in priyom.upcoming(cache, 24, station=verb) if t.khz]
            if not items:
                await msg.channel.send(embed=box("📡  Radio", f"nothing called {clean(verb.upper(), 20)} is on "
                                                 f"Priyom's schedule today.\n\n{RADIO_USAGE}", COLOR_RADIO,
                                                 footer=_others('radio')))
                return
            now = datetime.now(timezone.utc)
            onair = [t for t in items if t.start - timedelta(minutes=10) <= now <= t.start + timedelta(minutes=10)]
            if not onair:
                nxt = f"next at **{items[0].start:%H:%M}Z** on {items[0].khz:g} kHz"
                await msg.channel.send(embed=box("📡  Radio", f"{clean(verb.upper(), 20)} isn't on the air now — {nxt}.",
                                                 COLOR_RADIO, footer=_others('radio')))
                return
            t = onair[0]
            khz, mode, region, label = t.khz, (t.mode or "usb").lower(), "eu", t.station
        await go_live(msg, khz, mode, region, label, "radio")
    except FeedError as e:
        log_warning(f"[radio] {e}")
        await msg.channel.send(embed=box("📡  Radio", f"couldn't reach the receivers — {clean(str(e), 200)}", COLOR_ERROR))
    except Exception as e:
        log_error(f"[radio] !radio failed: {e}")
        await msg.channel.send(embed=box("📡  Radio", "Something went wrong with the radio. It's in the log.", COLOR_ERROR))


# ── !tacamo ─────────────────────────────────────────────────────────────────

def tacamo_embed(found, last: dict, cache: dict):
    from utils.radio import adsb
    if found:
        lines = []
        for s in found:
            where = f"{s.lat:.1f}, {s.lon:.1f}" if s.lat is not None else "position withheld"
            alt = f"{s.altitude_ft:,} ft" if s.altitude_ft else "on the ground"
            name = s.callsign or s.registration or s.hex
            lines.append(f"**{s.label}** · `{clean(name, 20)}` · {alt} · {where} · [track]({s.map_url})")
        desc = "\n".join(lines)
    else:
        desc = ("None broadcasting right now. They often fly with ADS-B switched off, "
                "so this means none *visible*, not none flying.")
    embed = box("✈️  The EAM relay planes", desc, COLOR_RADIO,
                footer=f"E-6B TACAMO relays EAMs to submarines · via adsb.lol (ODbL) · {_age(cache)}\n"
                       f"{_others('tacamo')}")
    if not found and last:
        add_field(embed, "Last seen", "\n".join(
            f"**{adsb.TYPES.get(k, k)}** · {adsb.ago(v['at'])}"
            + (f" · `{v['callsign']}`" if v.get('callsign') else "")
            + (f" · {v['altitude_ft']:,} ft" if v.get('altitude_ft') else "")
            for k, v in last.items()))
    return embed


async def handle_tacamo_command(ctx, msg, send_kaia_response=None):
    from utils.radio import adsb
    log_action(f"!tacamo for {msg.author}")
    if not radio_enabled():
        await msg.channel.send(embed=box("✈️  TACAMO", "The radio feeds are switched off (`radio.enabled`).", COLOR_ERROR))
        return
    try:
        cache = await adsb.refresh()
        await msg.channel.send(embed=tacamo_embed(adsb.sightings(cache), adsb.last_seen(), cache))
    except FeedError as e:
        log_warning(f"[radio] adsb.lol: {e}")
        await msg.channel.send(embed=box("✈️  TACAMO", f"adsb.lol didn't answer as expected — {clean(str(e), 200)}", COLOR_ERROR))
    except Exception as e:
        log_error(f"[radio] !tacamo failed: {e}")
        await msg.channel.send(embed=box("✈️  TACAMO", "Something went wrong. It's in the log.", COLOR_ERROR))


nightshift.register("tacamo")


async def go_live(msg, khz: float, mode: str, region: str, label: str, family_key: str,
                  blurb: str = "") -> None:
    """Join the caller's voice channel and play a receiver there."""
    from utils.radio import live
    if msg.guild is None or not getattr(msg.author, "voice", None) or not msg.author.voice.channel:
        await msg.channel.send(embed=box("📡  Radio", f"join a voice channel first, then `!{family_key}`.",
                                         COLOR_ERROR, footer=_others(family_key)))
        return
    from utils.audio.strudel_session import get_session as music_session
    if music_session(msg.guild.id):
        await msg.channel.send(embed=box("📡  Radio", "the music's playing — `!music off` first.", COLOR_ERROR))
        return
    try:
        s = await live.start(msg.author.voice.channel, khz, mode, region, label, str(msg.author.display_name))
    except RuntimeError as e:
        # No free receiver, or none sent audio: the reason is the answer.
        log_warning(f"[radio] live {label}: {e}")
        await msg.channel.send(embed=box("📡  Radio", f"{clean(str(e), 200)} — try again in a few minutes.",
                                         COLOR_ERROR, footer=_others(family_key)))
        return
    await msg.channel.send(embed=box(
        f"📡  Live · {label}",
        (f"{blurb}\n\n" if blurb else "")
        + f"{khz:g} kHz {mode.upper()} from **{clean(s.receiver.location or s.receiver.host, 80)}**. "
          f"`!radio off` to stop; I leave after {config.get('radio.live_max_minutes', 60)} minutes "
          f"or when the channel empties.",
        COLOR_RADIO, footer=_others(family_key)))


BUZZER_BLURB = ("UVB-76, *The Buzzer* — a buzz every couple of seconds on 4625 kHz since the 1970s, "
                "broken a few times a year by a voice reading Russian names and numbers. "
                "Nobody outside knows what it's for. It carries best at night in Europe; by day "
                "you may hear only static.")


async def handle_buzzer_command(ctx, msg, send_kaia_response=None):
    log_action(f"!buzzer for {msg.author}")
    if not radio_enabled():
        await msg.channel.send(embed=box("📡  Radio", "The radio feeds are switched off (`radio.enabled`).", COLOR_ERROR))
        return
    parts = msg.content.strip().split()
    if len(parts) > 1 and parts[1].lower() == "off":
        from utils.radio import live
        stopped = msg.guild and await live.stop(msg.guild.id)
        await msg.channel.send(embed=box("📡  Radio", "off the air." if stopped else "nothing was playing.", COLOR_RADIO))
        return
    try:
        khz, mode, region, label = LIVE_PRESETS["buzzer"]
        await go_live(msg, khz, mode, region, label, "buzzer", BUZZER_BLURB)
    except FeedError as e:
        await msg.channel.send(embed=box("📡  Radio", f"couldn't reach the receivers — {clean(str(e), 200)}", COLOR_ERROR))
    except Exception as e:
        log_error(f"[radio] !buzzer failed: {e}")
        await msg.channel.send(embed=box("📡  Radio", "Something went wrong with the radio. It's in the log.", COLOR_ERROR))


nightshift.register("buzzer")


# ── !beacons ────────────────────────────────────────────────────────────────

BAND_ARGS = {"20": 0, "20m": 0, "17": 1, "17m": 1, "15": 2, "15m": 2, "12": 3, "12m": 3, "10": 4, "10m": 4}


def beacons_embed(result: dict | None):
    from utils.radio import beacons
    now = beacons.now_on_air()
    embed = box("🗼  The worldwide beacon chain",
                "Eighteen beacons on six continents take turns every ten seconds on five bands. "
                "Hearing one means that path is open right now.", COLOR_RADIO,
                footer=f"NCDXF/IARU International Beacon Project · heard via a KiwiSDR\n{_others('beacons')}")
    add_field(embed, "On the air this second", "\n".join(
        f"`{khz / 1000:.3f} MHz` **{call}** · {where}" for khz, call, where in now))
    if result:
        heard = [b for b in result["beacons"] if b[2] >= beacons.HEARD_DB]
        quiet = [b for b in result["beacons"] if b[2] < beacons.HEARD_DB]
        at = datetime.fromisoformat(result["at"])
        add_field(embed, f"What Kaia heard on {result['khz'] / 1000:.3f} MHz · {at:%H:%M}Z · from {clean(result['receiver'], 50)}",
                  ("\n".join(f"✅ **{c}** {w} · +{db:.0f} dB" for c, w, db in sorted(heard, key=lambda b: -b[2]))
                   or "nothing — the band is closed from there right now")
                  + (f"\n\n*not heard:* {', '.join(c for c, _, _ in quiet)}" if quiet else ""))
    return embed


async def handle_beacons_command(ctx, msg, send_kaia_response=None):
    import asyncio
    import time
    from utils.radio import beacons, kiwi
    parts = msg.content.strip().split()
    band = BAND_ARGS.get(parts[1].lower(), 0) if len(parts) > 1 else 0
    log_action(f"!beacons band {band} for {msg.author}")
    if not radio_enabled():
        await msg.channel.send(embed=box("🗼  Beacons", "The radio feeds are switched off (`radio.enabled`).", COLOR_ERROR))
        return
    recent = beacons.recent()
    fresh = (recent and time.time() - float(recent.get("fetched_at", 0)) < beacons.FRESH_S
             and recent.get("khz") == beacons.BANDS_KHZ[band])
    await msg.channel.send(embed=beacons_embed(recent if fresh else None))
    if fresh or not kiwi.available():
        return
    if beacons._lock.locked():
        await msg.channel.send(embed=box("🗼  Beacons", "I'm already listening — results in a few minutes.", COLOR_RADIO))
        return
    await msg.channel.send(embed=box("🗼  Listening", f"one full cycle on {beacons.BANDS_KHZ[band] / 1000:.3f} MHz — "
                                     "back in about three minutes.", COLOR_RADIO))

    async def listen_and_report():
        try:
            result = await beacons.listen(band)
            heard = [b[0] for b in result["beacons"] if b[2] >= beacons.HEARD_DB]
            log_info(f"[radio] beacons on {result['khz']:g} kHz from {result['receiver']}: "
                     f"heard {len(heard)} of {len(result['beacons'])}{': ' + ', '.join(heard) if heard else ''}")
            await msg.channel.send(embed=beacons_embed(result))
        except FeedError as e:
            await msg.channel.send(embed=box("🗼  Beacons", f"couldn't get a clean listen — {clean(str(e), 200)}", COLOR_ERROR))
        except Exception as e:
            log_error(f"[radio] !beacons listen failed: {e}")
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    task_registry.register(f"beacons_listen_{int(time.time())}", asyncio.create_task(listen_and_report()))


nightshift.register("beacons")



# ── !overnight ──────────────────────────────────────────────────────────────

async def handle_overnight_command(ctx, msg, send_kaia_response=None):
    """Write the overnight log now, here. Skips the unprompted gate: it was asked for."""
    from utils.radio import overnight
    log_action(f"!overnight for {msg.author}")
    try:
        facts = await overnight.gather()
        if len(facts) < overnight.MIN_FACTS:
            await msg.channel.send(embed=box("🌙  Overnight log", "Not enough happened overnight to write up yet.",
                                             COLOR_RADIO, footer=_others("overnight")))
            return
        text = await overnight.write(ctx, facts)
        embed = box("🌙  Overnight log", clean_block(text, 1800) if text else "(nothing usable came back)",
                    COLOR_RADIO, footer=f"written from {len(facts)} facts gathered in Python\n{_others('overnight')}")
        await msg.channel.send(embed=embed)
    except Exception as e:
        log_error(f"[radio] !overnight failed: {e}")
        await msg.channel.send(embed=box("🌙  Overnight log", "Something went wrong. It's in the log.", COLOR_ERROR))


nightshift.register("overnight")
