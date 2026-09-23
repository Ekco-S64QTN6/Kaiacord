"""
Voice-channel session driving the Strudel engine through a performance.

One session per guild. The session owns the engine, the capture, the voice
connection and the arrangement clock, and a background task advances the
performance so parts come and go over minutes instead of one pattern looping.
"""

from __future__ import annotations

import asyncio
import time

import discord

from utils.audio import dj
from utils.audio.performance import Performance, build
from utils.audio.strudel_engine import StrudelEngine, monitor_to_speakers
from utils.audio.strudel_patterns import GENRES
from utils.audio.strudel_source import StrudelAudioSource
from utils.infrastructure.logging.kaia_logger import (log_action, log_debug,
                                                      log_error, log_info,
                                                      log_warning)

_sessions: dict[int, "MusicSession"] = {}
WATCHDOG_PERIOD_S = 10.0


def _cfg(key: str, default):
    try:
        from utils.infrastructure.system.yaml_config import config
        return config.get(f"music.{key}", default)
    except Exception:
        return default


class MusicSession:
    def __init__(self, vc: discord.VoiceClient, engine: StrudelEngine,
                 source: StrudelAudioSource, perf: Performance,
                 genre: str, requested_by: str, text_channel=None):
        self.vc = vc
        self.engine = engine
        self.source = source
        self.perf = perf
        self.genre = genre
        self.requested_by = requested_by
        self.text_channel = text_channel
        self.started_at = time.time()
        self._closing = False
        self._alone_since: float | None = None
        self._restore: tuple[float, list[str]] | None = None
        self.listeners_seen: set[str] = set()
        self.requests = 0
        self._task = asyncio.create_task(self._run())

    @property
    def guild_id(self) -> int:
        return self.vc.guild.id

    @property
    def channel_name(self) -> str:
        return getattr(self.vc.channel, "name", "unknown")

    def _humans(self) -> int:
        humans = [m for m in (getattr(self.vc.channel, "members", []) or []) if not m.bot]
        self.listeners_seen.update(getattr(m, "display_name", str(m)) for m in humans)
        return len(humans)

    async def _push(self) -> bool:
        """Send the current program to the browser, off the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.engine.play, self.perf.code())

    async def _label(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.engine.set_label, self.genre, text)

    async def request(self, text: str, who: str = "") -> "dj.RequestResult":
        """A listener's request, applied to the running set."""
        result = dj.apply_request(text, self.perf, GENRES[self.genre]["cpm"])
        if result.changed:
            if not await self._push():
                log_warning(f"[music] request '{text}' produced a program Strudel rejected.")
                return dj.RequestResult(True, "that didn't take — the engine refused it.")
            self.requests += 1
            await self._label(result.reply)
            log_action(f"[music] request from {who or 'someone'}: '{text}' → {result.reply}")
            if result.restore_after_s:
                self._restore = (time.time() + result.restore_after_s, result.restore_lanes)
        return result

    async def _run(self) -> None:
        """Advance the arrangement and keep the connection healthy."""
        try:
            while not self._closing:
                await asyncio.sleep(WATCHDOG_PERIOD_S)
                if self._closing:
                    return

                if not self.vc.is_connected():
                    log_warning(f"[music] voice dropped in {self.channel_name}.")
                    await self.stop()
                    return

                # The operator can close the player window at any time, and with
                # show_window on that is a normal thing to do. Treat it as "end
                # the set", not as a pattern failure — otherwise the session
                # stays up streaming silence and logs an error every tick.
                if not self.engine.alive():
                    if self.text_channel:
                        try:
                            await self.text_channel.send(
                                "the player window was closed, so i stopped the set.")
                        except Exception:
                            pass
                    await self.stop()
                    return

                # Move the performance on. Strudel hot-swaps at the next cycle
                # boundary, measured gapless: a continuous pad across two live
                # re-evaluations never fell below 0.20 peak.
                # Hold off while somebody is typing in the editor. Applying
                # over a half-finished human edit is worse than being a beat
                # late with the next move.
                if self._restore and time.time() >= self._restore[0]:
                    for name in self._restore[1]:
                        if name in self.perf.lanes:
                            self.perf.lanes[name].live = True
                    self._restore = None
                    if await self._push():
                        await self._label("and the beat's back")
                        log_info("[music] drop over; drums back in.")

                if self._held_for_human():
                    pass
                elif self.perf.advance(WATCHDOG_PERIOD_S):
                    d = self.perf.describe()
                    if await self._push():
                        log_info(f"[music] {self.genre}: {d['section']}"
                                 f"  [{'+'.join(d['lanes']) or 'silent'}]")
                        await self._label(d["section"])
                    else:
                        log_warning(f"[music] '{d['section']}' was rejected; "
                                    f"holding the previous state.")

                if not self.vc.is_playing() and not self.vc.is_paused():
                    log_warning("[music] playback stopped; restarting source.")
                    try:
                        self.vc.play(self.source)
                    except Exception as exc:
                        log_error(f"[music] restart failed: {exc}")
                        await self.stop()
                        return

                grace = float(_cfg("alone_grace_seconds", 120))
                if self._humans() == 0:
                    if self._alone_since is None:
                        self._alone_since = time.time()
                        log_info(f"[music] alone in {self.channel_name}; leaving in "
                                 f"{grace:.0f}s.")
                    elif time.time() - self._alone_since > grace:
                        log_action(f"[music] left {self.channel_name} — nobody listening.")
                        await self.stop()
                        return
                elif self._alone_since is not None:
                    self._alone_since = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_error(f"[music] session loop failed: {exc}")

    def _held_for_human(self) -> bool:
        """Pause the script while the editor has unapplied human changes."""
        try:
            if not self.engine.human_edited():
                self._held = 0
                return False
        except Exception:
            return False
        self._held = getattr(self, "_held", 0) + 1
        # Do not wait forever: if the editor is left dirty and abandoned, the
        # performance would freeze on one state for the rest of the session.
        if self._held * WATCHDOG_PERIOD_S > float(_cfg("human_edit_grace_seconds", 180)):
            log_info("[music] resuming the script; the editor has been left dirty.")
            self._held = 0
            return False
        return True

    async def set_genre(self, genre: str) -> None:
        self.genre = genre
        self.perf = build_for_mood(genre)
        self._restore = None
        await self._push()
        log_action(f"[music] switched to {genre}.")

    async def stop(self) -> None:
        if self._closing:
            return
        self._closing = True
        _sessions.pop(self.guild_id, None)
        for step, what in (
            (lambda: self.engine.stop(), "stop pattern"),
            (lambda: self.vc.is_playing() and self.vc.stop(), "stop playback"),
            (lambda: self.source.cleanup(), "cleanup source"),
            (lambda: self.engine.close(), "close engine"),
        ):
            try:
                step()
            except Exception as exc:
                log_debug(f"[music] {what}: {exc}")
        try:
            await self.vc.disconnect(force=True)
        except Exception as exc:
            log_debug(f"[music] disconnect: {exc}")
        if self._task and not self._task.done():
            self._task.cancel()
        minutes = (time.time() - self.started_at) / 60
        log_action(f"[music] session ended after {minutes:.1f} min.")
        self._remember(minutes)

    def _remember(self, minutes: float) -> None:
        """So she knows she played, for whom, and for how long."""
        if minutes < 1:
            return
        try:
            from utils.core.kaia_expression import remember
            who = sorted(self.listeners_seen - {self.requested_by})
            crowd = ", ".join([self.requested_by] + who[:5]) if self.requested_by else ", ".join(who[:6])
            took = f" and took {self.requests} request{'s' if self.requests != 1 else ''}" if self.requests else ""
            remember("music",
                     f"[i played a {self.genre} set in {self.channel_name} for {minutes:.0f} minutes"
                     f"{' — ' + crowd + ' listened' if crowd else ''}{took}.]",
                     channel_id=getattr(self.text_channel, "id", None),
                     title=f"a {self.genre} set",
                     detail={"genre": self.genre, "minutes": round(minutes, 1),
                             "listeners": sorted(self.listeners_seen), "requests": self.requests})
        except Exception as exc:
            log_debug(f"[music] set not remembered: {exc}")

    def stats(self) -> dict:
        return {
            "channel": self.channel_name, "genre": self.genre,
            "requested_by": self.requested_by,
            "uptime_min": round((time.time() - self.started_at) / 60.0, 1),
            "listeners": self._humans(),
            **self.perf.describe(), **self.source.stats(),
        }


