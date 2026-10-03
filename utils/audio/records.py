"""Records: a set from the local music library, mixed record to record.

`!music records` plays the crate in `library.py` the way a DJ would: each next
record chosen to sit with the last in key and tempo, stretched to its tempo
(ffmpeg `atempo`, which keeps the pitch), and brought in under the end of the
one playing with an equal-power crossfade. All of it is ffmpeg and NumPy on the
CPU: no model, no VRAM, nothing analysed live — the catalog already holds BPM
and key.

Same contract as the Strudel source: `read()` hands discord.py one 20 ms frame
every 20 ms and never blocks; ffmpeg output is pumped into a buffer on a
thread, and the next record is picked and probed on another, long before its
fade begins.
"""
from __future__ import annotations

import asyncio
import random
import re
import subprocess
import threading
import time
from collections import deque
from typing import Callable, Optional

import numpy as np

try:
    import discord
    _AudioSource = discord.AudioSource
except Exception:                      # pragma: no cover
    _AudioSource = object

from utils.audio import library
from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_error, log_warning

RATE = 48000
FRAME_MS = 20
FRAME_BYTES = RATE * 2 * 2 * FRAME_MS // 1000          # s16le stereo
FRAMES_PER_S = 1000 // FRAME_MS
SILENCE = b"\x00" * FRAME_BYTES
#: A record shorter than this is not crossfaded into: there is no room.
MIN_RECORD_S = 30.0


def probe_seconds(path: str) -> Optional[float]:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", path],
            capture_output=True, text=True, timeout=20)
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


#: Every record is brought to about this mean level, so the next one is not
#: twice as loud as the last. Never raised past its own peak.
TARGET_MEAN_DB = -14.0


def gain_db(path: str) -> float:
    """The gain that brings a record's mean level to TARGET_MEAN_DB without
    pushing its peak past full scale. 0 if it cannot be measured."""
    try:
        out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-af", "volumedetect",
                              "-f", "null", "-"], capture_output=True, text=True, timeout=60).stderr
        mean = float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", out).group(1))
        peak = float(re.search(r"max_volume:\s*(-?[\d.]+) dB", out).group(1))
    except (OSError, AttributeError, ValueError, subprocess.SubprocessError):
        return 0.0
    return round(max(-12.0, min(TARGET_MEAN_DB - mean, -peak, 12.0)), 1)


def open_pcm(path: str, ratio: float = 1.0, gain: float = 0.0) -> subprocess.Popen:
    """ffmpeg decoding a record to 48 kHz stereo s16le, stretched by `ratio`."""
    args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path]
    filters = []
    if abs(ratio - 1.0) > 0.001:
        filters.append(f"atempo={ratio:.4f}")
    if abs(gain) >= 0.1:
        filters.append(f"volume={gain:.1f}dB")
    if filters:
        args += ["-af", ",".join(filters)]
    args += ["-f", "s16le", "-ar", str(RATE), "-ac", "2", "pipe:1"]
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)


class Deck:
    """One record being decoded: frames pumped from a byte stream into a buffer."""

    def __init__(self, record: library.Record, ratio: float, seconds: float,
                 stream_factory: Callable[..., object] = open_pcm, buffer_frames: int = 150,
                 gain: float = 0.0):
        self.record = record
        self.ratio = ratio
        self.total_frames = int(seconds / ratio * FRAMES_PER_S)
        self.played = 0
        self._proc = stream_factory(record.path, ratio, gain) if gain else stream_factory(record.path, ratio)
        self._frames: deque[bytes] = deque()
        self._lock = threading.Lock()
        self._room = threading.Semaphore(buffer_frames)
        self._eof = False
        self._closed = False
        threading.Thread(target=self._pump, daemon=True, name="kaia-records-deck").start()

    def _pump(self) -> None:
        out = getattr(self._proc, "stdout", self._proc)
        try:
            while not self._closed:
                self._room.acquire()
                chunk = out.read(FRAME_BYTES)
                if not chunk:
                    break
                if len(chunk) < FRAME_BYTES:
                    chunk = chunk + b"\x00" * (FRAME_BYTES - len(chunk))
                with self._lock:
                    self._frames.append(chunk)
        except Exception as e:
            log_debug(f"[records] deck read ended: {e}")
        self._eof = True

    def frame(self) -> Optional[bytes]:
        """The next frame; silence if decoding is behind; None once the record is over."""
        with self._lock:
            if self._frames:
                self.played += 1
                self._room.release()
                return self._frames.popleft()
        return None if self._eof else SILENCE

    @property
    def remaining(self) -> int:
        return max(0, self.total_frames - self.played)

    def close(self) -> None:
        self._closed = True
        self._room.release()
        proc = self._proc
        try:
            if hasattr(proc, "kill"):
                proc.kill()
        except Exception:
            pass


