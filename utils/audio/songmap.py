"""Where a record's sections are, so a mix can leave it at one.

A blend used to be fitted to the last phrase before the music ended, whatever
the record was doing there: every record played out its whole outro, and every
transition happened at the same point of a song. A DJ leaves a record where it
changes — as its outro starts, or as it falls into its last breakdown.

Three curves over the record, each as power against the record's own usual
level: everything (`full`), the low end (`bass`, under 180 Hz), and what is up
front in the mids (`lead`: 300-3400 Hz, the centre of the stereo picture, with
drum hits taken out — a vocal, a lead line, chords). `lead` is not a vocal
detector: it says how much is going on where a voice would be, which is what
two records fight over.

One stereo decode and an STFT per record, cached beside the beat ticks. Plain
NumPy and SciPy: no model, and nothing here runs on the voice thread.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

RATE = 11025
_NPERSEG, _STEP = 1024, 256
#: STFT frames averaged into one point of a curve (~0.19 s).
_DECIMATE = 8
HOP_S = _STEP * _DECIMATE / RATE
#: A curve's first point is centred this far into the record (half a window).
_LEAD_IN_S = _NPERSEG / 2 / RATE
MAP_DIR = Path(__file__).resolve().parents[2] / "memory" / "records" / "maps"
#: Bumped when the curves are computed differently: older caches are remade.
VERSION = 1

#: A section is thin when its `lead` is this far under the record's usual level…
THIN_DB = -4.0
#: …and a breakdown when its `bass` is this far under.
BREAK_DB = -8.0
#: The shortest outro or breakdown worth mixing at, in bars.
MIN_BARS = 8
#: An "outro" longer than this share of the record is not an outro: the record
#: is quiet in the mids for most of its length and the curve says nothing.
MAX_OUTRO_SHARE = 0.35
#: A record is not left at its breakdown before this much of it has played.
BREAK_AFTER_SHARE = 0.6
BREAK_AFTER_S = 150.0


@dataclass(frozen=True)
class Map:
    full: np.ndarray
    bass: np.ndarray
    lead: np.ndarray

    def db(self, name: str, a: float, b: float) -> float:
        """Mean level of a curve between `a` and `b` (own seconds), in dB
        against the record's usual level. -90 outside the record."""
        x = getattr(self, name)
        a, b = a - _LEAD_IN_S, b - _LEAD_IN_S
        i, j = int(max(0.0, a) / HOP_S), int(max(0.0, b) / HOP_S)
        j = max(j, i + 1)
        seg = x[i:j]
        if not len(seg):
            return -90.0
        return float(10 * np.log10(max(float(seg.mean()), 1e-9)))


def _decode(path: str) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-ac", "2",
                          "-ar", str(RATE), "-f", "s16le", "pipe:1"], capture_output=True, timeout=300)
    return np.frombuffer(out.stdout, dtype=np.int16).astype(np.float32).reshape(-1, 2) / 32768.0


def _usual(power: np.ndarray) -> float:
    """The level a curve sits at where the record is going: the 90th percentile
    of its ~4 s averages, so an intro and a breakdown do not pull it down."""
    k = max(1, int(round(4.0 / HOP_S)))
    n = len(power) // k
    if n < 4:
        return float(power.mean()) if len(power) else 0.0
    return float(np.percentile(power[:n * k].reshape(n, k).mean(axis=1), 90))


#: Seconds of a record analysed at a time: an hour-long mix in one STFT is
#: gigabytes of spectrogram.
_CHUNK_S = 60.0


def _curves(samples: np.ndarray) -> tuple:
    """(full, bass, lead) power per STFT frame for a stretch of stereo audio."""
    from scipy.ndimage import median_filter
    from scipy.signal import stft
    f, _, left = stft(samples[:, 0], RATE, nperseg=_NPERSEG, noverlap=_NPERSEG - _STEP, boundary=None, padded=False)
    _, _, right = stft(samples[:, 1], RATE, nperseg=_NPERSEG, noverlap=_NPERSEG - _STEP, boundary=None, padded=False)
    mid, side = np.abs(left + right) / 2, np.abs(left - right) / 2
    full = (mid ** 2).sum(axis=0)
    bass = (mid[f < 180] ** 2).sum(axis=0)
    # What is in the middle of the picture, in the band a voice sits in, less
    # what is a hit: a median along time keeps what sustains, one along
    # frequency keeps what is a click, and the first is weighed against both.
    band = (f >= 300) & (f <= 3400)
    centre = np.maximum(mid[band] - side[band], 0.0)
    held = median_filter(centre, size=(1, 17))
    hit = median_filter(centre, size=(17, 1))
    lead = ((centre * (held * held / (held * held + hit * hit + 1e-12))) ** 2).sum(axis=0)
    return full, bass, lead


