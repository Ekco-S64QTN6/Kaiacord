"""Whether a planned blend locks, measured on the two records themselves.

Every other part of the planner predicts: a bar counted on tracked ticks from
bar one, a tempo fitted through them, a drift extrapolated from the fit. A
tick inserted or dropped in a breakdown, a tracker that sits early on one
record and late on another, a tempo that moves — each leaves the prediction
confident and the kicks apart, and nothing noticed until it was heard.

This is the ear. Each record's low-band onset envelope (kicks, at ~2 ms) is
computed once and cached; a blend is laid out on the played timeline exactly as
the mixer will play it — the outgoing at its ratio, the incoming from its
offset at its own — and, bar by bar through the whole overlap, the lag that
best lines the two envelopes up is measured. A blend whose beats sit together
in every bar it can hear is `locked`; one that drifts, flams or never agrees
is not, whatever the grids said.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from utils.audio.beatgrid import RATE

ENV_HOP = 22                                  # samples at 11025 Hz: ~2.0 ms
ENV_RATE = RATE / ENV_HOP
ENV_DIR = Path(__file__).resolve().parents[2] / "memory" / "records" / "env2"

#: A bar's beats are together when the lag is inside this; a flam starts to be
#: heard around 20 ms, and two kicks 30 ms apart are plainly two.
LOCK_S = 0.012
#: A bar is judged only when its lag is unambiguous: the best alignment beats
#: every alignment more than a sixteenth of a beat away by this factor. Two
#: records whose drums do not share a pulse (most pop, hip-hop and synthwave
#: pairs) peak anywhere and are judged nowhere — which is the verdict.
CONFIDENT = 1.4
#: Locked (or lockable by one shift): this share of the overlap's bars agree
#: on one lag, within AGREE_S of each other.
AGREE = 0.6
AGREE_S = 0.010


def _cache_path(path: str) -> Path:
    return ENV_DIR / (hashlib.sha1(path.encode("utf-8")).hexdigest()[:20] + ".npy")


def _decode(path: str) -> np.ndarray:
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-ac", "1",
                          "-ar", str(RATE), "-f", "s16le", "pipe:1"], capture_output=True, timeout=300)
    return np.frombuffer(out.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def kick_envelope(samples: np.ndarray) -> np.ndarray:
    """Rises in low-band power, at ENV_RATE. The power is smoothed below the
    bass's own frequencies (zero-phase, so it is not delayed) before it is
    differentiated: measured per 2 ms hop without that, the envelope followed
    each cycle of a 50 Hz kick and its derivative was ripple, not onsets."""
    from scipy.signal import butter, sosfiltfilt
    if len(samples) < RATE:
        return np.zeros(0)
    low = sosfiltfilt(butter(4, 150, btype="low", fs=RATE, output="sos"), samples)
    power = sosfiltfilt(butter(2, 30, btype="low", fs=RATE, output="sos"), low * low)
    e = np.log(np.maximum(power[::ENV_HOP], 1e-9))
    return np.maximum(0.0, np.diff(e, prepend=e[0])).astype(np.float32)


def envelope(path: str) -> Optional[np.ndarray]:
    """The record's low-band onset envelope at ENV_RATE, cached beside the ticks."""
    cache = _cache_path(path)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    try:
        if cache.exists() and cache.stat().st_mtime >= mtime:
            return np.load(cache).astype(np.float32)
    except (OSError, ValueError):
        pass
    try:
        env = kick_envelope(_decode(path))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if len(env) < ENV_RATE * 10:
        return None
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(f".{cache.name}.{os.getpid()}.tmp.npy")
        np.save(tmp, env.astype(np.float16))
        os.replace(tmp, cache)
    except OSError:
        pass
    return env.astype(np.float32)


def _at(env: np.ndarray, own: np.ndarray) -> np.ndarray:
    """The envelope sampled at `own` seconds of its record (0 outside it)."""
    return np.interp(own * ENV_RATE, np.arange(len(env)), env, left=0.0, right=0.0)


@dataclass
class Verdict:
    locked: bool
    bars: int                                 # bars in the overlap
    judged: int                               # bars with a clear lag
    lags_ms: list = field(default_factory=list)   # per judged bar, + = incoming late
    worst_ms: float = 0.0
    median_ms: float = 0.0
    walk_ms: float = 0.0                      # change in lag from the first judged quarter to the last
    why: str = ""
    correction_ms: float | None = None        # the lag the bars agree on, when they do
    agree: int = 0                            # bars agreeing on it

    def summary(self) -> str:
        return (f"{'locked' if self.locked else 'NOT locked'}: {self.agree}/{self.bars} bars agree "
                f"({self.judged} clear), at {self.median_ms:+.0f} ms, worst {self.worst_ms:.0f} ms, walk {self.walk_ms:+.0f} ms"
                + (f" — {self.why}" if self.why else ""))