def mix(out_frame: bytes, in_frame: bytes, t: float) -> bytes:
    """Equal-power crossfade at position t (0 = all outgoing, 1 = all incoming)."""
    a = np.frombuffer(out_frame, dtype=np.int16).astype(np.float32)
    b = np.frombuffer(in_frame, dtype=np.int16).astype(np.float32)
    t = min(1.0, max(0.0, t))
    y = a * np.cos(t * np.pi / 2) + b * np.sin(t * np.pi / 2)
    return np.clip(np.rint(y), -32768, 32767).astype(np.int16).tobytes()


class CrossfadeSource(_AudioSource):
    """Plays decks one after another, overlapping the end of one with the start
    of the next. `pick` returns the next (record, ratio, seconds) or None."""

    def __init__(self, first: Deck, pick: Callable[[Deck], Optional[tuple]],
                 fade_s: float = 8.0, stream_factory=open_pcm,
                 on_change: Optional[Callable[[library.Record], None]] = None):
        self.current: Optional[Deck] = first
        self.incoming: Optional[Deck] = None
        self._pick = pick
        self._fade = int(fade_s * FRAMES_PER_S)
        self._factory = stream_factory
        self._on_change = on_change
        self._queued: Optional[tuple] = None
        self._picking = False
        self._skip = False
        self.frames_sent = 0
        self._prefetch()

    def is_opus(self) -> bool:
        return False

    def _prefetch(self) -> None:
        if self._picking or self._queued or self.current is None:
            return
        self._picking = True
        deck = self.current

        def run():
            try:
                self._queued = self._pick(deck)
            except Exception as e:
                log_warning(f"[records] could not choose the next record: {e}")
                self._queued = None
            finally:
                self._picking = False
        threading.Thread(target=run, daemon=True, name="kaia-records-pick").start()

    def skip(self) -> None:
        """Start the next record's fade now."""
        self._skip = True

    def _start_incoming(self) -> None:
        if self.incoming or not self._queued:
            return
        record, ratio, seconds, *rest = self._queued
        self._queued = None
        try:
            self.incoming = Deck(record, ratio, seconds, self._factory, gain=rest[0] if rest else 0.0)
        except Exception as e:
            log_error(f"[records] could not open {record.name}: {e}")

    def read(self) -> bytes:
        cur = self.current
        if cur is None:
            return b""
        fading = self._skip or cur.remaining <= self._fade
        if fading:
            self._start_incoming()
        out = cur.frame()
        nxt = self.incoming
        if nxt is not None:
            done = nxt.played
            t = done / max(1, min(self._fade, cur.remaining + done))
            inc = nxt.frame() or SILENCE
            if out is None or t >= 1.0:
                self._advance()
                frame = inc
            else:
                frame = mix(out, inc, t)
        elif out is None:
            # The record ended with nothing ready: a gap, then whatever comes.
            self._start_incoming()
            if self.incoming:
                self._advance()
                frame = self.current.frame() or SILENCE
            elif self._picking or self._queued:
                frame = SILENCE
            else:
                cur.close()
                self.current = None
                return b""
        else:
            frame = out
        self.frames_sent += 1
        return frame

    def _advance(self) -> None:
        old, self.current, self.incoming = self.current, self.incoming, None
        self._skip = False
        if old:
            old.close()
        if self.current and self._on_change:
            try:
                self._on_change(self.current.record)
            except Exception as e:
                log_debug(f"[records] on_change: {e}")
        self._prefetch()

    def cleanup(self) -> None:
        for deck in (self.current, self.incoming):
            if deck:
                deck.close()
        self.current = self.incoming = None


# ── Sessions ─────────────────────────────────────────────────────────

_sessions: dict[int, "RecordsSession"] = {}


def get_records(guild_id: int) -> Optional["RecordsSession"]:
    return _sessions.get(guild_id)


