"""`!radio` live: a KiwiSDR stream played into a Discord voice channel.

kiwirecorder --nc (raw s16le, mono, 12 kHz) → discord.FFmpegPCMAudio, which
resamples to Discord's 48 kHz stereo. A live session holds one listener slot
on someone's receiver, so it ends after `radio.live_max_minutes` (60), when the
channel empties, or on `!radio off`.
"""
from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

import discord

from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_error
from utils.infrastructure.system.yaml_config import config
from utils.radio import kiwi

_sessions: dict[int, "LiveSession"] = {}
# A real file for FFmpeg's stderr. discord.py calls .fileno() on what it's
# given; subprocess.DEVNULL is the int -3, so it fell back to piping stderr
# through a thread that called .write() on that int — "Write error for
# FFmpegPCMAudio: 'int' object has no attribute 'write'" on every play.
import os as _os
_DEVNULL = open(_os.devnull, "wb")
STALL_S = 30


class _CountingReader:
    """The stream's stdout, remembering when audio last arrived."""
    def __init__(self, raw):
        self.raw = raw
        self.last = time.time()

    def read(self, n=-1):
        data = self.raw.read(n)
        if data:
            self.last = time.time()
        return data


@dataclass
class LiveSession:
    guild_id: int
    vc: discord.VoiceClient
    proc: object
    receiver: kiwi.Receiver
    khz: float
    mode: str
    label: str
    requested_by: str
    started: float = field(default_factory=time.time)
    watchdog: Optional[asyncio.Task] = None
    reader: Optional[_CountingReader] = None
    local: bool = False          # the local RTL-SDR, whose device lock this session holds

    @property
    def minutes(self) -> float:
        return (time.time() - self.started) / 60


def get(guild_id: int) -> Optional[LiveSession]:
    return _sessions.get(guild_id)


def active() -> list[LiveSession]:
    return list(_sessions.values())


async def free_voice(guild) -> None:
    """Stop whatever radio audio this guild's voice connection is playing — a
    live session, a scanner listen-along, a clip — so the next thing can play.
    One connection per guild, and discord.py refuses a second play()."""
    await stop(guild.id)
    try:
        from utils.radio import scanner
        await scanner.stop_listen_along(guild.id, disconnect=False)
    except Exception as e:
        log_debug(f"[radio] listen-along not stopped: {e}")
    vc = guild.voice_client
    if vc and vc.is_connected() and vc.is_playing():
        vc.stop()


async def start(channel, khz: float, mode: str, region: str, label: str, requested_by: str) -> LiveSession:
    guild_id = channel.guild.id
    await free_voice(channel.guild)
    receivers = kiwi.choose(await kiwi.directory(), khz, region, n=4)
    if not receivers:
        raise RuntimeError(f"no free receiver covers {khz:g} kHz right now")
    # Join voice only once a receiver is actually sending audio: one that
    # accepts the connection and never streams played silence into the channel.
    proc = receiver = None
    for r in receivers:
        p = kiwi.open_stream(r, khz, mode)
        if await asyncio.to_thread(kiwi.first_audio, p):
            proc, receiver = p, r
            break
        log_debug(f"[radio] {r.host} sent no audio; trying the next receiver")
        kiwi.close_stream(p)
    if proc is None:
        raise RuntimeError(f"none of {len(receivers)} receivers sent audio on {khz:g} kHz")
    reader = _CountingReader(proc.stdout)
    # stderr to /dev/null: left alone, ffmpeg inherits the bot's real terminal
    # (fd 2, beneath the logging redirect) and its warnings land on the curses
    # dashboard, which then cannot redraw.
    source = discord.FFmpegPCMAudio(reader, pipe=True, before_options="-f s16le -ar 12000 -ac 1",
                                    stderr=_DEVNULL)
    vc = channel.guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        vc = await channel.connect(timeout=30.0, reconnect=True)
    vc.play(source, after=lambda e: log_error(f"[radio] playback error: {e}") if e else None)
    session = LiveSession(guild_id, vc, proc, receiver, khz, mode, label, requested_by, reader=reader)
    session.watchdog = asyncio.create_task(_watch(session))
    _sessions[guild_id] = session
    log_action(f"[radio] live {label} {khz:g} kHz {mode} via {receiver.host} in {channel.name} for {requested_by}")
    return session


