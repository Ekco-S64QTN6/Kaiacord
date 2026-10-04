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
import contextlib
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_warning
from utils.infrastructure.system.gc_quiet import settle
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


def snap_channel(freq_hz: int) -> int:
    """The channel a catch is on. The waterfall rounds to 2.5 kHz, which split
    one transmitter across neighbouring rows (462.2775 / 462.275). Amateur
    bands sit on a 5 kHz grid (146.860); land-mobile, FRS/GMRS and MURS on
    6.25 kHz (462.5625). Named channels win over the grid."""
    for c in _NAMED_CACHE.get("rows") or []:
        if abs(c - freq_hz) <= 3000:
            return c
    # A channel already heard, within a grid step: a wide signal straddles the
    # grid and would otherwise alternate between two neighbouring rows.
    # Only rows on the grid (or listed) count: an off-grid row written before
    # snapping would otherwise keep attracting its own catches.
    def on_grid(c: dict) -> bool:
        f = c["freq_hz"]
        return c.get("source") == "listed" or _snap(f, _step(f)) == f
    heard = [c["freq_hz"] for c in ledger.channels()
             if c["hits"] and abs(c["freq_hz"] - freq_hz) <= 4000 and on_grid(c)]
    if heard:
        return min(heard, key=lambda f: abs(f - freq_hz))
    return _snap(freq_hz, _step(freq_hz))


def _step(freq_hz: int) -> int:
    return 5000 if _service_of(freq_hz) == "amateur" else 6250


_NAMED_CACHE: dict = {}


def _cfg(key: str, default):
    return config.get(f"radio.local.{key}", default)


_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def due_net(now: Optional[datetime] = None) -> Optional[dict]:
    """A listed net whose window is open now (radio.local.nets, local time):
    {mhz, day, time, minutes, label}. A net pre-empts the waterfall and runs
    outside the nightly hours: the scanner sits on that one channel."""
    now = now or datetime.now()
    for net in _cfg("nets", []) or []:
        try:
            day = str(net["day"]).lower()[:3]
            h, m = (int(x) for x in str(net["time"]).split(":"))
            start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            minutes = int(net.get("minutes", 60))
            freq = _mhz(float(net["mhz"]))
        except (KeyError, TypeError, ValueError):
            continue
        if _DAYS[now.weekday()] == day and start <= now < start + timedelta(minutes=minutes):
            return {"freq_hz": freq, "label": str(net.get("label") or ""), "until": start.timestamp() + minutes * 60}
    return None


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
    shared = radio_log.clips_dir()               # clips/ or, under pytest, clips.test/
    d = shared.parent / ("local_clips.test" if shared.name.endswith(".test") else "local_clips")
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
    rotated = sorted(d.glob("*.ogg"))[:-300]
    for old in rotated:
        old.unlink(missing_ok=True)
        old.with_suffix(".png").unlink(missing_ok=True)          # its spectrogram
    ledger.forget_clips([p.name for p in rotated])
    return name


@contextlib.contextmanager
def _wav(audio):
    import tempfile
    import wave
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "catch.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rtl.SAMPLE_RATE)
            w.writeframes(audio.tobytes())
        yield p


# Dispatch channels get a vocabulary prompt: it took valid map letters from 48%
# to 77% over 52 real clips and recovered calls the plain pass missed. Word
# lists, never example sentences — sentences with numbers and street names
# were copied into the transcripts ("Westview 38" became "11, rescue 38", a
# cross street nobody said appeared). Ham bands get none: a ham word list
# clipped a conversation and, on a hard clip, came back as the list itself.
DISPATCH_PROMPT = ("Fire and EMS dispatch. Engine, truck, rescue, medic, battalion, units, medical emergency, "
                   "cross of, map, northbound, southbound, eastbound, westbound, service road, number. Adam, Boy, "
                   "Charles, David, Edward, Frank, George, Henry, Ida, John, King, Lincoln, Mary, Nora, Ocean, Paul, "
                   "Queen, Robert, Sam, Tom, Union, Victor, William, X-ray, Young, Zebra.")