def bar_lags(out_env: np.ndarray, out_ratio: float, in_env: np.ndarray, in_ratio: float,
             in_start: float, in_offset: float, drop: float, length: float, beat: float) -> list:
    """[(bar index, lag seconds or None)] through the overlap. Times are seconds
    of the outgoing as played (its own time = played × out_ratio); the incoming
    starts at played `in_start` from its own `in_offset` and plays at `in_ratio`."""
    bar = 4 * beat
    n = max(1, int(round(length / bar)))
    step = 1.0 / ENV_RATE
    # A quarter beat either way: an off-beat bassline half a beat away rises in
    # the same band as the kick, and must never be the alignment chosen.
    reach = int(beat / 4 * ENV_RATE)
    smear = np.hanning(5)
    out = []
    for k in range(n):
        t0 = drop + k * bar
        t = np.arange(t0 - beat / 2, t0 + bar + beat / 2, step)
        a = _at(out_env, t * out_ratio)
        b = _at(in_env, in_offset + (t - in_start) * in_ratio)
        a, b = np.convolve(a, smear, "same"), np.convolve(b, smear, "same")
        if a.max() <= 0 or b.max() <= 0:
            out.append((k, None))
            continue
        a, b = a - a.mean(), b - b.mean()
        m = len(a)
        lags = np.arange(-reach, reach + 1)
        cc = np.array([np.dot(a[max(0, l):m - max(0, -l)], b[max(0, -l):m - max(0, l)]) for l in lags])
        best = int(np.argmax(cc))
        if cc[best] <= 0:
            out.append((k, None))
            continue
        away = max(1, int(beat / 16 * ENV_RATE))
        others = np.concatenate([cc[:max(0, best - away)], cc[best + away + 1:]])
        rival = float(others.max()) if len(others) else 0.0
        if rival > 0 and cc[best] < CONFIDENT * rival:
            out.append((k, None))
            continue
        frac = 0.0
        if 0 < best < len(cc) - 1:
            l, c, r = cc[best - 1], cc[best], cc[best + 1]
            d = l - 2 * c + r
            frac = 0.5 * (l - r) / d if d else 0.0
        # cc[l] pairs a[i + l] with b[i]: the incoming onset at i meets the
        # outgoing's at i + l, so a positive lag is the incoming early.
        out.append((k, -float((lags[best] + frac) / ENV_RATE)))
    return out


def judge(lags: list) -> Verdict:
    """Locked when most bars agree on one lag and it is inside LOCK_S, not
    walking. `correction` is that agreed lag whatever its size: a blend whose
    bars all agree it is 53 ms late is fixed by starting it 53 ms earlier."""
    vals = [v for _, v in lags if v is not None]
    n = len(lags)
    if not n:
        return Verdict(False, 0, 0, why="no overlap")
    ms = np.array(vals) * 1000 if vals else np.zeros(0)
    if len(ms) < AGREE * n:
        return Verdict(False, n, len(vals), [round(float(v), 1) for v in ms],
                       why=f"no common beat — only {len(vals)} of {n} bars line up clearly")
    centre = float(np.median(ms))
    inl = ms[np.abs(ms - centre) <= AGREE_S * 1000]
    if len(inl) < AGREE * n:
        return Verdict(False, n, len(vals), [round(float(v), 1) for v in ms],
                       median_ms=centre, why=f"no common beat — the bars disagree ({len(inl)} of {n} agree)")
    centre = float(np.median(inl))
    q = max(1, len(inl) // 4)
    walk = float(np.median(inl[-q:]) - np.median(inl[:q]))
    worst = float(np.max(np.abs(inl)))
    locked = abs(centre) <= LOCK_S * 1000 and worst <= 2 * LOCK_S * 1000
    v = Verdict(locked, n, len(vals), [round(float(x), 1) for x in ms], worst, centre, walk)
    v.correction_ms = centre
    v.agree = len(inl)
    if not locked:
        v.why = f"every bar agrees the incoming is {centre:+.0f} ms off"
    return v


def check(out_path: str, out_ratio: float, in_path: str, in_ratio: float, in_start: float,
          in_offset: float, drop: float, length: float, beat: float) -> Verdict:
    """Measure a planned blend (see `bar_lags`) and judge it."""
    a, b = envelope(out_path), envelope(in_path)
    if a is None or b is None:
        return Verdict(False, 0, 0, why="a record could not be read")
    return judge(bar_lags(a, out_ratio, b, in_ratio, in_start, in_offset, drop, length, beat))
