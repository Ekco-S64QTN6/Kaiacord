"""`!radio` live: a KiwiSDR stream played into a Discord voice channel.

kiwirecorder --nc (raw s16le, mono, 12 kHz) → discord.FFmpegPCMAudio, which
resamples to Discord's 48 kHz stereo. A live session holds one listener slot
on someone's receiver, so it ends after `radio.live_max_minutes` (60), when the
channel empties, or on `!radio off`.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import discord

from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_error
from utils.infrastructure.system.yaml_config import config
from utils.radio import kiwi

_sessions: dict[int, "LiveSession"] = {}


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

    @property
    def minutes(self) -> float:
        return (time.time() - self.started) / 60


def get(guild_id: int) -> Optional[LiveSession]:
    return _sessions.get(guild_id)


def active() -> list[LiveSession]:
    return list(_sessions.values())


async def start(channel, khz: float, mode: str, region: str, label: str, requested_by: str) -> LiveSession:
    guild_id = channel.guild.id
    if guild_id in _sessions:
        await stop(guild_id)
    receivers = kiwi.choose(await kiwi.directory(), khz, region)
    if not receivers:
        raise RuntimeError(f"no free receiver covers {khz:g} kHz right now")
    receiver = receivers[0]
    proc = kiwi.open_stream(receiver, khz, mode)
    source = discord.FFmpegPCMAudio(proc.stdout, pipe=True, before_options="-f s16le -ar 12000 -ac 1")
    vc = channel.guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        vc = await channel.connect(timeout=30.0, reconnect=True)
    vc.play(source, after=lambda e: log_error(f"[radio] playback error: {e}") if e else None)
    session = LiveSession(guild_id, vc, proc, receiver, khz, mode, label, requested_by)
    session.watchdog = asyncio.create_task(_watch(session))
    _sessions[guild_id] = session
    log_action(f"[radio] live {label} {khz:g} kHz {mode} via {receiver.host} in {channel.name} for {requested_by}")
    return session


async def _watch(s: LiveSession) -> None:
    limit = float(config.get("radio.live_max_minutes", 60))
    try:
        while s.guild_id in _sessions:
            await asyncio.sleep(20)
            humans = [m for m in getattr(s.vc.channel, "members", []) if not m.bot]
            if s.minutes >= limit or not humans or s.proc.poll() is not None:
                log_debug(f"[radio] live session ending ({s.minutes:.0f} min, {len(humans)} listening)")
                await stop(s.guild_id)
                return
    except asyncio.CancelledError:
        pass


async def stop(guild_id: int) -> bool:
    s = _sessions.pop(guild_id, None)
    if not s:
        return False
    try:
        if s.vc.is_playing():
            s.vc.stop()
    finally:
        kiwi.close_stream(s.proc)
        if s.vc.is_connected():
            await s.vc.disconnect(force=True)
        if s.watchdog and s.watchdog is not asyncio.current_task():
            s.watchdog.cancel()
    log_action(f"[radio] live session ended after {s.minutes:.0f} min")
    return True


async def stop_all() -> None:
    for gid in list(_sessions):
        try:
            await stop(gid)
        except Exception as e:
            log_debug(f"[radio] stop_all: {e}")
