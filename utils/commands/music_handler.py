"""
Kaia Music Command Handler
Handles !music — joins a voice channel and performs generative music.

    !music on [--genre]     join the caller's voice channel and start
    !music off              stop and leave
    !music status           what is playing, and where in the arrangement
    !music genres           list them
    !music <genre>          switch without leaving
    !music records [query]  a set from the local record library, mixed record
                            to record (starting from the query, if given)
    !music skip             the next record, now
    !music booth            the DJ booth window: both decks and the mixer, live

The sound engine is Strudel (https://codeberg.org/uzu/strudel, AGPL-3.0),
driven in a local browser and captured off a PipeWire null sink. It is CPU and
GPU-light for this process — the synthesis happens in the browser — and shares
nothing with the inference path, so the chat model keeps its VRAM.
"""

from __future__ import annotations

import time

import discord

from utils.audio import dj
from utils.audio.strudel_patterns import (DEFAULT_GENRE, GENRES, describe,
                                          genre_names)
from utils.audio.strudel_session import (active_sessions, get_session,
                                         start_session)
from utils.commands.embed_style import add_field, box, clean, notice
from utils.infrastructure.logging.kaia_logger import (log_action, log_error,
                                                      log_warning)
from utils.infrastructure.system.yaml_config import config

COLOR_MUSIC = 0x5B4B8A
_last_start: dict[int, float] = {}
_COOLDOWN_S = 20

_ON = {"on", "start", "play", "join"}
_OFF = {"off", "stop", "leave", "quit"}
_INFO = {"status", "info", "now", "genres", "list", "help"}
_RECORDS = {"records", "vinyl", "crate", "library"}
_SKIP = {"skip", "next"}
_BOOTH = {"booth", "decks", "dashboard"}


def _parse(parts: list[str]) -> tuple[str, str | None, str]:
    """(verb, genre, request). Anything that is not a verb or a genre is a request."""
    verb, genre, rest = "", None, []
    for raw in parts[1:]:
        tok = raw.lstrip("-").lower()
        if tok in GENRES:
            genre = tok
        elif tok in _ON or tok in _OFF or tok in _INFO:
            verb = verb or tok
        else:
            rest.append(raw)
    request = " ".join(rest)
    if not verb:
        verb = "on" if genre else ("request" if request else "status")
    return verb, genre, request


