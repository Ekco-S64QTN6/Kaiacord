"""Where the beats and bars are in a record.

A mix is only clean if the incoming record's beats land on the outgoing
record's beats and its bar one lands on a bar one. The catalog gives the tempo
to a whole BPM; that drifts by tens of milliseconds over a 16-beat blend, and
says nothing about where the beats fall. This reads the low end (kick and
bass), builds an onset curve, and finds the beat period and phase whose comb
lines up with it best.

The bar is not guessed from accents — on a log-energy curve they barely
differ, and the guess picked the wrong beat of the bar most of the time, so
kicks met kicks with the claps on the wrong beats. A dance record starts its
beat on a downbeat: `grid_for` takes the record's first strong beat as bar one,
and `grid_at` counts beats from it to wherever the record is being mixed out
of, keeping the bar only when the count comes out whole. CPU only, ~1 s a call.
"""
from __future__ import annotations

import functools
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

import numpy as np

RATE = 11025
HOP = 110                       # ~10 ms
HOPS_PER_S = RATE / HOP
FINE_HOP = 22                   # ~2 ms, for lining up kicks
#: A comb peak must stand this far above the average phase to be trusted.
MIN_CONTRAST = 1.35


@dataclass(frozen=True)
class Grid:
    bpm: float                  # refined, in the record's own time
    downbeat: float             # seconds to a bar's first beat, own time
    contrast: float             # how clearly the beat stood out
    #: False when the bar could not be counted from the record's first beat,
    #: and `downbeat` is the accent guess — right about one time in four.
    bar_known: bool = True
    #: Which bar of the record `downbeat` starts, counted from bar one (0):
    #: phrases of 4 and 8 bars are counted from it.
    bar0: int = 0

    @property
    def beat(self) -> float:
        return 60.0 / self.bpm

    def next_bar(self, t: float, stretch: float = 1.0, every: int = 1) -> float:
        """The first bar start at or after `t`, in seconds of the record as
        played (stretched by `stretch`, so its tempo is bpm * stretch). With
        `every`, only bars that open a phrase of that many bars, counted from
        the record's bar one."""
        bar = 4 * self.beat / stretch
        period = bar * max(1, every)
        first = (self.downbeat / stretch) - (self.bar0 % max(1, every)) * bar
        k = int(np.ceil((t - first) / period - 1e-9))
        return first + k * period


_RUBBERBAND: Optional[bool] = None
#: ffmpeg's atempo puts every onset about this much early (half its WSOLA
#: window, measured on click tracks at ±2.5%), and its output is that much
#: short. Rubberband with percussive transients is within a millisecond.
ATEMPO_EARLY_S = 0.020


def has_rubberband() -> bool:
    global _RUBBERBAND
    if _RUBBERBAND is None:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, timeout=10).stdout
            _RUBBERBAND = bool(re.search(r"\brubberband\b", out))
        except (OSError, subprocess.SubprocessError):
            _RUBBERBAND = False
    return _RUBBERBAND


def stretch_filter(ratio: float, semitones: int = 0) -> Optional[str]:
    """The ffmpeg filter that plays a record at `ratio` times its tempo, pitch
    kept (or moved by `semitones`, rubberband only), or None when nothing
    changes. Rubberband keeps the kicks where they were; atempo, the fallback,
    moves them ATEMPO_EARLY_S early (`stretch_latency`) and cannot shift key."""
    semitones = semitones if has_rubberband() else 0
    if abs(ratio - 1.0) <= 1e-4 and not semitones:
        return None
    if has_rubberband():
        pitch = f":pitch={2 ** (semitones / 12):.6f}" if semitones else ""
        return f"rubberband=tempo={ratio:.5f}{pitch}:transients=crisp:detector=percussive"
    return f"atempo={ratio:.5f}"


def stretch_latency(ratio: float) -> float:
    """How early `stretch_filter(ratio)` puts the record's onsets, in seconds."""
    return ATEMPO_EARLY_S if stretch_filter(ratio) and not has_rubberband() else 0.0


