"""The ear: whether a blend's beats lock, measured on the records themselves.

Click tracks with known offsets — the judge must report the offset to the
millisecond, correct it, and refuse a pair whose beats share no pulse.
"""
import numpy as np
import pytest

from utils.audio import mixcheck as M
from utils.audio.beatgrid import RATE


def clicks(bpm, secs, offset=0.0, pattern=(1, 1, 1, 1), jitter=0.0, seed=0):
    """A kick-like thump on the beats `pattern` marks."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(secs * RATE), np.float32)
    n = np.arange(int(0.08 * RATE))
    burst = np.sin(2 * np.pi * 60 * n / RATE) * np.exp(-n / (0.02 * RATE))
    beat, t, i = 60 / bpm, offset, 0
    while t < secs - 0.1:
        if pattern[i % len(pattern)]:
            s = int((t + rng.uniform(-jitter, jitter)) * RATE)
            x[s:s + len(burst)] += burst
        t += beat
        i += 1
    return M.kick_envelope(x)


BPM, BEAT = 128, 60 / 128
OUT = None


def setup_module():
    global OUT
    OUT = clicks(BPM, 120)


@pytest.mark.parametrize("off_ms", [0, 8, -30, 54, 100])
def test_the_offset_is_measured_to_the_millisecond(off_ms):
    inc = clicks(BPM, 120, offset=0.5)
    start = 16 * BEAT + off_ms / 1000 - 0.5
    v = M.judge(M.bar_lags(OUT, 1.0, inc, 1.0, start, 0.0, 16 * BEAT, 32 * BEAT, BEAT))
    assert v.median_ms == pytest.approx(off_ms, abs=1.0)
    assert v.locked == (abs(off_ms) <= M.LOCK_S * 1000)
    if not v.locked:
        assert v.correction_ms == pytest.approx(off_ms, abs=1.0)


def test_a_stretched_record_is_measured_in_played_time():
    from utils.audio import library
    inc = clicks(132, 120, offset=0.3)
    r = library.tempo_ratio(BPM, 132)
    v = M.judge(M.bar_lags(OUT, 1.0, inc, r, 16 * BEAT - 0.3 / r, 0.0, 16 * BEAT, 32 * BEAT, BEAT))
    assert v.locked and abs(v.median_ms) < 1.5


def test_beats_that_share_no_pulse_are_not_a_blend():
    """Two grooves whose hits scatter against each other: no lag agreed, no
    correction offered — the transition must be a switch."""
    inc = clicks(BPM, 120, offset=0.5, pattern=(1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1), jitter=0.09, seed=3)
    v = M.judge(M.bar_lags(OUT, 1.0, inc, 1.0, 16 * BEAT - 0.5, 0.0, 16 * BEAT, 32 * BEAT, BEAT))
    assert not v.locked and v.correction_ms is None


def test_a_drifting_pair_is_not_locked():
    inc = clicks(128.6, 120, offset=0.5)
    v = M.judge(M.bar_lags(OUT, 1.0, inc, 1.0, 16 * BEAT - 0.5, 0.0, 16 * BEAT, 64 * BEAT, BEAT))
    assert not v.locked


def test_an_off_beat_hit_is_never_chosen():
    """The search reaches a quarter beat: something on the off-beat (a rolling
    bassline) cannot become the alignment."""
    inc = clicks(BPM, 120, offset=0.5)
    start = 16 * BEAT + BEAT / 2 - 0.5                 # every hit exactly on the off-beat
    v = M.judge(M.bar_lags(OUT, 1.0, inc, 1.0, start, 0.0, 16 * BEAT, 32 * BEAT, BEAT))
    assert not v.locked and (v.correction_ms is None or abs(v.correction_ms) <= BEAT / 4 * 1000 + 1)


def test_verify_moves_a_blend_by_the_measured_amount(monkeypatch):
    from types import SimpleNamespace
    from utils.audio import setlist
    inc = clicks(BPM, 120, offset=0.5)
    monkeypatch.setattr(M, "envelope", lambda p: OUT if p == "out" else inc)
    plan = SimpleNamespace(ratio=1.0, start=16 * BEAT + 0.054 - 0.5, offset=0.0, drop=16 * BEAT,
                           length=32 * BEAT, beat=BEAT)
    v, shift = setlist.verify("out", 1.0, "in", plan)
    assert v.locked and shift == pytest.approx(-0.054, abs=0.002)


def test_sets_follow_only_measured_locks():
    from utils.audio import library, setlist
    recs = {f"/m/{c}.mp3": library.Record(path=f"/m/{c}.mp3", artist="", title=c, bpm=125, key="8A", genre="House")
            for c in "abcdefg"}
    edge = {"ms": 0.0, "agree": 14, "bars": 16, "ratio": 1.0}
    chain = list(recs)
    g = {"edges": {a: {b: edge} for a, b in zip(chain, chain[1:])}}
    g["edges"][chain[2]][chain[5]] = edge
    sets = setlist.make_sets(g, recs)
    assert sets
    for s in sets:
        assert len(s) == len(set(s))
        for a, b in zip(s, s[1:]):
            assert b in g["edges"][a]
