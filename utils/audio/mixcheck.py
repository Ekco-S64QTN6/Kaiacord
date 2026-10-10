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
#: A record has no kick in a bar whose low-band onset energy is under this share
#: of its kick level (`kick_level`). Two beats can only flam where both have
#: one: a beatless outro under a drum intro, or a pad intro over a groove, is
#: overlapped safely whatever the lags say — and the lags measured there are
#: noise (they wander to the edge of the search on a pad's swells).
NO_KICK = 0.4


#: Bars with no shared kick may have claps and hats a little apart in at most
#: this share of the bars where both have them (and none when fewer than five).
HITS_CLASH = 0.2


def needed(n: int) -> int:
    """Bars that must agree out of `n` that can clash. A blend is searched for
    in many places, and on a short overlap noise agrees by chance (a random lag
    falls inside AGREE_S about one time in twelve): four bars must all agree,
    eight need six, longer overlaps AGREE of them."""
    import math
    return n if n <= 4 else max(6, math.ceil(AGREE * n)) if n <= 8 else math.ceil(AGREE * n)


#: The second band listened to: claps, snares and hats (2–5 kHz). Where no
#: kick holds two records together, these are the rhythm that is heard, and a
#: bar with no kick on one side can still clash on them.
HITS_DIR = ENV_DIR.parent / "env_hits"


def _cache_path(path: str, band: str = "kick") -> Path:
    return (ENV_DIR if band == "kick" else HITS_DIR) / (hashlib.sha1(path.encode("utf-8")).hexdigest()[:20] + ".npy")


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
    return _onsets(low)


def hits_envelope(samples: np.ndarray) -> np.ndarray:
    """Rises in 2–5 kHz power (claps, snares, hats), at ENV_RATE."""
    from scipy.signal import butter, sosfiltfilt
    if len(samples) < RATE:
        return np.zeros(0)
    return _onsets(sosfiltfilt(butter(4, [2000, 5000], btype="band", fs=RATE, output="sos"), samples))


def _onsets(band: np.ndarray) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt
    power = sosfiltfilt(butter(2, 30, btype="low", fs=RATE, output="sos"), band * band)
    e = np.log(np.maximum(power[::ENV_HOP], 1e-9))
    return np.maximum(0.0, np.diff(e, prepend=e[0])).astype(np.float32)


#: Envelopes held in memory, most recently used last: a search measures the
#: same two records dozens of times.
_MEM: dict = {}
MEM_RECORDS = 48


def envelope(path: str, band: str = "kick") -> Optional[np.ndarray]:
    """The record's onset envelope at ENV_RATE — "kick" (low band) or "hits"
    (2–5 kHz) — cached beside the ticks. One decode makes both."""
    cache = _cache_path(path, band)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    held = _MEM.pop((path, band), None)
    if held is not None and held[0] == mtime:
        _MEM[(path, band)] = held
        return held[1]
    try:
        if cache.exists() and cache.stat().st_mtime < mtime:
            # Older than the file: still good if only its tags changed.
            from utils.audio.library import audio_signature
            sig = cache.with_suffix(".sig")
            if sig.exists() and sig.read_text().strip() == (audio_signature(path) or "-"):
                os.utime(cache)
        if cache.exists() and cache.stat().st_mtime >= mtime:
            env = np.load(cache).astype(np.float32)
            _MEM[(path, band)] = (mtime, env)
            while len(_MEM) > MEM_RECORDS:
                _MEM.pop(next(iter(_MEM)))
            return env
    except (OSError, ValueError):
        pass
    try:
        samples = _decode(path)
        envs = {"kick": kick_envelope(samples), "hits": hits_envelope(samples)}
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if len(envs["kick"]) < ENV_RATE * 10:
        return None
    from utils.audio.library import audio_signature
    sig = audio_signature(path) or ""
    for b, env in envs.items():
        c = _cache_path(path, b)
        try:
            c.parent.mkdir(parents=True, exist_ok=True)
            tmp = c.with_name(f".{c.name}.{os.getpid()}.tmp.npy")
            np.save(tmp, env.astype(np.float16))
            os.replace(tmp, c)
            c.with_suffix(".sig").write_text(sig)
        except OSError:
            pass
    return envs[band].astype(np.float32)


_levels: dict = {}


def kick_level(path: str, env: Optional[np.ndarray] = None, band: str = "kick") -> Optional[float]:
    """The record's onset energy per second in `band` where it plays: the 75th
    percentile over one-second windows, so breakdowns and a long intro do not
    pull it down."""
    if (path, band) in _levels:
        return _levels[(path, band)]
    env = envelope(path, band) if env is None else env
    if env is None:
        return None
    w = int(ENV_RATE)
    n = len(env) // w
    if n < 10:
        return None
    lvl = float(np.percentile(env[:n * w].reshape(n, w).sum(axis=1), 75))
    _levels[(path, band)] = lvl if lvl > 0 else None
    return _levels[(path, band)]


