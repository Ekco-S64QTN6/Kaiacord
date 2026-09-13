"""
Kaia Music Command Handler
Handles !music — joins a voice channel and performs generative music.

    !music on [--genre]     join the caller's voice channel and start
    !music off              stop and leave
    !music status           what is playing, and where in the arrangement
    !music genres           list them
    !music <genre>          switch without leaving

The sound engine is Strudel (https://codeberg.org/uzu/strudel, AGPL-3.0),
driven in a local browser and captured off a PipeWire null sink. It is CPU and
GPU-light for this process — the synthesis happens in the browser — and shares
nothing with the inference path, so the chat model keeps its VRAM.
"""

from __future__ import annotations

import time

import discord

from utils.audio.strudel_patterns import (DEFAULT_GENRE, GENRES, describe,
                                          genre_names)
from utils.audio.strudel_session import (active_sessions, get_session,
                                         start_session)
from utils.infrastructure.logging.kaia_logger import (log_action, log_error,
                                                      log_warning)
from utils.infrastructure.system.yaml_config import config

_last_start: dict[int, float] = {}
_COOLDOWN_S = 20

_ON = {"on", "start", "play", "join"}
_OFF = {"off", "stop", "leave", "quit"}


def _genres_line() -> str:
    return ", ".join(f"`{g}`" for g in genre_names())


def _parse(parts: list[str]) -> tuple[str, str | None]:
    """Return (verb, genre). Accepts `--house`, `house`, or nothing."""
    verb, genre = "", None
    for raw in parts[1:]:
        tok = raw.lstrip("-").lower()
        if tok in GENRES:
            genre = tok
        elif tok in _ON or tok in _OFF or tok in {
                "status", "info", "now", "genres", "list", "help"}:
            verb = verb or tok
    if not verb:
        verb = "on" if genre else "status"
    return verb, genre


async def handle_music_command(ctx, msg, send_kaia_response):
    if not config.get("music.enabled", True):
        await send_kaia_response(msg.channel, "the music engine is switched off.")
        return
    if msg.guild is None:
        await send_kaia_response(msg.channel, "only in a server voice channel.")
        return

    verb, genre = _parse(msg.content.strip().split())
    session = get_session(msg.guild.id)

    if verb in {"genres", "list"}:
        lines = [f"`{g}` — {GENRES[g]['blurb']}" for g in genre_names()]
        await send_kaia_response(
            msg.channel,
            "what i can play:\n" + "\n".join(lines) +
            "\n\n`!music on --house` to start, `!music off` to stop.")
        return

    if verb == "help":
        await send_kaia_response(
            msg.channel,
            "`!music on [--genre]` · `!music off` · `!music status` · "
            f"`!music genres`\ngenres: {_genres_line()}")
        return

    if verb in {"status", "info", "now"}:
        if not session:
            await send_kaia_response(msg.channel, "nothing playing.")
            return
        s = session.stats()
        e = discord.Embed(title="🎧 kaia radio", colour=0x5B4B8A)
        e.add_field(name="genre", value=f"{s['genre']} ({GENRES[s['genre']]['bpm']})", inline=True)
        e.add_field(name="channel", value=s["channel"], inline=True)
        e.add_field(name="listeners", value=str(s["listeners"]), inline=True)
        e.add_field(name="section",
                    value=f"{s['section']} ({s['section_index']}/{s['sections_total']})",
                    inline=True)
        e.add_field(name="playing", value="+".join(s["lanes"]) or "—", inline=True)
        e.add_field(name="next in", value=f"{s['remaining_s']:.0f}s", inline=True)
        e.set_footer(text=f"up {s['uptime_min']} min · pass {s['passes'] + 1} · "
                          f"buffer {s['buffered_s']}s · {s['underruns']} underruns")
        await msg.channel.send(embed=e)
        return

    if verb in _OFF:
        if not session:
            await send_kaia_response(msg.channel, "i'm not playing anything.")
            return
        await send_kaia_response(msg.channel, "winding it down.")
        await session.stop()
        return

    # ── on / switch ──────────────────────────────────────────────────
    if session and genre and genre != session.genre:
        await session.set_genre(genre)
        await send_kaia_response(msg.channel, f"shifting to *{genre}*.")
        return
    if session:
        await send_kaia_response(
            msg.channel, f"already playing *{session.genre}* in {session.channel_name}.")
        return

    voice_state = getattr(msg.author, "voice", None)
    if not voice_state or not voice_state.channel:
        await send_kaia_response(msg.channel, "join a voice channel first.")
        return
    channel = voice_state.channel

    perms = channel.permissions_for(msg.guild.me)
    if not (perms.connect and perms.speak):
        await send_kaia_response(
            msg.channel, f"i can't speak in {channel.name}.")
        return

    now = time.time()
    if now - _last_start.get(msg.guild.id, 0.0) < _COOLDOWN_S:
        await send_kaia_response(msg.channel, "give me a moment.")
        return
    limit = int(config.get("music.max_concurrent_sessions", 1))
    if len(active_sessions()) >= limit:
        await send_kaia_response(msg.channel, "i'm already playing elsewhere.")
        return

    _last_start[msg.guild.id] = now
    genre = genre or config.get("music.default_genre", DEFAULT_GENRE)
    if genre not in GENRES:
        genre = DEFAULT_GENRE

    try:
        async with msg.channel.typing():
            await start_session(channel, genre=genre,
                                requested_by=msg.author.display_name,
                                text_channel=msg.channel)
    except RuntimeError as exc:
        log_error(f"[music] engine unavailable: {exc}")
        await send_kaia_response(
            msg.channel,
            "the music engine won't start — assets or audio sink are missing. "
            "`tools/maintenance/fetch_music_assets.py` sets them up.")
        return
    except discord.ClientException as exc:
        log_warning(f"[music] join failed: {exc}")
        await send_kaia_response(msg.channel, "i couldn't get into that channel.")
        return
    except Exception as exc:
        log_error(f"[music] start failed: {exc}")
        await send_kaia_response(msg.channel, "something went wrong starting the sound.")
        return

    await send_kaia_response(
        msg.channel,
        f"in {channel.name}. *{describe(genre)}* — it builds and changes as it goes.")
