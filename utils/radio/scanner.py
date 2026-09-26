"""Kaia's local scanner: what the RTL-SDR attached to the bot hears overnight.

Every night between `radio.local.hours` (local, midnight to 6 by default) it
runs the waterfall watch (utils/radio/waterfall.py): the dongle hops the bands
continuously and holds on anything that keys up. Each catch is classified —
voice if Whisper finds words, data if it has a digital voice mode's shape,
otherwise a bare carrier — and written to the ledger (utils/radio/ledger.py):
frequency, what is on it, and which hours it is active. The ledger is seeded
with names: the US-wide channels below (NOAA, FRS/GMRS, MURS, calling
channels, marine 16) and whatever local repeaters the deployment lists under
`radio.local.channels` — local knowledge, so it lives in config, not here.

People talking — repeaters, walkie-talkies, Baofengs on FRS/GMRS/MURS — is
the point; pagers and data are logged but not transcribed.

"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.radio import ledger, rtl

MHZ = 1_000_000

#: (name, start_hz, end_hz, service)
BANDS = [
    ("2m", 144 * MHZ, 148 * MHZ, "amateur"),
    ("1.25m", 222 * MHZ, 225 * MHZ, "amateur"),
    ("vhf-business", 150_800_000, 158_000_000, "business / MURS / marine"),
    ("railroad", 160_200_000, 161_600_000, "railroad"),
    ("noaa", 162_400_000, 162_560_000, "weather"),
    ("70cm", 420 * MHZ, 450 * MHZ, "amateur"),
    ("uhf-business", 450 * MHZ, 462_500_000, "business"),
    ("frs-gmrs", 462_500_000, 467_800_000, "FRS / GMRS"),
    ("900", 902 * MHZ, 928 * MHZ, "amateur / ISM"),
]


def _mhz(x: float) -> int:
    return int(round(x * MHZ))


FRS_GMRS = [462.5625, 462.5875, 462.6125, 462.6375, 462.6625, 462.6875, 462.7125,
            467.5625, 467.5875, 467.6125, 467.6375, 467.6625, 467.6875, 467.7125,
            462.5500, 462.5750, 462.6000, 462.6250, 462.6500, 462.6750, 462.7000, 462.7250]
MURS = [151.820, 151.880, 151.940, 154.570, 154.600]
NOAA = [162.400, 162.425, 162.450, 162.475, 162.500, 162.525, 162.550]


def seed_channels() -> list[dict]:
    rows = []
    # Local repeaters from config: [{mhz: 146.86, label: "...", mode: fm|digital}]
    for c in _cfg("channels", []) or []:
        try:
            f = _mhz(float(c["mhz"]))
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({"freq_hz": f, "band": _band_of(f), "service": c.get("service") or _service_of(f),
                     "label": str(c.get("label") or ""), "mode": str(c.get("mode") or "fm")})
    rows += [{"freq_hz": _mhz(f), "band": "frs-gmrs", "service": "FRS / GMRS",
              "label": f"FRS/GMRS ch {i}"} for i, f in enumerate(FRS_GMRS, 1)]
    rows += [{"freq_hz": _mhz(f), "band": "vhf-business", "service": "MURS", "label": f"MURS ch {i}"}
             for i, f in enumerate(MURS, 1)]
    rows += [{"freq_hz": _mhz(f), "band": "noaa", "service": "weather", "label": f"NOAA WX {i}"}
             for i, f in enumerate(NOAA, 1)]
    rows += [{"freq_hz": _mhz(146.520), "band": "2m", "service": "amateur", "label": "2m national simplex calling"},
             {"freq_hz": _mhz(446.000), "band": "70cm", "service": "amateur", "label": "70cm national simplex calling"},
             {"freq_hz": _mhz(156.800), "band": "vhf-business", "service": "marine", "label": "Marine ch 16 (distress / calling)"}]
    return rows


def _band_of(freq_hz: int) -> str:
    for name, lo, hi, _ in BANDS:
        if lo <= freq_hz <= hi:
            return name
    return ""


def _near(freq_hz: int, channels_mhz: list, tol_hz: int = 3000) -> bool:
    return any(abs(freq_hz - _mhz(f)) <= tol_hz for f in channels_mhz)


def _service_of(freq_hz: int) -> str:
    # The named channels first: FRS/GMRS is 22 channels inside 462.5-467.8,
    # and the rest of that span (463-467) is business radio.
    if _near(freq_hz, FRS_GMRS):
        return "FRS / GMRS"
    if _near(freq_hz, MURS):
        return "MURS"
    if _near(freq_hz, NOAA):
        return "weather"
    if 462_500_000 <= freq_hz <= 467_800_000:
        return "business"
    for name, lo, hi, service in BANDS:
        if lo <= freq_hz <= hi:
            return service
    return ""


def _snap(freq_hz: int, step: int = 6250) -> int:
    return int(round(freq_hz / step) * step)


def _cfg(key: str, default):
    return config.get(f"radio.local.{key}", default)


def within_hours(now: Optional[datetime] = None) -> bool:
    """Inside radio.local.hours, local time ("00:00-06:00")."""
    now = now or datetime.now()
    try:
        a, b = str(_cfg("hours", "00:00-06:00")).split("-")
        start = int(a[:2]) * 60 + int(a[3:5])
        end = int(b[:2]) * 60 + int(b[3:5])
    except (ValueError, IndexError):
        start, end = 0, 360
    minute = now.hour * 60 + now.minute
    return start <= minute < end if start <= end else (minute >= start or minute < end)


def _clips_dir() -> Path:
    from utils.radio import log as radio_log
    d = radio_log.clips_dir().parent / "local_clips"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_clip(audio, freq_hz: int, when: float) -> Optional[str]:
    """Opus clip of a catch; keeps the newest 300."""
    import subprocess
    d = _clips_dir()
    name = f"{time.strftime('%Y%m%dT%H%M%S', time.localtime(when))}_{freq_hz}.ogg"
    try:
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "s16le", "-ar",
                        str(rtl.SAMPLE_RATE), "-ac", "1", "-i", "-", "-c:a", "libopus", "-b:a", "24k",
                        str(d / name)], input=audio.tobytes(), capture_output=True, timeout=60, check=True)
    except Exception as e:
        log_debug(f"[scanner] clip not saved: {e}")
        return None
    for old in sorted(d.glob("*.ogg"))[:-300]:
        old.unlink(missing_ok=True)
    return name


def _transcribe(audio) -> str:
    import tempfile
    import wave
    from utils.radio import transcribe
    if not transcribe.available():
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "catch.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rtl.SAMPLE_RATE)
            w.writeframes(audio.tobytes())
        return transcribe.transcribe_file(p, language=None).strip()


MIN_CATCH_S = 1.5


def looks_like_speech(text: str) -> bool:
    """Words, not Whisper looping on noise: "Stavros Stavrides, Stavros
    Stavrides, Stavros Stavrides" came off a carrier on 463.7575."""
    words = [w.strip(".,!?\"'").lower() for w in text.split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return False
    if len(set(words)) / len(words) < 0.5:
        return False
    return text.strip().lower().rstrip(".") not in ("thank you", "thanks for watching", "you")
TRANSCRIBE_PER_NIGHT = 60
_transcribed = {"date": "", "count": 0}


def classify(catch) -> None:
    """A catch from the waterfall → the ledger: voice if Whisper finds words,
    data if it has a digital mode's shape, otherwise a bare carrier. Runs on
    the watcher's worker thread."""
    if catch.seconds < MIN_CATCH_S or len(catch.audio) < rtl.SAMPLE_RATE:
        return                                   # a kerchunk
    m = rtl.measure(catch.audio, catch.freq_hz)
    kind, transcript = ("data" if m.digital else "carrier"), ""
    today = datetime.now().strftime("%Y-%m-%d")
    if _transcribed["date"] != today:
        _transcribed.update(date=today, count=0)
    if not m.digital and _transcribed["count"] < TRANSCRIBE_PER_NIGHT:
        _transcribed["count"] += 1
        text = _transcribe(catch.audio)
        if looks_like_speech(text):
            kind, transcript = "voice", text
    clip = _save_clip(catch.audio, catch.freq_hz, catch.started) if kind != "carrier" else None
    ledger.record(catch.freq_hz, kind, round(catch.seconds, 1), m.rms, m.hf_ratio, clip, transcript,
                  _band_of(catch.freq_hz), _service_of(catch.freq_hz), catch.started)
    label = (ledger.channel(catch.freq_hz) or {}).get("label") or _service_of(catch.freq_hz)
    log_info(f"[scanner] {kind} on {catch.freq_hz / MHZ:.4f} MHz ({label}), {catch.seconds:.0f}s"
             + (f": {transcript[:80]}" if transcript else ""))
    if _along:
        icon = {"voice": "🗣️", "data": "📟", "carrier": "〰️"}.get(kind, "📻")
        _announce(f"{icon} **{catch.freq_hz / MHZ:.4f} MHz** · {label} · {kind}, {catch.seconds:.0f}s"
                  + (f"\n> {transcript[:300]}" if transcript else ""))


_running = False

# ── Listen along ────────────────────────────────────────────────────────────
# Someone in a voice channel hearing the scan as it happens: a tick per hop and
# the channel whenever it holds, with each catch posted to the text channel.
# While anyone listens along the watch runs even outside the nightly hours.

import queue as _queue
import threading as _threading

_along: dict = {}                    # guild_id -> {"vc", "text", "loop"}
_audio: "_queue.Queue" = _queue.Queue(maxsize=600)


def _sink(chunk) -> None:
    if not _along:
        return
    try:
        _audio.put_nowait(chunk)
    except _queue.Full:
        pass                         # nobody draining: drop rather than lag


def listening_along() -> bool:
    return bool(_along)


class ScanAudio:
    """discord.AudioSource over the watcher's 12 kHz audio: 20 ms frames of
    48 kHz stereo, silence when nothing is queued."""

    FRAME_12K = 240

    def __init__(self):
        import numpy as _np
        self._np = _np
        self._buf = _np.zeros(0, _np.int16)

    def is_opus(self) -> bool:
        return False

    def read(self) -> bytes:
        np_ = self._np
        while len(self._buf) < self.FRAME_12K:
            try:
                self._buf = np_.concatenate([self._buf, _audio.get_nowait()])
            except _queue.Empty:
                self._buf = np_.concatenate([self._buf, np_.zeros(self.FRAME_12K - len(self._buf), np_.int16)])
        frame, self._buf = self._buf[:self.FRAME_12K], self._buf[self.FRAME_12K:]
        up = np_.repeat(frame, 4)                              # 12 kHz -> 48 kHz
        return np_.column_stack([up, up]).astype(np_.int16).tobytes()

    def cleanup(self) -> None:
        pass


async def start_listen_along(voice_channel, text_channel, requested_by: str) -> None:
    import discord
    guild = voice_channel.guild
    from utils.radio import live
    await live.stop(guild.id)
    vc = guild.voice_client
    if vc and vc.is_connected():
        if vc.is_playing():
            vc.stop()
        await vc.move_to(voice_channel)
    else:
        vc = await voice_channel.connect(timeout=30.0, reconnect=True)
    while not _audio.empty():
        _audio.get_nowait()
    vc.play(discord.PCMAudio(_PcmStream(ScanAudio())))
    _along[guild.id] = {"vc": vc, "text": text_channel, "loop": asyncio.get_running_loop()}
    log_info(f"[scanner] {requested_by} is listening along in {voice_channel.name}")
    if not _running and rtl.available() and not rtl.DEVICE.locked():
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        ledger.seed(seed_channels())
        task_registry.register(f"scanner_watch_{int(time.time())}", asyncio.create_task(_watch()))


async def stop_listen_along(guild_id: int) -> bool:
    entry = _along.pop(guild_id, None)
    if not entry:
        return False
    vc = entry["vc"]
    if vc.is_playing():
        vc.stop()
    if vc.is_connected():
        await vc.disconnect(force=True)
    return True


class _PcmStream:
    """A file-like wrapper so discord.PCMAudio can pull frames from ScanAudio."""

    def __init__(self, source: ScanAudio):
        self.source = source

    def read(self, n: int) -> bytes:
        return self.source.read()


def _announce(text: str) -> None:
    """Post a catch to every listen-along text channel. From the worker thread."""
    import discord
    for entry in list(_along.values()):
        try:
            asyncio.run_coroutine_threadsafe(
                entry["text"].send(embed=discord.Embed(description=text, color=0x2F7D6D)), entry["loop"])
        except Exception as e:
            log_debug(f"[scanner] announce failed: {e}")


async def _watch() -> None:
    """Hold the dongle and run the waterfall until the window closes or a live
    listen asks for it."""
    import threading
    from utils.radio.waterfall import Watcher
    global _running
    _running = True
    stop = threading.Event()
    try:
        async with rtl.DEVICE:
            rtl.YIELD.clear()
            watcher = Watcher(classify, gain_db=float(_cfg("gain", rtl.DEFAULT_GAIN)), stop=stop, sink=_sink)
            job = asyncio.create_task(asyncio.to_thread(watcher.run))
            log_info("[scanner] waterfall watch started")
            while not job.done():
                if rtl.YIELD.is_set() or not _cfg("enabled", True) or \
                        not (within_hours() or listening_along()):
                    stop.set()
                await asyncio.sleep(1)
            await job
            log_info(f"[scanner] waterfall watch stopped after {watcher.passes} passes")
    except Exception as e:
        log_warning(f"[scanner] waterfall watch failed: {type(e).__name__}: {e}")
    finally:
        from utils.radio import transcribe
        transcribe.release_if_idle()
        _running = False


def tick(now: Optional[datetime] = None) -> bool:
    """Start the watch if it's scanning hours and the dongle is free. Called
    every minute by the radio task. Returns whether it started."""
    if _running or not _cfg("enabled", True) or not rtl.available() or rtl.DEVICE.locked():
        return False
    if not within_hours(now):
        return False
    ledger.seed(seed_channels())
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    task_registry.register(f"scanner_watch_{int(time.time())}", asyncio.create_task(_watch()))
    return True


def running() -> bool:
    return _running