HAM_BANDS = [(144_000_000, 148_000_000), (222_000_000, 225_000_000), (420_000_000, 450_000_000),
             (902_000_000, 928_500_000)]


#: A transcript this much made of the prompt's own words is the prompt read
#: back, not the channel: real dispatch measured 0.57 at most, echoes 1.00.
ECHO_SHARE = 0.8


def prompt_for(freq_hz: int) -> Optional[str]:
    return None if any(lo <= freq_hz < hi for lo, hi in HAM_BANDS) else DISPATCH_PROMPT


def prompt_echo(text: str, prompt: Optional[str]) -> bool:
    if not prompt:
        return False
    vocab = {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]+", prompt)}
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z-]+", text)]
    return len(words) >= 6 and sum(w in vocab for w in words) / len(words) >= ECHO_SHARE


def _transcribe(audio, speech_only: bool = True, freq_hz: int = 0) -> str:
    """`speech_only` keeps only segments Whisper scores as speech, which is
    what stops it writing words onto a carrier; it also scores some real
    repeater voice low, so a strong, speech-like catch gets a second pass
    without it. Whisper hears only the carried audio (`speech_audio`): a clip
    that was mostly squelch tail gave it hiss to write words onto."""
    from utils.radio import transcribe
    from utils.radio.waterfall import speech_audio
    if not transcribe.available():
        return ""
    speech = speech_audio(audio)
    if len(speech) >= rtl.SAMPLE_RATE // 2:
        audio = speech
    prompt = prompt_for(freq_hz) if freq_hz else None
    with _wav(audio) as p:
        # English, not auto-detect: on static, auto-detect picked Norwegian and
        # Whisper produced a subtitle credit. radio.local.language overrides.
        run = transcribe.transcribe_speech if speech_only else transcribe.transcribe_file
        text = run(p, language=_cfg("language", "en"), prompt=prompt).strip()
        if prompt_echo(text, prompt):
            log_debug(f"[scanner] the prompt came back as the transcript on {freq_hz / MHZ:.4f}; again without it")
            text = run(p, language=_cfg("language", "en")).strip()
        return text


# A Morse ID keys fast on one tone: 150–257 key-downs a minute on 145.690's and
# 448.775's IDs, where voice measured 133 or fewer.
MORSE_KEYS_PER_MIN = 140
MORSE_PROMINENCE_DB = 5.5
ID_CLIP_EVERY_S = 6 * 3600       # an ID sent every few minutes is kept this often per channel
_id_clips: dict = {}             # freq -> when its last Morse ID clip was kept


MORSE_ON_STD_DB = 4.0            # a keyed tone's "on" level: IDs held 0.6–3.9 dB, voice 5.1 and up