async def handle_music_command(ctx, msg, send_kaia_response):
    if not config.get("music.enabled", True):
        await msg.channel.send(embed=notice("the music engine is switched off."))
        return
    if msg.guild is None:
        await msg.channel.send(embed=notice("only in a server voice channel."))
        return

    parts = msg.content.strip().split()
    if len(parts) > 1 and parts[1].lower() in _RECORDS:
        return await _records(msg, " ".join(parts[2:]))
    from utils.audio.records import get_records
    crate_session = get_records(msg.guild.id)
    if crate_session and len(parts) > 1 and parts[1].lower() in _BOOTH:
        from utils.audio import dj_dashboard
        import asyncio
        await asyncio.to_thread(dj_dashboard.open_window)
        return await msg.channel.send(embed=notice(
            f"the booth is open on my screen — {dj_dashboard.url() or 'the server would not start'}"))
    if crate_session and len(parts) > 1 and parts[1].lower() in _SKIP:
        crate_session.skip()
        return await msg.channel.send(embed=notice("bringing the next one in."))

    verb, genre, request = _parse(parts)
    session = get_session(msg.guild.id)
    if crate_session and verb in _OFF:
        await msg.channel.send(embed=notice("fading out."))
        return await crate_session.stop()
    if crate_session and verb in {"status", "info", "now"}:
        return await msg.channel.send(embed=_records_status(crate_session))

    if verb in {"genres", "list"}:
        embed = box("🎧  What I can play",
                    "\n".join(f"`{g}` — {GENRES[g]['blurb']}" for g in genre_names()),
                    COLOR_MUSIC, footer="!music on to let me pick · !music on --house to choose")
        await msg.channel.send(embed=embed)
        return

    if verb == "help":
        embed = box("🎧  Music", "\n".join((
            "`!music on` — i pick something for the mood we're in",
            "`!music on --<genre>` · `!music <genre>` — play or switch genre",
            "`!music off` · `!music status` · `!music genres`",
            "`!music records [artist or title]` — records from the library, mixed · `!music skip` · "
            "`!music booth` — the DJ booth window",
            "",
            "**requests while i play:** " + " · ".join(f"`{r}`" for r in dj.REQUESTS),
        )), COLOR_MUSIC)
        await msg.channel.send(embed=embed)
        return

    if verb == "request":
        if not session:
            await msg.channel.send(embed=notice(
                "i'm not playing anything — `!music on` first.", error=True))
            return
        result = await session.request(request, getattr(msg.author, "display_name", ""))
        if not result.understood:
            await msg.channel.send(embed=notice(
                "not sure what you want there. try " + ", ".join(f"`{r}`" for r in dj.REQUESTS) + "."))
            return
        await msg.channel.send(embed=notice(f"🎧 {result.reply}"))
        return

    if verb in {"status", "info", "now"}:
        if not session:
            await msg.channel.send(embed=notice("nothing playing. `!music on` and i'll pick something."))
            return
        s = session.stats()
        bpm = dj.bpm_of(session.perf.cpm)
        e = box("🎧  kaia radio", f"*{clean(s['section'], 200)}*", COLOR_MUSIC,
                footer=f"up {s['uptime_min']} min · pass {s['passes'] + 1} · "
                       f"{s['underruns']} underruns · !music help for requests")
        add_field(e, "Genre", f"{s['genre']} · {bpm:g} bpm" if bpm else s["genre"], inline=True)
        add_field(e, "Channel", s["channel"], inline=True)
        add_field(e, "Listeners", str(s["listeners"]), inline=True)
        add_field(e, "Playing", " + ".join(s["lanes"]) or "—", inline=False)
        await msg.channel.send(embed=e)
        return

    if verb in _OFF:
        if not session:
            await msg.channel.send(embed=notice("i'm not playing anything."))
            return
        await msg.channel.send(embed=notice("winding it down."))
        await session.stop()
        return

    # ── on / switch ──────────────────────────────────────────────────
    if session and genre and genre != session.genre:
        await session.set_genre(genre)
        await msg.channel.send(embed=notice(f"shifting to *{genre}*."))
        return
    if session:
        await msg.channel.send(embed=notice(
            f"already playing *{session.genre}* in {session.channel_name}."))
        return

    voice_state = getattr(msg.author, "voice", None)
    if not voice_state or not voice_state.channel:
        await msg.channel.send(embed=notice("join a voice channel first."))
        return
    channel = voice_state.channel

    perms = channel.permissions_for(msg.guild.me)
    if not (perms.connect and perms.speak):
        await msg.channel.send(embed=notice(f"i can't speak in {channel.name}.", error=True))
        return

    now = time.time()
    if now - _last_start.get(msg.guild.id, 0.0) < _COOLDOWN_S:
        await msg.channel.send(embed=notice("give me a moment."))
        return
    limit = int(config.get("music.max_concurrent_sessions", 1))
    if len(active_sessions()) >= limit:
        await msg.channel.send(embed=notice("i'm already playing elsewhere."))
        return

    _last_start[msg.guild.id] = now
    why = ""
    if not genre:
        # Her pick: mood and the hour. The configured default is only the
        # fallback if that fails.
        try:
            from datetime import datetime
            from utils.core.kaia_art_intent import mood
            genre, why = dj.pick_genre(mood(), datetime.now().hour, GENRES)
        except Exception:
            genre = config.get("music.default_genre", DEFAULT_GENRE)
    if genre not in GENRES:
        genre = DEFAULT_GENRE

    try:
        async with msg.channel.typing():
            await start_session(channel, genre=genre,
                                requested_by=msg.author.display_name,
                                text_channel=msg.channel)
    except RuntimeError as exc:
        log_error(f"[music] engine unavailable: {exc}")
        await msg.channel.send(embed=notice(
            "the music engine won't start — assets or audio sink are missing. "
            "`tools/maintenance/fetch_music_assets.py` sets them up.", error=True))
        return
    except discord.ClientException as exc:
        log_warning(f"[music] join failed: {exc}")
        await msg.channel.send(embed=notice("i couldn't get into that channel.", error=True))
        return
    except Exception as exc:
        log_error(f"[music] start failed: {exc}")
        await msg.channel.send(embed=notice("something went wrong starting the sound.", error=True))
        return

    lead = f"{why}, so *{genre}*." if why else f"*{genre}*."
    embed = box(f"🎧  In {channel.name}", f"{lead}\n{describe(genre)} — it builds and changes as it goes.",
                COLOR_MUSIC, footer="!music darker · faster · drop · more bass … — !music help")
    await msg.channel.send(embed=embed)
    log_action(f"[music] {msg.author.display_name} started a set; kaia picked {genre}"
               + (f" ({why})" if why else ""))