async def start_local(channel, freq_hz: int, label: str, requested_by: str, gain: int = 40) -> LiveSession:
    """Play the local RTL-SDR on `freq_hz` into a voice channel. Holds the
    dongle for the session, so the nightly scanner pauses until it ends."""
    from utils.radio import rtl
    guild_id = channel.guild.id
    await free_voice(channel.guild)
    rtl.YIELD.set()                      # the waterfall watch gives the dongle up within a hop
    try:
        await asyncio.wait_for(rtl.DEVICE.acquire(), 90)
    except asyncio.TimeoutError:
        raise RuntimeError("the scanner is mid-recording; try again in a minute")
    finally:
        rtl.YIELD.clear()
    try:
        proc = rtl.open_stream(freq_hz, gain)
        if not await asyncio.to_thread(kiwi.first_audio, proc):
            kiwi.close_stream(proc)
            raise RuntimeError("the RTL-SDR didn't start streaming — another program may be using it")
        reader = _CountingReader(proc.stdout)
        source = discord.FFmpegPCMAudio(reader, pipe=True, before_options=f"-f s16le -ar {rtl.SAMPLE_RATE} -ac 1",
                                        stderr=_DEVNULL)
        vc = channel.guild.voice_client
        if vc and vc.is_connected():
            await vc.move_to(channel)
        else:
            vc = await channel.connect(timeout=30.0, reconnect=True)
        vc.play(source, after=lambda e: log_error(f"[radio] playback error: {e}") if e else None)
    except Exception:
        rtl.DEVICE.release()
        raise
    session = LiveSession(guild_id, vc, proc, None, freq_hz / 1e3, "fm", label, requested_by,
                          reader=reader, local=True)
    session.watchdog = asyncio.create_task(_watch(session))
    _sessions[guild_id] = session
    log_action(f"[radio] local {label} {freq_hz / 1e6:.4f} MHz in {channel.name} for {requested_by}")
    return session


async def play_clip(channel, path, label: str, requested_by: str) -> None:
    """Play a recorded clip into a voice channel, then leave. A live session
    in that guild is stopped first."""
    from pathlib import Path as _Path
    path = _Path(path)
    if not path.is_file():
        raise RuntimeError("that recording is no longer on disk")
    guild_id = channel.guild.id
    await free_voice(channel.guild)
    vc = channel.guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        vc = await channel.connect(timeout=30.0, reconnect=True)
    loop = asyncio.get_running_loop()

    def _done(err):
        if err:
            log_error(f"[radio] clip playback error: {err}")
        # Leave once the clip ends, unless something else started playing.
        async def _leave():
            await asyncio.sleep(2)
            if vc.is_connected() and not vc.is_playing() and guild_id not in _sessions:
                await vc.disconnect(force=True)
        asyncio.run_coroutine_threadsafe(_leave(), loop)

    vc.play(discord.FFmpegPCMAudio(str(path), stderr=_DEVNULL), after=_done)
    log_action(f"[radio] playing clip {path.name} ({label}) in {channel.name} for {requested_by}")


async def _watch(s: LiveSession) -> None:
    limit = float(config.get("radio.live_max_minutes", 60))
    empty_checks = 0
    try:
        while s.guild_id in _sessions:
            await asyncio.sleep(20)
            humans = [m for m in (getattr(s.vc.channel, "members", []) or []) if not m.bot]
            empty_checks = empty_checks + 1 if not humans else 0
            reason = ("time limit" if s.minutes >= limit
                      else "the channel emptied" if empty_checks >= 2
                      else "the receiver stream ended" if s.proc.poll() is not None
                      else f"no audio for {STALL_S}s" if s.reader and time.time() - s.reader.last > STALL_S
                      else "")
            if reason:
                log_action(f"[radio] live session ending: {reason} ({s.minutes:.0f} min)")
                await stop(s.guild_id)
                return
    except asyncio.CancelledError:
        pass


async def stop(guild_id: int) -> bool:
    s = _sessions.pop(guild_id, None)
    if not s:
        return False
    try:
        # Stream first: discord.py's pipe writer then reads end-of-stream and
        # exits on its own. Stopping playback first blanks its handles while
        # it is still blocked reading, and the thread dies with a traceback.
        await asyncio.to_thread(kiwi.close_stream, s.proc)
        await asyncio.sleep(0.5)
        if s.vc.is_playing():
            s.vc.stop()
    finally:
        if s.vc.is_connected():
            await s.vc.disconnect(force=True)
        if s.watchdog and s.watchdog is not asyncio.current_task():
            s.watchdog.cancel()
        if s.local:
            from utils.radio import rtl
            if rtl.DEVICE.locked():
                rtl.DEVICE.release()
    log_action(f"[radio] live session ended after {s.minutes:.0f} min")
    return True


async def stop_all() -> None:
    for gid in list(_sessions):
        try:
            await stop(gid)
        except Exception as e:
            log_debug(f"[radio] stop_all: {e}")