def _decode(path: str, seconds: float) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-t", str(seconds), "-i", path,
                          "-ac", "1", "-ar", str(RATE), "-f", "s16le", "pipe:1"],
                         capture_output=True, timeout=60)
    return np.frombuffer(out.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def onset_curve(samples: np.ndarray, hop: int = HOP) -> np.ndarray:
    """Rises in low-band energy, one value per `hop` samples."""
    from scipy.signal import butter, sosfilt
    low = sosfilt(butter(2, 160, btype="low", fs=RATE, output="sos"), samples)
    n = len(low) // hop
    if n < 10:
        return np.zeros(0)
    e = np.sqrt(np.mean(low[: n * hop].reshape(n, hop) ** 2, axis=1)) + 1e-6
    # Measured from silence, so a record whose first kick is its first sample
    # has an onset there: that kick is bar one.
    return np.maximum(0.0, np.diff(np.log(e), prepend=np.log(1e-6)))


def find_grid(onsets: np.ndarray, bpm: float) -> Optional[Grid]:
    """The beat comb that best fits `onsets`, searched within 1.5% of `bpm`
    (and at half or double it, should the catalog have the octave wrong)."""
    if len(onsets) < HOPS_PER_S * 10 or not bpm:
        return None
    best = None
    candidates = np.concatenate([np.arange(b * 0.985, b * 1.015, 0.02)
                                 for b in (bpm,) if 60 <= b <= 200])
    for b in candidates:
        period = HOPS_PER_S * 60.0 / b
        beats = np.arange(0, len(onsets) - period, period)
        if len(beats) < 8:
            continue
        phases = np.arange(int(period))
        idx = (phases[:, None] + beats[None, :]).astype(int)
        scores = onsets[np.clip(idx, 0, len(onsets) - 1)].sum(axis=1)
        p = int(np.argmax(scores))
        contrast = float(scores[p] / (scores.mean() + 1e-9))
        if best is None or scores[p] > best[0]:
            best = (scores[p], b, p, contrast, period, scores)
    if best is None:
        return None
    _, b, p, contrast, period, scores = best
    # Sub-hop phase by parabolic interpolation round the peak.
    l, r = scores[(p - 1) % len(scores)], scores[(p + 1) % len(scores)]
    denom = l - 2 * scores[p] + r
    frac = 0.5 * (l - r) / denom if denom else 0.0
    phase = (p + frac) % period
    # A guess at which beat starts the bar, kept for when it cannot be
    # counted (`grid_at` with an anchor does): the beat with the strongest
    # accents. On a log-energy onset curve the accents barely differ, and it
    # picks the wrong beat of the bar most of the time.
    accents = []
    for j in range(4):
        idx = np.arange(phase + j * period, len(onsets), 4 * period).astype(int)
        accents.append(onsets[idx].sum() if len(idx) else 0.0)
    first = phase + int(np.argmax(accents)) * period
    return Grid(bpm=float(b), downbeat=float(first / HOPS_PER_S), contrast=contrast, bar_known=False)


def _beat_phase(g: Grid) -> float:
    """Seconds to the first beat of `g`'s comb (any beat, not the bar)."""
    return g.downbeat % g.beat


def first_strong_beat(onsets: np.ndarray, g: Grid) -> Optional[float]:
    """Seconds to the first beat of the comb where the beat has come in: the
    first tooth well above the noise, with two of the next three as strong.
    A dance record starts its beat on a downbeat, so this is bar one."""
    P = g.beat * HOPS_PER_S
    teeth = np.arange(_beat_phase(g) * HOPS_PER_S, len(onsets) - 2, P)
    if len(teeth) < 8:
        return None
    h = np.array([onsets[max(0, int(t) - 2):int(t) + 3].max() for t in teeth])
    floor = 0.35 * np.percentile(h, 75)
    strong = h > floor
    for k in range(len(teeth) - 3):
        if strong[k] and strong[k + 1:k + 4].sum() >= 2:
            return float(teeth[k] / HOPS_PER_S)
    return None


#: The bar count from the record's first beat is trusted only when the beats
#: between come out this close to a whole number.
COUNT_SLACK = 0.25


def _window(path: str, start: float, seconds: float) -> np.ndarray:
    args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", str(seconds),
            "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "s16le", "pipe:1"]
    raw = subprocess.run(args, capture_output=True, timeout=60).stdout
    return onset_curve(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)


def grid_at(path: str, bpm: Optional[float], start: float = 0.0, seconds: float = 40.0,
            anchor: Optional[Grid] = None) -> Optional[Grid]:
    """The beat grid round one stretch of a record — wherever it is being
    mixed out of — with `downbeat` a bar start in seconds from the record's
    start. The beat is read locally because a record's phase does not hold
    end to end (breakdowns, live drums). The bar is counted: beats from
    `anchor` (the record's `grid_for`, whose downbeat is its first beat) to
    here, whole bars of four. None if the beat there is not clear enough to
    mix on; `bar_known` False if the count does not come out whole."""
    if not bpm:
        return None
    start = max(0.0, start)
    try:
        g = find_grid(_window(path, start, seconds), bpm)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not g or g.contrast < MIN_CONTRAST:
        return None
    here = start + _beat_phase(g)                      # a beat, absolute
    if anchor is None or not anchor.bar_known:
        return Grid(g.bpm, start + g.downbeat, g.contrast, bar_known=False)
    beat = 120.0 / (g.bpm + anchor.bpm)                # the mean beat over the span
    n = (here - anchor.downbeat) / beat
    if abs(n - round(n)) > COUNT_SLACK:
        return Grid(g.bpm, start + g.downbeat, g.contrast, bar_known=False)
    to_bar = (-int(round(n))) % 4
    return Grid(g.bpm, here + to_bar * g.beat, g.contrast, bar_known=True,
                bar0=(int(round(n)) + to_bar) // 4)


@functools.lru_cache(maxsize=128)
def grid_for(path: str, bpm: Optional[float], seconds: float = 60.0) -> Optional[Grid]:
    """The grid of a record's opening, where it is mixed in: `downbeat` is the
    first beat of the record's beat — bar one — not the comb's first tooth,
    which can fall in the silence or the beatless intro before it."""
    if not bpm:
        return None
    try:
        onsets = _window(path, 0.0, seconds)
        g = find_grid(onsets, bpm)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not g or g.contrast < MIN_CONTRAST:
        return None
    first = first_strong_beat(onsets, g)
    if first is None:
        return Grid(g.bpm, g.downbeat, g.contrast, bar_known=False)
    contrast = g.contrast
    if first > 3.0:
        # A blend starts the record at its first beat, so its steadiness is
        # measured from there: a beatless intro in the window read as a loose
        # beat (2.2, 3.0) on records whose beat is steady once it starts.
        try:
            g2 = find_grid(_window(path, first, 45.0), g.bpm)
            if g2 is not None:
                contrast = max(contrast, g2.contrast)
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return Grid(g.bpm, first, contrast, bar_known=True)


@functools.lru_cache(maxsize=256)
def first_sound(path: str, threshold_db: float = -45.0) -> float:
    """Seconds to the first moment the record is audible (Mixxx uses the
    first point over -60 dBFS; -45 skips encoder noise and room tone). A
    record started from its first sample brought its silence in with it."""
    try:
        args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-t", "30", "-i", path,
                "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
        a = np.frombuffer(subprocess.run(args, capture_output=True, timeout=30).stdout, dtype=np.int16)
    except (OSError, subprocess.SubprocessError):
        return 0.0
    n = len(a) // 400                                   # 50 ms frames
    if n == 0:
        return 0.0
    rms = np.sqrt(np.mean(a[: n * 400].astype(np.float32).reshape(n, 400) ** 2, axis=1))
    loud = np.flatnonzero(rms > 32768 * 10 ** (threshold_db / 20))
    return float(max(0.0, loud[0] * 0.05 - 0.05)) if len(loud) else 0.0


@functools.lru_cache(maxsize=256)
def bass_entry(path: str, bpm: Optional[float], bars: int = 64) -> Optional[int]:
    """The bar (counted from bar one, 0-based) where the record's bassline
    comes in: the first bar whose sub-bass (under 100 Hz) reaches 60% of its
    usual level over the opening and holds for three of the next four. A dance
    record's intro carries kick and percussion with the bassline held back for
    8, 16 or 32 bars, so the result is snapped to a four-bar phrase when within
    a bar of one. None if the record has no counted bar one or no bassline in
    its first `bars` bars."""
    g = grid_for(path, bpm)
    if g is None or not g.bar_known:
        return None
    bar = 4 * g.beat
    try:
        raw = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{g.downbeat:.3f}",
                              "-t", f"{bars * bar:.2f}", "-i", path, "-ac", "1", "-ar", str(RATE),
                              "-f", "s16le", "pipe:1"], capture_output=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if len(raw) < 2 * RATE * 8 * bar:                       # under eight bars decoded
        return None
    from scipy.signal import butter, sosfilt
    x = sosfilt(butter(4, 100, btype="low", fs=RATE, output="sos"),
                np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
    n = int(bar * RATE)
    count = len(x) // n
    if count < 8:
        return None
    rms = np.sqrt(np.mean(x[: count * n].reshape(count, n) ** 2, axis=1))
    on = rms >= 0.6 * np.percentile(rms, 75)
    for k in range(count - 4):
        if on[k] and on[k + 1:k + 5].sum() >= 3:
            near = int(round(k / 4)) * 4
            return near if abs(near - k) <= 1 else k
    return None


@functools.lru_cache(maxsize=128)
def last_strong_beat(path: str, bpm: Optional[float], duration: float, tail: float = 120.0) -> Optional[float]:
    """Seconds (own time) of the record's last strong beat: where its music
    ends, before a beatless outro, a fade or trailing silence. DJ software
    mixes out at the outro, not at the end of the file; blending over a fade
    hands the bass swap to nothing. None if no beat is clear in the tail."""
    if not bpm or not duration:
        return None
    start = max(0.0, duration - tail)
    try:
        onsets = _window(path, start, tail)
        g = find_grid(onsets, bpm)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not g or g.contrast < MIN_CONTRAST:
        return None
    P = g.beat * HOPS_PER_S
    teeth = np.arange(_beat_phase(g) * HOPS_PER_S, len(onsets) - 2, P)
    if len(teeth) < 8:
        return None
    h = np.array([onsets[max(0, int(t) - 2):int(t) + 3].max() for t in teeth])
    strong = h > 0.35 * np.percentile(h, 75)
    for k in range(len(teeth) - 1, 2, -1):
        if strong[k] and strong[k - 3:k].sum() >= 2:
            return float(start + teeth[k] / HOPS_PER_S)
    return None


def _decode_stretched(path: str, start: float, seconds: float, ratio: float) -> np.ndarray:
    """`seconds` of a record as played at `ratio`, from `start` seconds of its own time."""
    af = stretch_filter(ratio) or "anull"
    args = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}",
            "-t", f"{seconds * ratio:.3f}", "-i", path, "-af", af, "-ac", "1", "-ar", str(RATE),
            "-f", "s16le", "pipe:1"]
    raw = subprocess.run(args, capture_output=True, timeout=60).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def fine_offset(out_path: str, out_ratio: float, out_at: float, in_path: str, in_ratio: float,
                in_at: float, beat: float, seconds: float = 12.0) -> Optional[float]:
    """How far to move the incoming record so its kicks fall on the outgoing
    record's, by cross-correlating their low-end onsets over the blend.

    `out_at` / `in_at` are where each is planned to be (seconds as played)
    at the same instant. Returns the correction in seconds (positive: start the
    incoming later), searched within half a beat, or None if neither record
    has a clear enough kick there to say."""
    try:
        a = onset_curve(_decode_stretched(out_path, out_at * out_ratio, seconds, out_ratio), FINE_HOP)
        b = onset_curve(_decode_stretched(in_path, in_at * in_ratio, seconds, in_ratio), FINE_HOP)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    rate = RATE / FINE_HOP
    n = min(len(a), len(b))
    if n < rate * 4:
        return None
    # A short smear, so a kick that is a hop early still meets its partner.
    k = np.hanning(7)
    a, b = np.convolve(a[:n], k, "same"), np.convolve(b[:n], k, "same")
    a, b = a - a.mean(), b - b.mean()
    reach = int(beat / 2 * rate)
    lags = np.arange(-reach, reach + 1)
    cc = np.array([np.dot(a[max(0, l):n - max(0, -l)], b[max(0, -l):n - max(0, l)]) for l in lags])
    best = int(np.argmax(cc))
    if cc[best] <= 0 or cc[best] < 1.5 * np.median(np.abs(cc)):
        return None
    frac = 0.0
    if 0 < best < len(cc) - 1:
        l, c, r = cc[best - 1], cc[best], cc[best + 1]
        d = l - 2 * c + r
        frac = 0.5 * (l - r) / d if d else 0.0
    # Lag l: incoming onset at hop i matches outgoing at hop i + l, so the
    # incoming must start l hops later.
    return float((lags[best] + frac) / rate)