def compute(samples: np.ndarray) -> Optional[Map]:
    """The three curves of a stereo record (float, RATE). None if too short."""
    if samples.ndim != 2 or len(samples) < RATE * 20:
        return None
    # Whole STFT frames per chunk, each chunk overlapping the next by a
    # window less a step, so the frames run on as if it were one transform.
    frames = int(_CHUNK_S * RATE) // _STEP
    parts = []
    for i in range(0, len(samples) - _NPERSEG + 1, frames * _STEP):
        parts.append(_curves(samples[i:i + frames * _STEP + _NPERSEG - _STEP]))
    out = []
    for x in (np.concatenate([p[k] for p in parts]) for k in range(3)):
        n = len(x) // _DECIMATE
        x = x[:n * _DECIMATE].reshape(n, _DECIMATE).mean(axis=1)
        ref = _usual(x)
        out.append((x / ref if ref > 0 else np.zeros_like(x)).astype(np.float32))
    return Map(*out)


def _cache_path(path: str) -> Path:
    return MAP_DIR / (hashlib.sha1(path.encode("utf-8")).hexdigest()[:20] + f".v{VERSION}.npz")


_MEM: dict = {}
_MEM_RECORDS = 64
_mem_lock = threading.Lock()


def get(path: str) -> Optional[Map]:
    """The record's map, from the cache or computed now (a second or two).
    None when the file cannot be read."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _mem_lock:
        held = _MEM.pop(path, None)
        if held is not None and held[0] == mtime:
            _MEM[path] = held
            return held[1]
    cache = _cache_path(path)
    m = None
    try:
        if cache.exists() and cache.stat().st_mtime >= mtime:
            with np.load(cache) as z:
                m = Map(z["full"].astype(np.float32), z["bass"].astype(np.float32), z["lead"].astype(np.float32))
    except (OSError, ValueError, KeyError):
        m = None
    if m is None:
        try:
            m = compute(_decode(path))
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        if m is None:
            return None
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_name(f".{cache.stem}.{os.getpid()}.{threading.get_ident()}.tmp.npz")
            np.savez(tmp, full=m.full, bass=m.bass, lead=m.lead)
            os.replace(tmp, cache)
        except OSError:
            pass
    with _mem_lock:
        _MEM[path] = (mtime, m)
        while len(_MEM) > _MEM_RECORDS:
            _MEM.pop(next(iter(_MEM)))
    return m


def outro_start(m: Map, music_end: float, bar_s: float) -> Optional[float]:
    """Own seconds where the record's outro starts: the last stretch, running
    to where its music ends, in which what was up front has gone. None when it
    has no such stretch (it ends on a full section) or the curve cannot say."""
    if bar_s <= 0 or music_end < 16 * bar_s:
        return None
    n = 0
    # Two bars at a time, a bar's step: a fill or one loud bar does not end it.
    while (n + 2) * bar_s < music_end:
        if m.db("lead", music_end - (n + 2) * bar_s, music_end - n * bar_s) >= THIN_DB:
            break
        n += 1
    if n:
        n += 1                                   # the window that ended the run began a bar inside it
    if n < MIN_BARS or n * bar_s > MAX_OUTRO_SHARE * music_end:
        return None
    return music_end - n * bar_s


def last_break(m: Map, before: float, bar_s: float, length: float) -> Optional[float]:
    """Own seconds where the record's last breakdown starts — the last run of
    MIN_BARS or more with the low end gone that ends before `before` — if it
    comes late enough in the record (`length`) to leave it there."""
    if bar_s <= 0:
        return None
    floor = max(BREAK_AFTER_S, BREAK_AFTER_SHARE * length)
    end = None
    t = before - bar_s
    while t >= floor - bar_s:
        thin = m.db("bass", t, t + bar_s) < BREAK_DB
        if thin and end is None:
            end = t + bar_s
        elif not thin and end is not None:
            start = t + bar_s
            if (end - start) >= MIN_BARS * bar_s - 1e-6 and start >= floor and end < before - 4 * bar_s + 1e-6:
                return start
            end = None
        t -= bar_s
    return None


def out_points(path: str, music_end: float, bpm: Optional[float], length: float) -> list:
    """Where the record can be left, own seconds, latest first:
    [("outro", t), ("break", t)] — whichever it has."""
    if not bpm or bpm <= 0:
        return []
    m = get(path)
    if m is None:
        return []
    bar_s = 240.0 / bpm
    out = []
    o = outro_start(m, music_end, bar_s)
    if o is not None:
        out.append(("outro", o))
    b = last_break(m, o if o is not None else music_end, bar_s, length)
    if b is not None:
        out.append(("break", b))
    return out
