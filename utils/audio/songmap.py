"""Where a record's sections are, so a mix can leave it at one.

A blend used to be fitted to the last phrase before the music ended, whatever
the record was doing there: every record played out its whole outro, and every
transition happened at the same point of a song. A DJ leaves a record where it
changes — as its outro starts, or as it falls into its last breakdown.

Five curves over the record, each relative to that record's own usual level:
`full` (all-frequency mid-channel energy), `bass` (under 180 Hz), `lead` (sustained
300-3400 Hz centre energy), `upper` (3500-5200 Hz energy at this analyser's
11.025 kHz sample rate), and `transient` (positive spectral flux). `lead` is
not a vocal detector or stem separation: it is a sustained midrange/centre
proxy. `upper` is not a full-band air detector; frequencies above Nyquist are
not measured. Spectral flux is a change/activity proxy, not a percussion
classifier.

A phrase-profile API summarizes these same cached curves in raw seconds. It
aligns windows only when the beatgrid has a counted bar one; otherwise it
returns unaligned time windows and leaves their bar count unknown. Section
labels are explicitly candidates with heuristic evidence scores, never
ground-truth arrangement or vocal labels.

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
VERSION = 3

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
    upper: np.ndarray
    transient: np.ndarray

    def db(self, name: str, a: float, b: float) -> float:
        """Mean normalized level of a curve between own-time seconds `a` and `b`."""
        x = getattr(self, name)
        a, b = a - _LEAD_IN_S, b - _LEAD_IN_S
        i, j = int(max(0.0, a) / HOP_S), int(max(0.0, b) / HOP_S)
        j = max(j, i + 1)
        seg = x[i:j]
        if not len(seg):
            return -90.0
        return float(10 * np.log10(max(float(seg.mean()), 1e-9)))


@dataclass(frozen=True)
class PhraseState:
    """A compact observation over a raw-time window, not an asserted song section.

    `aligned` means its boundaries follow a counted musical phrase. If false,
    `bars` is None and the window is only a time-local feature summary.
    `section` values are candidates; `section_strength` is a heuristic score,
    not a calibrated probability.
    """
    start: float
    end: float
    aligned: bool
    bars: Optional[int]
    full_db: float
    bass_db: float
    lead_db: float
    upper_db: float
    transient_db: float
    energy_change_db: float
    section: Optional[str] = None
    section_strength: float = 0.0


@dataclass(frozen=True)
class PhraseProfile:
    """Cached-map evidence summarized into time-local phrase candidates."""
    duration: float
    phrase_bars: int
    grid_bpm: Optional[float]
    grid_contrast: Optional[float]
    aligned: bool
    phrases: tuple[PhraseState, ...]


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
    """(full, bass, lead-proxy, upper-band, spectral-flux) per STFT frame."""
    from scipy.ndimage import median_filter
    from scipy.signal import stft
    f, _, left = stft(samples[:, 0], RATE, nperseg=_NPERSEG, noverlap=_NPERSEG - _STEP, boundary=None, padded=False)
    _, _, right = stft(samples[:, 1], RATE, nperseg=_NPERSEG, noverlap=_NPERSEG - _STEP, boundary=None, padded=False)
    mid, side = np.abs(left + right) / 2, np.abs(left - right) / 2
    full = (mid ** 2).sum(axis=0)
    bass = (mid[f < 180] ** 2).sum(axis=0)
    upper_band = (f >= 3500) & (f <= 5200)
    upper = (mid[upper_band] ** 2).sum(axis=0)
    # What is in the middle of the picture, in the band a voice sits in, less
    # what is a hit: a median along time keeps what sustains, one along
    # frequency keeps what is a click, and the first is weighed against both.
    band = (f >= 300) & (f <= 3400)
    centre = np.maximum(mid[band] - side[band], 0.0)
    held = median_filter(centre, size=(1, 17))
    hit = median_filter(centre, size=(17, 1))
    lead = ((centre * (held * held / (held * held + hit * hit + 1e-12))) ** 2).sum(axis=0)
    # Positive spectral flux: how much new spectrum appeared since the last
    # frame. This is activity evidence, not a drum/onset classifier.
    flux = np.maximum(np.diff(mid, axis=1), 0.0).sum(axis=0)
    transient = np.concatenate((np.zeros(1, dtype=np.float32), flux.astype(np.float32)))
    return full, bass, lead, upper, transient


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
    curves = [np.concatenate([p[k] for p in parts]) for k in range(5)]
    for x in curves:
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
    """The record's map, keyed by the complete audio payload identity.

    Fingerprinting and any decode happen on the caller's background worker;
    this function must never be called from the 20 ms audio-render callback.
    """
    from utils.audio.library import audio_signature

    signature = audio_signature(path)
    if signature is None:
        return None
    with _mem_lock:
        held = _MEM.pop(path, None)
        if held is not None and held[0] == signature:
            _MEM[path] = held
            return held[1]
    cache = _cache_path(path)
    m = None
    try:
        if cache.exists():
            with np.load(cache) as z:
                cached_signature = str(z["signature"].item())
                if cached_signature == signature:
                    m = Map(
                        z["full"].astype(np.float32),
                        z["bass"].astype(np.float32),
                        z["lead"].astype(np.float32),
                        z["upper"].astype(np.float32),
                        z["transient"].astype(np.float32),
                    )
    except (OSError, ValueError, KeyError):
        m = None
    if m is None:
        try:
            m = compute(_decode(path))
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        if m is None:
            return None
        # Do not cache analysis of a file that changed while ffmpeg was reading it.
        if audio_signature(path, refresh=True) != signature:
            return None
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_name(f".{cache.stem}.{os.getpid()}.{threading.get_ident()}.tmp.npz")
            np.savez(tmp, full=m.full, bass=m.bass, lead=m.lead, upper=m.upper,
                     transient=m.transient, signature=np.asarray(signature))
            os.replace(tmp, cache)
        except OSError:
            pass
    elif audio_signature(path, refresh=True) != signature:
        return None
    with _mem_lock:
        _MEM[path] = (signature, m)
        while len(_MEM) > _MEM_RECORDS:
            _MEM.pop(next(iter(_MEM)))
    return m




def _candidate_strength(value: float) -> float:
    """Bound a heuristic evidence score; it is not a probability."""
    return float(min(0.95, max(0.0, value)))


def profile_from_map(m: Map, grid=None, *, phrase_bars: int = 4,
                     fallback_window_s: float = 8.0,
                     duration: Optional[float] = None) -> PhraseProfile:
    """Summarize one cached map into phrase-local, explainable audio evidence.

    A counted grid produces windows aligned to `phrase_bars`; the pre-beat
    intro is retained as an unaligned window. Without a counted bar one, use
    fixed-time windows and explicitly leave `bars` unknown. This function is
    pure: it never decodes audio or touches the filesystem.
    """
    if phrase_bars < 1 or phrase_bars > 32:
        raise ValueError("phrase_bars must be between 1 and 32")
    if fallback_window_s <= 0:
        raise ValueError("fallback_window_s must be positive")
    if duration is None:
        duration = len(m.full) * HOP_S + _LEAD_IN_S
    duration = max(0.0, float(duration))
    if duration <= 0 or not len(m.full):
        return PhraseProfile(duration, phrase_bars, getattr(grid, "bpm", None),
                             getattr(grid, "contrast", None), False, ())

    aligned = bool(grid is not None and getattr(grid, "bar_known", False)
                   and getattr(grid, "bpm", 0.0) > 0)
    spans: list[tuple[float, float, bool, Optional[int]]] = []
    phrase_s = 0.0
    first = 0.0
    if aligned:
        phrase_s = 4.0 * float(grid.beat) * phrase_bars
        first_boundary = grid.tick_bar(0.0, every=phrase_bars) if grid.tracked else grid.downbeat
        if first_boundary is None:
            # A nominally counted grid without a usable first phrase tick is
            # not enough evidence to label any window as phrase-aligned.
            aligned = False
        else:
            first = float(first_boundary)
            if first < 0 or first >= duration:
                first = float(grid.downbeat)
            first = max(0.0, first)
            if first > HOP_S:
                spans.append((0.0, min(first, duration), False, None))
            t = first
            while t < duration - HOP_S:
                # Follow every tracked phrase boundary. A single average BPM
                # interval slowly drifts on records whose tempo changes.
                next_boundary = (
                    grid.tick_bar(t + HOP_S, every=phrase_bars)
                    if grid.tracked else t + phrase_s
                )
                if next_boundary is None or next_boundary <= t + HOP_S:
                    # The tracker has no further trustworthy phrase boundary.
                    # Keep the remainder useful as time-local evidence, but
                    # do not invent bar counts or claim alignment.
                    fallback_start = t
                    while fallback_start < duration - HOP_S:
                        end = min(duration, fallback_start + fallback_window_s)
                        spans.append((fallback_start, end, False, None))
                        fallback_start = end
                    break
                next_boundary = float(next_boundary)
                end = min(duration, next_boundary)
                complete = next_boundary <= duration + 0.001
                spans.append((t, end, complete, phrase_bars if complete else None))
                if not complete:
                    break
                t = next_boundary
    if not aligned:
        t = 0.0
        while t < duration - HOP_S:
            end = min(duration, t + fallback_window_s)
            spans.append((t, end, False, None))
            t = end

    if not spans:
        spans.append((0.0, duration, False, None))

    bar_s = 4.0 * float(grid.beat) if aligned else 0.0
    outro = outro_start(m, duration, bar_s) if aligned else None
    break_at = last_break(m, outro if outro is not None else duration, bar_s, duration) if aligned else None
    states: list[PhraseState] = []
    for start, end, is_aligned, bars in spans:
        full_db = m.db("full", start, end)
        bass_db = m.db("bass", start, end)
        lead_db = m.db("lead", start, end)
        upper_db = m.db("upper", start, end)
        transient_db = m.db("transient", start, end)
        previous = states[-1] if states else None
        previous2 = states[-2] if len(states) >= 2 else None
        energy_change = full_db - previous.full_db if previous else 0.0
        section: Optional[str] = None
        strength = 0.0

        if aligned and start < first and end <= first + HOP_S:
            section, strength = "intro_candidate", 0.7
        elif outro is not None and start >= outro - HOP_S:
            section = "outro_candidate"
            strength = _candidate_strength(0.55 + max(0.0, THIN_DB - lead_db) / 16.0)
        elif bass_db < BREAK_DB and (
            (break_at is not None and start + HOP_S >= break_at)
            or start >= (16.0 * bar_s if aligned else 24.0)
        ):
            section = "breakdown_candidate"
            strength = _candidate_strength(0.55 + (BREAK_DB - bass_db) / 20.0)
        elif previous is not None and previous.bass_db < BREAK_DB and bass_db - previous.bass_db >= 4.0:
            section = "drop_candidate"
            strength = _candidate_strength(0.6 + (bass_db - previous.bass_db - 4.0) / 16.0)
        elif (previous is not None and previous2 is not None
              and full_db - previous.full_db >= 1.0
              and previous.full_db - previous2.full_db >= 0.5
              and (upper_db - previous.upper_db >= 0.5
                   or transient_db - previous.transient_db >= 0.8)):
            section = "build_candidate"
            strength = _candidate_strength(0.55 + min(0.3, energy_change / 10.0))
        elif (previous is not None and abs(energy_change) <= 1.0
              and bass_db >= BREAK_DB and transient_db > -8.0):
            section, strength = "groove_candidate", 0.5

        states.append(PhraseState(
            start=round(start, 3), end=round(end, 3), aligned=is_aligned, bars=bars,
            full_db=full_db, bass_db=bass_db, lead_db=lead_db, upper_db=upper_db,
            transient_db=transient_db, energy_change_db=energy_change,
            section=section, section_strength=strength,
        ))

    return PhraseProfile(
        duration=round(duration, 3),
        phrase_bars=phrase_bars,
        # Contrast is retained as a raw tracker statistic even when the bar
        # count is not trustworthy; consumers must not treat it as a probability.
        grid_bpm=float(grid.bpm) if grid is not None else None,
        grid_contrast=float(grid.contrast) if grid is not None else None,
        aligned=aligned,
        phrases=tuple(states),
    )


def phrase_profile(path: str, bpm: Optional[float], *, phrase_bars: int = 4,
                   fallback_window_s: float = 8.0,
                   duration: Optional[float] = None) -> Optional[PhraseProfile]:
    """Build a read-only profile from the cached map and beatgrid.

    This may fingerprint, decode or run beatgrid analysis on a cache miss. Call
    from background planning/preparation only, never from the 20 ms renderer.
    The final identity check prevents combining a map and grid from different
    replacements of the same path.
    """
    from utils.audio.library import audio_signature

    identity = audio_signature(path)
    if identity is None:
        return None
    m = get(path)
    if m is None:
        return None
    grid = None
    if bpm is not None and bpm > 0:
        try:
            from utils.audio import beatgrid
            grid = beatgrid.grid_for(path, bpm)
        except (OSError, subprocess.SubprocessError, ValueError):
            grid = None
    if audio_signature(path, refresh=True) != identity:
        return None
    return profile_from_map(m, grid, phrase_bars=phrase_bars,
                            fallback_window_s=fallback_window_s, duration=duration)


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
