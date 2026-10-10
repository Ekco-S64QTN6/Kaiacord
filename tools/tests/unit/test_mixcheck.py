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


def _kicks_then_pads(secs_kick, secs_total):
    """Kicks for `secs_kick`, then a soft swell with no kick to the end."""
    env = clicks(BPM, secs_total)
    cut = int(secs_kick * M.ENV_RATE)
    rng = np.random.default_rng(7)
    env[cut:] = np.abs(rng.normal(0, env[:cut].mean() * 0.05, len(env) - cut))
    return env


def test_bars_where_only_one_record_has_a_kick_cannot_clash(monkeypatch):
    """A beatless outro under a groove has no kick to flam with: where its
    claps and hats are quiet too, it is clear. Over kicks that scatter against
    each other it is not."""
    out = _kicks_then_pads(60, 120)
    quiet = _kicks_then_pads(60, 120)                        # its claps stop with its kick
    inc = clicks(BPM, 120, offset=0.5, pattern=(1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 1), jitter=0.09, seed=3)
    envs = {("out-pads", "kick"): out, ("out-pads", "hits"): quiet, ("in-loose", "kick"): inc,
            ("in-loose", "hits"): inc}
    monkeypatch.setattr(M, "envelope", lambda p, band="kick": envs[(p, band)])
    M._levels.clear()
    in_pads = M.check("out-pads", 1.0, "in-loose", 1.0, 64.0 - 0.5, 0.0, 64.0, 32 * BEAT, BEAT)
    on_kicks = M.check("out-pads", 1.0, "in-loose", 1.0, 16 * BEAT - 0.5, 0.0, 16 * BEAT, 32 * BEAT, BEAT)
    assert in_pads.locked and "never two kicks" in in_pads.why
    assert not on_kicks.locked


def test_no_shared_kick_is_not_enough_when_the_claps_clash(monkeypatch):
    """No kick on one side, but claps and hats on both, 60 ms apart: heard as
    a mess whatever the low band says. Not a blend."""
    out = _kicks_then_pads(60, 120)
    claps_out = clicks(BPM, 120, offset=0.0)
    claps_in = clicks(BPM, 120, offset=0.56)                 # 60 ms off the outgoing's
    inc = clicks(BPM, 120, offset=0.5)
    envs = {("out", "kick"): out, ("out", "hits"): claps_out, ("in", "kick"): inc, ("in", "hits"): claps_in}
    monkeypatch.setattr(M, "envelope", lambda p, band="kick": envs[(p, band)])
    M._levels.clear()
    v = M.check("out", 1.0, "in", 1.0, 64.0 - 0.5, 0.0, 64.0, 32 * BEAT, BEAT)
    assert not v.locked and "clash" in v.why


def test_a_short_overlap_must_agree_in_more_of_its_bars():
    """Searched in many places, a short overlap agrees by chance: four bars
    must all agree, eight need six."""
    assert M.needed(4) == 4 and M.needed(8) == 6 and M.needed(16) == 10
    three_of_four = [(0, 0.0), (1, 0.001), (2, -0.001), (3, 0.08)]
    assert not M.judge(three_of_four).locked
    assert M.judge([(k, 0.001 * (k % 2)) for k in range(4)]).locked


def test_find_blend_tries_other_places_before_giving_up():
    """The first place does not lock; the search moves the incoming's cue and
    the outgoing's mix-out until one does, and says where."""
    from utils.audio import library, records as R, setlist
    from utils.audio.beatgrid import Grid
    g = Grid(124.0, 0.0, 6.0, bar_known=True)
    nxt = R.Next(library.Record("/m/in.mp3", "", "in", 124.0, "8A", "House"), 300.0, 0.0, g, 0.0, None)
    tried = []

    def verify(out_path, out_ratio, in_path, plan):
        tried.append((round(plan.drop, 1), round(plan.offset, 1)))
        ok = plan.offset > 30.0                  # only a cue 16+ bars in locks
        return M.Verdict(ok, 16, 16, agree=16 if ok else 2), 0.0
    found = setlist.find_blend(100.0, "/m/out.mp3", 1.0, g, 300.0, nxt, "end", 64, verify_fn=verify)
    assert found is not None
    plan, v, shift, how = found
    assert plan.kind == "blend" and plan.offset > 30.0 and how["cue"] in (16, 32) and len(tried) > 1
    nothing = setlist.find_blend(100.0, "/m/out.mp3", 1.0, g, 300.0, nxt, "end", 64,
                                 verify_fn=lambda *a: (M.Verdict(False, 16, 2), 0.0))
    assert nothing is None


def _mp3(path, tag: bytes, audio: bytes):
    size = len(tag)
    syncsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    path.write_bytes(b"ID3\x03\x00\x00" + syncsafe + tag + audio)


def test_a_retagged_record_is_not_measured_again(tmp_path):
    """The graph keeps a record's pairs when only its tags changed (the
    metadata script rewrites them across the library); new audio is new."""
    import os
    from utils.audio import library, setlist
    p = tmp_path / "a.mp3"
    _mp3(p, b"TIT2 old title", b"\xff\xfb" + bytes(range(256)) * 400)
    r = library.Record(str(p), "A", "a", 124.0, "8A", "House")
    g = {"method": setlist.METHOD, "records": {str(p): {"mtime": os.path.getmtime(p) - 100,
                                                        "sig": library.audio_signature(str(p))}}}
    _mp3(p, b"TIT2 a much longer new title, with cover art", b"\xff\xfb" + bytes(range(256)) * 400)
    assert not setlist.needs_build(g, [r])
    _mp3(p, b"TIT2 old title", b"\xff\xfb" + bytes(range(255, -1, -1)) * 400)
    assert setlist.needs_build(g, [r])


def test_sets_hold_no_song_twice_and_run_about_an_hour():
    """A walk never takes another file or mix of a song already in the set,
    and keeps going until it has an hour of music."""
    from utils.audio import library, setlist
    names = ["One", "Two", "Two (Club Mix)", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen"]
    recs = {f"/m/{i}.mp3": library.Record(f"/m/{i}.mp3", "Same Artist", n, 124.0, "8A", "House")
            for i, n in enumerate(names)}
    paths = list(recs)
    edge = {"ms": 0.0, "agree": 14, "bars": 16, "ratio": 1.0, "beats": 64, "back": 0, "cue": None}
    g = {"records": {p: {"seconds": 300.0} for p in paths},
         "edges": {a: {b: edge for b in paths if b != a} for a in paths}}
    sets = setlist.make_sets(g, recs)
    assert sets
    for st in sets:
        assert not any(library.same_song(recs[a], recs[b]) for i, a in enumerate(st) for b in st[i + 1:])
        assert setlist.played_seconds(g, st, recs) >= setlist.SET_MIN_S