def _steady_keyed_tone(audio) -> bool:
    """One fixed tone switching fully on and off, at the same level each time
    it's on. keyed_tone, built for shortwave, picked 2440 Hz on W5EBQ's
    1045 Hz ID and diluted its key rate over the squelch tail."""
    import numpy as np
    from utils.radio.waterfall import FRAME, carried
    on, _ = carried(audio)
    if on.sum() < 50:
        return False
    first, last = np.where(on)[0][[0, -1]]
    x = audio[first * FRAME:(last + 1) * FRAME].astype(float)
    n = 480                                                         # 40 ms, 25 Hz bins
    k = len(x) // n
    if k < 10:
        return False
    sp = np.abs(np.fft.rfft(x[:k * n].reshape(k, n) * np.hanning(n), axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / rtl.SAMPLE_RATE)
    band = np.where((f >= 400) & (f <= 1600))[0]
    b = band[np.argmax(sp[:, band].mean(axis=0))]
    level = 10 * np.log10(sp[:, b - 1:b + 2].sum(axis=1) + 1e-9)
    lo, hi = np.percentile(level, 10), np.percentile(level, 90)
    up = level > (lo + hi) / 2
    keys_per_s = np.count_nonzero(np.diff(up.astype(int)) == 1) / (k * n / rtl.SAMPLE_RATE)
    # The level while on, away from the edges: a frame a key-down or key-up
    # falls in is only partly on.
    inside = up[1:-1] & up[:-2] & up[2:]
    if inside.sum() < 3:
        return False
    return hi - lo >= 20 and keys_per_s >= 1.5 and float(np.std(level[1:-1][inside])) <= MORSE_ON_STD_DB


def morse_id(audio) -> bool:
    from utils.radio import watch
    if _steady_keyed_tone(audio):
        return True
    with _wav(audio) as p:
        t = watch.keyed_tone(p)
    return t.get("keys_per_min", 0) >= MORSE_KEYS_PER_MIN and t.get("prominence_db", 0) >= MORSE_PROMINENCE_DB


MIN_CATCH_S = 1.5
# Under this much carrier in the audio a catch was hiss that tripped the
# trigger: nothing is transcribed or kept, and it's ledgered as noise. A
# channel configured `mode: digital` is exempt: its audio is hiss-shaped. The
# 463.5125's data bursts hold 0.1–0.3 s of carrier; static held 0.0.
STATIC_BELOW_S = 0.1


def looks_like_speech(text: str) -> bool:
    """Words, not Whisper looping on noise: "Stavros Stavrides, Stavros
    Stavrides, Stavros Stavrides" came off a carrier on 463.7575."""
    words = [w.strip(".,!?\"'").lower() for w in text.split()]
    words = [w for w in words if w]
    if len(words) < 3:
        return False
    # Whisper's stock filler, however many times over: "Thank you. Thank you"
    # came off three minutes of hiss on 457.606 and passed as half-unique.
    rest = " " + " ".join(words) + " "
    for filler in (" thank you ", " thanks for watching ", " thanks ", " you ", " bye "):
        while filler in rest:
            rest = rest.replace(filler, " ")
    if len(rest.split()) < 2:
        return False
    # A loop is three or more of the same words; dispatch reads every address
    # twice, and "…Street and South Market Street", twice, is 42% unique.
    if len(set(words)) / len(words) < 0.4:
        return False
    low = text.strip().lower()
    if any(p in low for p in ("teksting av", "subtitles by", "amara.org", "nicolai winther")):
        return False
    # Broadcast sign-offs Whisper writes onto a carrier: "We'll be right back."
    # came off 445.51 with nothing on it.
    return low.rstrip(".!") not in ("thank you", "thanks for watching", "you", "we'll be right back",
                                    "we will be right back", "stay tuned", "thanks for listening")
TRANSCRIBE_PER_NIGHT = 60
_transcribed = {"date": "", "count": 0}


QUIET_CHANNEL_HITS = 8       # catches with no voice before a channel is transcribed only now and then
RECHECK_EVERY = 10
_pinned: Optional[dict] = None   # the net being watched, while one is


def _on_net(freq_hz: int) -> bool:
    return _pinned is not None and abs(freq_hz - _pinned["freq_hz"]) <= 5000


def classify(catch) -> None:
    """A catch from the waterfall → the ledger: voice if Whisper finds words,
    data if it has a digital mode's shape, otherwise a bare carrier. Runs on
    the scanner-classify thread, fed from the watcher's child process.

    A catch on a net being watched is always transcribed and always clipped:
    the nightly budget and the quiet-channel rule are for the open scan, and a
    net is exactly what someone will want to play back."""
    if catch.seconds < MIN_CATCH_S or len(catch.audio) < rtl.SAMPLE_RATE:
        return                                   # a kerchunk
    if not _NAMED_CACHE.get("rows"):
        _NAMED_CACHE["rows"] = [c["freq_hz"] for c in seed_channels()]
    catch.freq_hz = snap_channel(catch.freq_hz)
    net = _on_net(catch.freq_hz)
    from utils.radio.waterfall import carried_audio
    signal = carried_audio(catch.audio)
    digital = any(c.get("mode") == "digital" and abs(c["freq_hz"] - catch.freq_hz) <= 3000 for c in seed_channels())
    # Measured over the carrier alone: the squelch tail and the gaps of a
    # followed conversation are hiss, which has a digital mode's shape.
    m = rtl.measure(catch.audio if digital else signal, catch.freq_hz)
    if not net and not digital and len(signal) / rtl.SAMPLE_RATE < STATIC_BELOW_S:
        # Whisper writes words onto static ("We'll be right back." on 445.51),
        # so it never gets the chance.
        ledger.record(catch.freq_hz, "noise", round(catch.seconds, 1), m.rms, m.hf_ratio, None, "",
                      _band_of(catch.freq_hz), _service_of(catch.freq_hz), catch.started)
        log_debug(f"[scanner] noise on {catch.freq_hz / MHZ:.4f} MHz, {catch.seconds:.0f}s: no carrier in the audio")
        return
    known = ledger.channel(catch.freq_hz) or {}
    # A channel that keys up every minute with no words (telemetry, a trunked
    # system's data) would spend the night's transcriptions in an hour.
    quiet_channel = not net and known.get("hits", 0) >= QUIET_CHANNEL_HITS and not known.get("voice") \
        and known.get("hits", 0) % RECHECK_EVERY
    # Packet radio (APRS) is in-band audio tones, which the digital-shape
    # measure cannot see: 166 APRS bursts in one night were filed as carriers,
    # and each spent a transcription.
    from utils.radio.waterfall import is_packet
    packet = not net and is_packet(catch.audio) and not morse_id(catch.audio)
    kind, transcript = ("data" if m.digital or packet else "carrier"), ""
    today = datetime.now().strftime("%Y-%m-%d")
    if _transcribed["date"] != today:
        _transcribed.update(date=today, count=0)
    from utils.radio.waterfall import voice_like
    speechlike = voice_like(catch.audio)
    if net or (not m.digital and not packet and not quiet_channel and _transcribed["count"] < TRANSCRIBE_PER_NIGHT):
        if not net:
            _transcribed["count"] += 1
        text = _transcribe(catch.audio, freq_hz=catch.freq_hz)
        if not looks_like_speech(text) and speechlike and not morse_id(catch.audio):
            text = _transcribe(catch.audio, speech_only=False, freq_hz=catch.freq_hz)
        if looks_like_speech(text):
            kind, transcript = "voice", text
    # Only what's worth hearing is kept: voice, a net, and a carrier that sounds
    # like speech (a spoken or Morse ID, or words Whisper missed). Data bursts
    # and bare carriers keep no clip; the ledger has their timing and hours. A
    # Morse ID repeats every few minutes, so one is kept per channel per
    # ID_CLIP_EVERY_S.
    keep = kind == "voice" or net
    if not keep and kind == "carrier" and speechlike:
        keep = True
        if morse_id(catch.audio):
            recent = [f for f, t in _id_clips.items()
                      if abs(f - catch.freq_hz) <= 5000 and catch.started - t < ID_CLIP_EVERY_S]
            keep = not recent
            if keep:
                _id_clips[catch.freq_hz] = catch.started
    clip = _save_clip(catch.audio, catch.freq_hz, catch.started) if keep else None
    ledger.record(catch.freq_hz, kind, round(catch.seconds, 1), m.rms, m.hf_ratio, clip, transcript,
                  _band_of(catch.freq_hz), _service_of(catch.freq_hz), catch.started)
    label = (ledger.channel(catch.freq_hz) or {}).get("label") or _service_of(catch.freq_hz)
    # Carriers are routine and frequent: below the dashboard's live log.
    (log_debug if kind == "carrier" else log_info)(
        f"[scanner] {kind} on {catch.freq_hz / MHZ:.4f} MHz ({label}), {catch.seconds:.0f}s"
        + (f": {transcript[:80]}" if transcript else ""))


_running = False
_failed_at = 0.0
FAIL_BACKOFF_S = 15 * 60          # an unplugged dongle is retried every 15 min, not every minute
_stop_event = None                # the current watch's stop flag
# Every watch alive — running, or queued behind another for the dongle — by its
# stop flag. Stopping goes to all of them: two restarts racing once queued a
# second watch, which took `_stop_event` while the first kept the dongle and
# ignored every stop until its tune ran out.
_stops: set = set()

# ── Listen along ────────────────────────────────────────────────────────────
# Someone in a voice channel hearing the scan as it happens: silence while it
# hops, the channel whenever a carrier opens the squelch on a hold. Nothing is
# posted per catch — a night is hundreds; `!scanner history` and KAIA//RX's LOG
# have them. While anyone listens along the watch runs even outside the
# nightly hours.

import queue as _queue
import threading as _threading

_along: dict = {}                    # guild_id -> {"vc", "started"}
_audio: "_queue.Queue" = _queue.Queue(maxsize=600)


def _sink(chunk) -> None:
    try:
        from utils.radio import rx_dashboard
        rx_dashboard.audio(chunk)         # the receiver dashboard's monitor, if anyone is listening
    except Exception:
        pass
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


async def start_listen_along(voice_channel, requested_by: str) -> None:
    import discord
    guild = voice_channel.guild
    from utils.audio.strudel_session import get_session as music_session
    if music_session(guild.id):
        raise RuntimeError("the music's playing — `!music off` first")
    from utils.radio import live
    await live.free_voice(guild)
    vc = guild.voice_client
    if vc and vc.is_connected():
        await vc.move_to(voice_channel)
    else:
        vc = await voice_channel.connect(timeout=30.0, reconnect=True)
    while not _audio.empty():
        _audio.get_nowait()
    settle("the scanner live")
    vc.play(discord.PCMAudio(_PcmStream(ScanAudio())))
    _along[guild.id] = {"vc": vc, "started": time.time()}
    log_info(f"[scanner] {requested_by} is listening along in {voice_channel.name}")
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    task_registry.register(f"scanner_along_watch_{guild.id}", asyncio.create_task(_along_watchdog(guild.id)))
    if not _running and rtl.available() and not rtl.DEVICE.locked():
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        ledger.seed(seed_channels())
        task_registry.register(f"scanner_watch_{int(time.time())}", asyncio.create_task(_watch()))


async def stop_listen_along(guild_id: int, disconnect: bool = True) -> bool:
    """End a listen-along. `disconnect=False` when something else is about to
    play on the same connection."""
    entry = _along.pop(guild_id, None)
    if not entry:
        return False
    vc = entry["vc"]
    if vc.is_playing():
        vc.stop()
    if disconnect and vc.is_connected():
        await vc.disconnect(force=True)
    log_info("[scanner] listen-along ended")
    return True


async def _along_watchdog(guild_id: int) -> None:
    """End a listen-along when the channel has been empty 40 s or it has run
    radio.live_max_minutes — otherwise it, and an out-of-hours watch, run on
    for nobody."""
    limit = float(config.get("radio.live_max_minutes", 60)) * 60
    empty = 0
    while guild_id in _along:
        await asyncio.sleep(20)
        entry = _along.get(guild_id)
        if not entry:
            return
        humans = [m for m in (getattr(entry["vc"].channel, "members", []) or []) if not m.bot]
        empty = empty + 1 if not humans else 0
        if empty >= 2 or time.time() - entry["started"] > limit:
            await stop_listen_along(guild_id)
            return


class _PcmStream:
    """A file-like wrapper so discord.PCMAudio can pull frames from ScanAudio."""

    def __init__(self, source: ScanAudio):
        self.source = source

    def read(self, n: int) -> bytes:
        return self.source.read()


async def _watch(net: Optional[dict] = None) -> None:
    """Hold the dongle and run the waterfall until the window closes or a live
    listen asks for it — or, with `net`, sit on that one channel until the net
    ends. The watcher runs in a child process (waterfall.child_main) so
    librtlsdr's C-level prints can't reach the dashboard's terminal."""
    import multiprocessing as mp
    import threading
    from utils.radio import waterfall
    global _running, _failed_at, _stop_event, _pinned
    _running = True
    _pinned = net
    # fork, not spawn: spawn re-imports the main module, and Kaiacord.py imports
    # the whole bot at top level. The child touches only numpy, ctypes and the
    # watcher — no logging or other lock another thread might hold.
    ctx = mp.get_context("fork")
    stop = ctx.Event()
    _stop_event = stop
    _stops.add(stop)
    catches, audio, passes = ctx.Queue(), ctx.Queue(maxsize=600), ctx.Value("i", 0)
    spectra = ctx.Queue(maxsize=400)              # what the receiver dashboard draws (rx_scope)

    def _consume():
        while True:
            try:
                c = catches.get(timeout=5)
            except Exception:
                if not proc.is_alive():
                    return
                continue
            if c is None:
                return
            try:
                classify(c)
            except Exception as e:
                log_warning(f"[scanner] classifying a catch failed: {e}")

    def _forward():
        while proc.is_alive() or not audio.empty():
            try:
                _sink(audio.get(timeout=1))
            except Exception:
                continue

    def _scope():
        from utils.radio.rx_scope import scope
        while proc.is_alive():
            try:
                scope.feed(spectra.get(timeout=1))
            except Exception:
                continue

    try:
        async with rtl.DEVICE:
            rtl.YIELD.clear()
            mode, freq, until = ("pinned", net["freq_hz"], net["until"]) if net else ("hop", 0, 0.0)
            # The hop plan keeps every seeded and configured channel out of a
            # slice's blind centre; config is read here, before the fork.
            seeded = seed_channels()
            hops = waterfall.hop_plan([c["freq_hz"] for c in seeded])
            digital = [c["freq_hz"] for c in seeded if c.get("mode") == "digital"]
            proc = ctx.Process(target=waterfall.child_main, name="kaia-scanner", daemon=True,
                               args=(mode, freq, until, float(_cfg("gain", rtl.DEFAULT_GAIN)), rtl.ppm(),
                                     stop, catches, audio, passes, hops, spectra, digital))
            proc.start()
            consumer = threading.Thread(target=_consume, name="scanner-classify", daemon=True)
            forwarder = threading.Thread(target=_forward, name="scanner-audio", daemon=True)
            scoper = threading.Thread(target=_scope, name="scanner-scope", daemon=True)
            consumer.start()
            forwarder.start()
            scoper.start()
            if net:
                log_info(f"[scanner] net watch on {net['freq_hz'] / MHZ:.4f} MHz ({net['label']}) until "
                         f"{datetime.fromtimestamp(net['until']):%H:%M}")
            else:
                log_info("[scanner] waterfall watch started")
            started = time.time()
            while proc.is_alive():
                if rtl.YIELD.is_set() or not _cfg("enabled", True):
                    stop.set()
                elif not net and (due_net() or tuned() or not (within_hours() or listening_along() or asked())):
                    stop.set()                     # a net is starting, a tune asked for, or the night is over
                await asyncio.sleep(1)
            await asyncio.to_thread(proc.join, 5)
            if proc.exitcode not in (0, None) and time.time() - started < 30:
                raise RuntimeError(f"the scanner process exited with code {proc.exitcode} — "
                                   "is the RTL-SDR busy or unplugged?")
        # The dongle is free: the next watch may start now. Finishing the last
        # classifications (Whisper on a catch can take a minute) and the night's
        # picture and notebook happen after, holding nothing — a tune waited on
        # all of it and gave up.
        _release(stop, net)
        log_info(f"[scanner] {'net' if net else 'waterfall'} watch stopped after {passes.value} passes")
        await asyncio.to_thread(consumer.join, 120)
        if not net:
            await asyncio.to_thread(_save_night)
            await asyncio.to_thread(refresh_notebook)
    except Exception as e:
        _failed_at = time.time()
        log_warning(f"[scanner] waterfall watch failed: {type(e).__name__}: {e} — retrying in 15 minutes")
    finally:
        from utils.radio import transcribe
        transcribe.release_if_idle()
        _release(stop, net)


def _release(stop, net) -> None:
    """This watch no longer holds or waits for the dongle."""
    global _running, _stop_event, _pinned
    if stop not in _stops:
        return
    _stops.discard(stop)
    if _stop_event is stop:
        _stop_event, _pinned = None, None
    _running = bool(_stops)


def nights_dir() -> Path:
    """Saved night waterfalls, one picture per band (rx_scope.save_night)."""
    clips = _clips_dir()
    return clips.parent / ("waterfalls.test" if clips.name.endswith(".test") else "waterfalls")


def _save_night() -> None:
    try:
        from utils.radio.rx_scope import scope
        saved = scope.save_night(nights_dir())
        if saved:
            log_info(f"[scanner] the night's waterfall saved: {len(saved)} bands")
    except Exception as e:
        log_warning(f"[scanner] the night's waterfall not saved: {e}")


# ── Tuned from the receiver dashboard ───────────────────────────────────────
# A click on the dashboard's waterfall sits the dongle on one channel for a
# while, exactly as a configured net does (`_watch(net)`): each transmission
# held, recorded and classified. Outside the scanning hours too — the dongle
# is idle then. A live listen in voice still has the dongle first.
_tuned: Optional[dict] = None


def tuned() -> Optional[dict]:
    return _tuned if _tuned and _tuned["until"] > time.time() else None


async def tune(freq_hz: int, minutes: float = 15.0) -> str:
    """Sit on `freq_hz` for `minutes`. Returns what happened, for the page."""
    global _tuned
    from utils.radio import live
    if any(getattr(s, "local", False) for s in live.active()):
        return "the dongle is playing live in voice — stop that first"
    if not rtl.available():
        return "the RTL-SDR isn't connected"
    freq_hz = snap_channel(int(freq_hz))
    _tuned = {"freq_hz": freq_hz, "until": time.time() + minutes * 60,
              "label": f"tuned from the dashboard · {freq_hz / MHZ:.4f} MHz"}
    log_info(f"[scanner] tuned to {freq_hz / MHZ:.4f} MHz from the receiver dashboard for {minutes:g} min")
    await _restart()
    return f"on {freq_hz / MHZ:.4f} MHz for {minutes:g} minutes"


async def untune() -> str:
    global _tuned
    _tuned = None
    await _restart()
    return "back to the scan" if within_hours() or asked() else "off — the scan runs " + _hours_text()


# ── Started from the receiver dashboard ─────────────────────────────────────
# ▶ SCAN runs the waterfall outside the nightly hours for as long as asked, and
# only while a dashboard page is open: closing the window ends it within
# DASH_GONE_S, as an empty voice channel ends a listen-along.
DASH_GONE_S = 60.0
_asked: Optional[dict] = None


def seen_by_dashboard() -> None:
    """A dashboard page is open (called by its stream, ten times a second)."""
    if _asked is not None:
        _asked["seen"] = time.time()


def asked() -> Optional[dict]:
    now = time.time()
    if _asked and _asked["until"] > now and now - _asked["seen"] < DASH_GONE_S:
        return _asked
    return None


async def start_scan(minutes: float = 30.0) -> str:
    """Scan now, from the dashboard. Returns what happened, for the page."""
    global _asked, _tuned
    from utils.radio import live
    if any(getattr(s, "local", False) for s in live.active()):
        return "the dongle is playing live in voice — stop that first"
    if not rtl.available():
        return "the RTL-SDR isn't connected"
    now = time.time()
    _asked = {"until": now + minutes * 60, "seen": now}
    if _running and not _pinned:
        return f"already scanning — kept going for {minutes:g} minutes"
    _tuned = None
    if not _running and rtl.DEVICE.locked():
        return "the dongle is busy"
    ledger.seed(seed_channels())
    await _restart()
    log_info(f"[scanner] scan started from the receiver dashboard for {minutes:g} min")
    return f"scanning for {minutes:g} minutes"


async def stop_scan() -> str:
    global _asked
    _asked = None
    if within_hours() or listening_along():
        return "the scan keeps running — it's " + ("the nightly hours" if within_hours() else "being listened to in voice")
    if not _pinned:
        _stop_all()
    return "scan stopped"


def _hours_text() -> str:
    return str(_cfg("hours", "00:00-06:00"))


_restarting = False
_restart_again = False


def _stop_all() -> None:
    for s in list(_stops):
        s.set()


async def _restart() -> None:
    """Stop whatever is watching and start what the state now asks for (a
    tune, a scan, or nothing). One at a time: a request arriving mid-restart
    only marks it to look again, so a run of clicks ends on the last one."""
    global _restarting, _restart_again
    if _restarting:
        _restart_again = True
        _stop_all()
        return
    _restarting = True
    try:
        while True:
            _restart_again = False
            for _ in range(120):
                # Every pass, not once: a watch just started by tick() registers
                # its stop flag only when its task first runs.
                _stop_all()
                if not _running and not rtl.DEVICE.locked():
                    break
                await asyncio.sleep(0.25)
            if _restart_again:
                continue
            tick()
            return
    finally:
        _restarting = False


def refresh_notebook() -> None:
    """Rewrite the band notebook (docs/reports/reference/local_band_notebook.md)
    from the ledger after a watch, so it holds what was heard without anyone
    running the tool. Its "My notes" section is kept. A separate process: the
    tool is not part of the bot, and it decodes clips with ffmpeg."""
    import subprocess
    import sys
    tool = Path(__file__).resolve().parents[2] / "tools" / "maintenance" / "band_notebook.py"
    if not tool.is_file():
        return
    try:
        out = subprocess.run([sys.executable, str(tool), "--write"], capture_output=True, text=True, timeout=300)
        if out.returncode:
            log_warning(f"[scanner] band notebook not refreshed: {(out.stderr or out.stdout).strip()[-200:]}")
        else:
            log_debug(f"[scanner] {out.stdout.strip()}")
    except Exception as e:
        log_warning(f"[scanner] band notebook not refreshed: {e}")


async def shutdown() -> None:
    """Stop the watcher thread and any listen-along. A watcher left running on
    its executor thread holds the dongle and keeps the process from exiting."""
    _stop_all()
    for guild_id in list(_along):
        await stop_listen_along(guild_id)
    for _ in range(80):                       # a hold stops within a chunk; the last classification can take a minute
        if not _running:
            return
        await asyncio.sleep(1)


def tick(now: Optional[datetime] = None) -> bool:
    """Start the watch if it's scanning hours and the dongle is free. Called
    every minute by the radio task. Returns whether it started."""
    global _running
    if _running or not _cfg("enabled", True) or not rtl.available() or rtl.DEVICE.locked():
        return False
    if time.time() - _failed_at < FAIL_BACKOFF_S:
        return False
    net = due_net(now) or tuned()
    if not net and not within_hours(now) and not asked():
        return False
    ledger.seed(seed_channels())
    _running = True                       # now, not when the task first runs: a second tick must see it
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    task_registry.register(f"scanner_watch_{int(time.time())}", asyncio.create_task(_watch(net)))
    return True


def running() -> bool:
    return _running