def kick_bars(env: np.ndarray, level: Optional[float], own_times: list, bar_s: float) -> list:
    """For each bar starting at `own_times` (seconds of the record, `bar_s`
    long in its own time): does it have a kick? Unknown level: assume so."""
    if not level:
        return [True] * len(own_times)
    out = []
    for t0 in own_times:
        a, b = int(max(0.0, t0) * ENV_RATE), int(max(0.0, t0 + bar_s) * ENV_RATE)
        e = float(env[a:b].sum()) / bar_s if b > a else 0.0
        out.append(e >= NO_KICK * level)
    return out


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
    # Both envelopes sampled once over the whole overlap; each bar's window
    # (half a beat either side of the bar) is a slice of it.
    t_all = np.arange(drop - beat / 2, drop + n * bar + beat / 2 + step, step)
    a_all = _at(out_env, t_all * out_ratio)
    b_all = _at(in_env, in_offset + (t_all - in_start) * in_ratio)
    w = int(round((bar + beat) / step))
    lags = np.arange(-reach, reach + 1)
    out = []
    for k in range(n):
        i0 = int(round(k * bar / step))
        a, b = a_all[i0:i0 + w], b_all[i0:i0 + w]
        if len(a) < w // 2:
            out.append((k, None))
            continue
        a, b = np.convolve(a, smear, "same"), np.convolve(b, smear, "same")
        if a.max() <= 0 or b.max() <= 0:
            out.append((k, None))
            continue
        a, b = a - a.mean(), b - b.mean()
        # cc[j] = sum_i a[i + lags[j]] * b[i], a outside its window counted as 0.
        cc = np.correlate(np.concatenate([np.zeros(reach), a, np.zeros(reach)]), b, "valid")
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


def judge(lags: list, both: Optional[list] = None) -> Verdict:
    """Locked when most bars agree on one lag and it is inside LOCK_S, not
    walking. `correction` is that agreed lag whatever its size: a blend whose
    bars all agree it is 53 ms late is fixed by starting it 53 ms earlier.

    `both` (per bar: do both records have a kick there?) leaves out the bars
    where at most one does — nothing to flam — so the verdict is over the bars
    that can clash; with none of those the blend is clear."""
    total = len(lags)
    if both is not None and len(both) == total:
        lags = [(k, v) for (k, v), b in zip(lags, both) if b]
        if total and not lags:
            v = Verdict(True, total, 0, why="never two kicks at once")
            v.correction_ms, v.agree = 0.0, total
            return v
    vals = [v for _, v in lags if v is not None]
    n = len(lags)
    if not n:
        return Verdict(False, 0, 0, why="no overlap")
    ms = np.array(vals) * 1000 if vals else np.zeros(0)
    if len(ms) < needed(n):
        return Verdict(False, n, len(vals), [round(float(v), 1) for v in ms],
                       why=f"no common beat — only {len(vals)} of {n} bars line up clearly")
    centre = float(np.median(ms))
    inl = ms[np.abs(ms - centre) <= AGREE_S * 1000]
    if len(inl) < needed(n):
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
    if total > n:                                 # bars with one kick or none: clear, counted as agreeing
        v.bars, v.agree = total, len(inl) + (total - n)
        v.why = (v.why + "; " if v.why else "") + f"{total - n} of {total} bars have one kick or none"
    if not locked:
        v.why = f"every bar agrees the incoming is {centre:+.0f} ms off"
    return v


def check(out_path: str, out_ratio: float, in_path: str, in_ratio: float, in_start: float,
          in_offset: float, drop: float, length: float, beat: float) -> Verdict:
    """Measure a planned blend (see `bar_lags`) and judge it."""
    a, b = envelope(out_path), envelope(in_path)
    if a is None or b is None:
        return Verdict(False, 0, 0, why="a record could not be read")
    lags = bar_lags(a, out_ratio, b, in_ratio, in_start, in_offset, drop, length, beat)
    bar = 4 * beat
    t0s = [drop + k * bar for k, _ in lags]
    own_a = [t * out_ratio for t in t0s]
    own_b = [in_offset + (t - in_start) * in_ratio for t in t0s]
    ka = kick_bars(a, kick_level(out_path, a), own_a, bar * out_ratio)
    kb = kick_bars(b, kick_level(in_path, b), own_b, bar * in_ratio)
    both = [x and y for x, y in zip(ka, kb)]
    v = judge(lags, both)
    if not v.locked or all(both):
        return v
    # Bars with one kick or none: nothing low to flam, but the claps, snares
    # and hats still play over each other there, with no kick to hold them.
    ha, hb = envelope(out_path, "hits"), envelope(in_path, "hits")
    if ha is None or hb is None:
        v.locked, v.why = False, "the bars without a shared kick could not be heard"
        return v
    hl = bar_lags(ha, out_ratio, hb, in_ratio, in_start, in_offset, drop, length, beat)
    pa = kick_bars(ha, kick_level(out_path, ha, "hits"), own_a, bar * out_ratio)
    pb = kick_bars(hb, kick_level(in_path, hb, "hits"), own_b, bar * in_ratio)
    heard = [hl[i][1] for i, k in enumerate(both) if not k and pa[i] and pb[i] and hl[i][1] is not None]
    clash = sum(1 for x in heard if abs(x) > 2 * AGREE_S)
    if clash > int(HITS_CLASH * len(heard)):
        v.locked = False
        v.why = f"no shared kick in {len(both) - sum(both)} bars, and the claps and hats clash in {clash} of {len(heard)}"
    elif heard:
        v.why += f"; claps and hats agree where no kick does ({len(heard) - clash} of {len(heard)})"
    return v
