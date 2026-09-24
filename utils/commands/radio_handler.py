"""
!skyking            — the latest Emergency Action Messages from the HFGCS net (eam.watch)
!skyking N          — message N in full: preamble, body, repeats, recording
!skyking classic    — a message from the Skyking archive, read the way it sounded
!numbers [station]  — number stations on the air in the next few hours (Priyom)

Skyking itself is defunct; the command is named for it as an homage, and shows
what the net sends now. Feeds are read from the on-disk cache the radio task
refreshes every few hours; a command only fetches when there is no cache yet.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from utils.commands.embed_style import COLOR_ERROR, add_field, box, clean
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.radio import eam_watch, priyom
from utils.radio.fetch import FeedError

COLOR_RADIO = 0x3B8B5A

#: The radio commands, for the small print under each box.
RADIO_COMMANDS = {
    "skyking": "!skyking — latest EAMs",
    "detail": "!skyking <n> — one in full",
    "classic": "!skyking classic — an old Skyking",
    "numbers": "!numbers [station] [hours] — number stations",
}


def _others(*leave_out: str) -> str:
    return " · ".join(v for k, v in RADIO_COMMANDS.items() if k not in leave_out)
DEFAULT_POLL_HOURS = 6


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