class RecordsSession:
    def __init__(self, vc, crate: list[library.Record], requested_by: str, text_channel=None,
                 alone_grace_s: float = 120.0):
        self.vc = vc
        self.crate = crate
        self.requested_by = requested_by
        self.text_channel = text_channel
        self.started_at = time.time()
        self.played: list[str] = []
        self.names: list[str] = []
        self.listeners_seen: set[str] = set()
        self.source: Optional[CrossfadeSource] = None
        self._alone_grace = alone_grace_s
        self._closing = False
        self._task: Optional[asyncio.Task] = None
        self._rng = random.Random()

    @property
    def guild_id(self) -> int:
        return self.vc.guild.id

    @property
    def channel_name(self) -> str:
        return getattr(self.vc.channel, "name", "voice")

    @property
    def now(self) -> Optional[library.Record]:
        return self.source.current.record if self.source and self.source.current else None

    def _choose(self, deck: Deck) -> Optional[tuple]:
        rec = library.next_record(deck.record, self.crate, self.played, self._rng)
        for _ in range(5):
            if rec is None:
                return None
            seconds = probe_seconds(rec.path)
            if seconds and seconds >= MIN_RECORD_S:
                # Stretched to the tempo of the one playing, as heard (its own stretch included).
                playing = deck.record.bpm * deck.ratio if deck.record.bpm else None
                ratio = library.tempo_ratio(playing, rec.bpm) or 1.0
                return rec, ratio, seconds, gain_db(rec.path)
            self.played.append(rec.path)
            rec = library.next_record(deck.record, self.crate, self.played, self._rng)
        return None

    def _changed(self, record: library.Record) -> None:
        self.played.append(record.path)
        self.names.append(record.name)
        log_action(f"[records] now playing {record.name} ({record.bpm or '?'} bpm, {record.key or '?'})")

    def _humans(self) -> list[str]:
        return [m.display_name for m in getattr(self.vc.channel, "members", []) if not m.bot]

    async def _watch(self) -> None:
        alone_since = None
        while not self._closing:
            await asyncio.sleep(15)
            people = self._humans()
            self.listeners_seen.update(people)
            if people:
                alone_since = None
            elif alone_since is None:
                alone_since = time.time()
            elif time.time() - alone_since >= self._alone_grace:
                log_action("[records] the channel emptied; stopping.")
                await self.stop()
                return
            if not self.vc.is_playing() and not self._closing:
                await self.stop()
                return

    def skip(self) -> None:
        if self.source:
            self.source.skip()

    async def stop(self, disconnect: bool = True) -> None:
        """End the set. `disconnect=False` when something else is taking the
        voice connection over (radio, a live set)."""
        if self._closing:
            return
        self._closing = True
        _sessions.pop(self.guild_id, None)
        try:
            if self.vc.is_playing():
                self.vc.stop()
        except Exception as e:
            log_debug(f"[records] stop playback: {e}")
        if self.source:
            self.source.cleanup()
        if disconnect:
            try:
                await self.vc.disconnect(force=True)
            except Exception as e:
                log_debug(f"[records] disconnect: {e}")
        if self._task and not self._task.done() and self._task is not asyncio.current_task():
            self._task.cancel()
        minutes = (time.time() - self.started_at) / 60
        log_action(f"[records] set ended after {minutes:.1f} min, {len(self.names)} records.")
        self._remember(minutes)

    def _remember(self, minutes: float) -> None:
        if minutes < 1 or not self.names:
            return
        try:
            from utils.core.kaia_expression import remember
            crowd = sorted(self.listeners_seen - {self.requested_by})
            who = ", ".join(([self.requested_by] if self.requested_by else []) + crowd[:5])
            some = ", ".join(self.names[:3]) + ("…" if len(self.names) > 3 else "")
            remember("music",
                     f"[i played records in {self.channel_name} for {minutes:.0f} minutes — "
                     f"{len(self.names)} of them, starting with {some}"
                     f"{'; ' + who + ' listened' if who else ''}.]",
                     channel_id=getattr(self.text_channel, "id", None),
                     title="a records set",
                     detail={"kind": "records", "minutes": round(minutes, 1), "records": self.names,
                             "listeners": sorted(self.listeners_seen)})
        except Exception as e:
            log_debug(f"[records] set not remembered: {e}")

    def stats(self) -> dict:
        nxt = self.source._queued[0].name if self.source and self.source._queued else None
        now = self.now
        return {"now": now.name if now else None, "bpm": now.bpm if now else None,
                "key": now.key if now else None, "genre": now.genre if now else None,
                "next": nxt, "played": len(self.names), "channel": self.channel_name,
                "uptime_min": round((time.time() - self.started_at) / 60), "listeners": len(self._humans())}


async def start_records(channel, crate: list[library.Record], first: library.Record, *,
                        requested_by: str, text_channel=None, fade_s: float = 8.0,
                        alone_grace_s: float = 120.0) -> RecordsSession:
    """Join `channel` and start the set at `first`. Stops whatever was playing there."""
    guild = channel.guild
    if (old := _sessions.get(guild.id)):
        await old.stop()
    try:
        from utils.audio.strudel_session import get_session
        if (synth := get_session(guild.id)):
            await synth.stop()
    except Exception as e:
        log_debug(f"[records] no live set to stop: {e}")
    try:
        from utils.radio import live
        await live.free_voice(guild)
    except Exception as e:
        log_debug(f"[records] radio not stopped: {e}")

    seconds = await asyncio.to_thread(probe_seconds, first.path)
    if not seconds:
        raise RuntimeError(f"could not read {first.name}")
    if not discord.opus.is_loaded():
        try:
            discord.opus._load_default()
        except Exception as exc:
            raise RuntimeError("libopus is not loaded") from exc

    vc = guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        vc = await channel.connect(timeout=30.0, reconnect=True)

    session = RecordsSession(vc, crate, requested_by, text_channel, alone_grace_s)
    deck = Deck(first, 1.0, seconds, gain=await asyncio.to_thread(gain_db, first.path))
    session._changed(first)
    session.source = CrossfadeSource(deck, session._choose, fade_s=fade_s, on_change=session._changed)
    vc.play(session.source, after=lambda e: log_error(f"[records] playback error: {e}") if e else None)
    _sessions[guild.id] = session
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    session._task = asyncio.create_task(session._watch())
    task_registry.register(f"records_watch_{guild.id}", session._task)
    return session


async def stop_all() -> None:
    for s in list(_sessions.values()):
        try:
            await s.stop()
        except Exception as e:
            log_debug(f"[records] stop_all: {e}")