def _records_status(session) -> discord.Embed:
    st = session.stats()
    now = st["now"] or "—"
    meta = " · ".join(x for x in (f"{st['bpm']:g} bpm" if st["bpm"] else "", st["key"] or "", st["genre"] or "") if x)
    e = box("🎧  records", f"**{clean(now, 200)}**" + (f"\n{meta}" if meta else ""), COLOR_MUSIC,
            footer=f"up {st['uptime_min']} min · {st['played']} played · !music skip · !music off")
    add_field(e, "Next", clean(st["next"], 200) if st["next"] else "choosing…", inline=False)
    add_field(e, "Channel", st["channel"], inline=True)
    add_field(e, "Listeners", str(st["listeners"]), inline=True)
    return e


async def _records(msg, query: str) -> None:
    """Start a set from the local record library."""
    from utils.audio import library, records
    voice_state = getattr(msg.author, "voice", None)
    if not voice_state or not voice_state.channel:
        return await msg.channel.send(embed=notice("join a voice channel first."))
    channel = voice_state.channel
    perms = channel.permissions_for(msg.guild.me)
    if not (perms.connect and perms.speak):
        return await msg.channel.send(embed=notice(f"i can't speak in {channel.name}.", error=True))

    import asyncio
    crate = await asyncio.to_thread(library.load, config.get("music.library_catalog", "") or "")
    if not crate:
        return await msg.channel.send(embed=notice(
            "i don't have a record library — `music.library_catalog` in kaia.yaml points at it.", error=True))
    if query:
        first = library.find(crate, query)
        if not first:
            return await msg.channel.send(embed=notice(f"nothing in the crate matches *{clean(query, 80)}*."))
        why = "you asked for it"
    else:
        from datetime import datetime
        try:
            from utils.core.kaia_art_intent import mood
            feeling = mood()
        except Exception:
            feeling = {}
        first = library.opener(crate, feeling, datetime.now().hour)
        why = "for the mood i'm in"
    try:
        async with msg.channel.typing():
            await records.start_records(
                channel, crate, first, requested_by=msg.author.display_name, text_channel=msg.channel,
                mix_beats=int(config.get("music.records_mix_beats", 16)),
                alone_grace_s=float(config.get("music.alone_grace_seconds", 120)))
    except discord.ClientException as exc:
        log_warning(f"[records] join failed: {exc}")
        return await msg.channel.send(embed=notice("i couldn't get into that channel.", error=True))
    except Exception as exc:
        log_error(f"[records] start failed: {exc}")
        return await msg.channel.send(embed=notice("the records wouldn't start; the log has why.", error=True))
    meta = " · ".join(x for x in (f"{first.bpm:g} bpm" if first.bpm else "", first.key or "") if x)
    await msg.channel.send(embed=box(
        f"🎧  Records in {channel.name}",
        f"starting with **{clean(first.name, 200)}**{' (' + meta + ')' if meta else ''}, {why}. "
        f"{len(crate)} in the crate; each next one picked to sit with the last in key and tempo.",
        COLOR_MUSIC, footer="!music skip · !music status · !music off"))
    log_action(f"[records] {msg.author.display_name} started records in {channel.name}: {first.name}")