def build_for_mood(genre: str) -> Performance:
    """The genre's performance, played at the tempo her mood sets."""
    from utils.core.kaia_art_intent import mood
    perf = build(GENRES[genre])
    perf.cpm = dj.tempo_for_mood(perf.cpm, mood())
    return perf


def get_session(guild_id: int) -> MusicSession | None:
    return _sessions.get(guild_id)


def active_sessions() -> list[MusicSession]:
    return list(_sessions.values())


async def start_session(channel, *, genre: str, requested_by: str,
                        text_channel=None) -> MusicSession:
    guild_id = channel.guild.id
    if (existing := _sessions.get(guild_id)):
        await existing.stop()

    if not discord.opus.is_loaded():
        try:
            discord.opus._load_default()
        except Exception as exc:
            raise RuntimeError("libopus is not loaded") from exc

    loop = asyncio.get_running_loop()
    engine = StrudelEngine(show_window=bool(_cfg("show_window", False)))
    # Playwright's sync API blocks; keep it off the event loop entirely.
    await loop.run_in_executor(None, engine.start)
    if _cfg("monitor_on_speakers", False):
        monitor_to_speakers(True)

    perf = build_for_mood(genre)
    await loop.run_in_executor(None, engine.play, perf.code())
    # Let the first section come up before Discord starts pulling frames.
    await asyncio.sleep(float(_cfg("prime_seconds", 6.0)))

    vc = channel.guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(channel)
    else:
        vc = await channel.connect(timeout=30.0, reconnect=True)

    source = StrudelAudioSource(engine)
    vc.play(source, after=lambda e: log_error(f"[music] playback error: {e}") if e else None)

    session = MusicSession(vc, engine, source, perf, genre, requested_by, text_channel)
    _sessions[guild_id] = session
    log_action(f"[music] '{genre}' started in {channel.name} for {requested_by}.")
    return session


async def stop_all() -> None:
    for s in list(_sessions.values()):
        try:
            await s.stop()
        except Exception as exc:
            log_debug(f"[music] stop_all: {exc}")
