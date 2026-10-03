"""!music records: choosing the next record, and mixing one into the next."""
import io
import json
import random
import time

import numpy as np
import pytest

from utils.audio import library
from utils.audio import records as R
from utils.audio.beatgrid import Grid
from utils.audio.records import FRAME_BYTES, FRAMES_PER_S, RATE, CrossfadeSource, Deck, Next, plan_transition, gains


def rec(name, bpm, key, genre="House"):
    return library.Record(path=f"/music/{name}.mp3", artist="A", title=name, bpm=bpm, key=key, genre=genre)


# ── The crate ─────────────────────────────────────────────────────────

def test_the_catalog_loads_only_records_that_exist(tmp_path):
    real = tmp_path / "a.mp3"
    real.write_bytes(b"x")
    cat = tmp_path / "dj_catalog.json"
    cat.write_text(json.dumps([
        {"filepath": str(real), "bpm": 124, "key": "8A", "genre": "House", "artist": "X", "title": "One"},
        {"filepath": str(tmp_path / "gone.mp3"), "bpm": 120, "key": "8A"},
        {"filepath": str(real), "bpm": "n/a", "key": "13Z"},
        "not a row",
    ]))
    crate = library.load(cat)
    assert [r.title for r in crate] == ["One", "a"]
    assert crate[1].bpm is None and crate[1].key is None
    assert library.load("") == [] and library.load(tmp_path / "missing.json") == []


@pytest.mark.parametrize("a, b, step", [
    ("8A", "8A", 0), ("8A", "9A", 1), ("12A", "1A", 1), ("8A", "8B", 1),
    ("8A", "10A", 2), ("8A", "9B", None), ("8A", "3A", None), ("8A", None, None),
])
def test_moves_round_the_camelot_wheel(a, b, step):
    assert library.key_step(a, b) == step


def test_tempo_matches_count_half_and_double_time():
    assert library.tempo_ratio(124, 120) == pytest.approx(124 / 120)
    assert library.tempo_ratio(174, 88) == pytest.approx(87 / 88)       # half time
    assert library.tempo_ratio(124, 100) is None                         # too far to stretch
    assert library.tempo_ratio(None, 120) is None


def test_the_next_record_fits_the_last():
    current = rec("now", 124, "8A")
    crate = [current, rec("clash", 90, "3B", "Pop"), rec("fits", 125, "9A"), rec("ok", 123, "8B", "Techno")]
    picks = {library.next_record(current, crate, [current.path], random.Random(i)).title for i in range(30)}
    assert "clash" not in picks and "fits" in picks


def test_nothing_recent_is_played_again_while_others_remain():
    crate = [rec(str(i), 124, "8A") for i in range(5)]
    played = [r.path for r in crate[:4]]
    assert library.next_record(crate[0], crate, played).title == "4"


def test_her_opener_follows_her_mood():
    crate = [rec("slow", 90, "8A"), rec("mid", 120, "8A"), rec("fast", 140, "8A")]
    assert library.opener(crate, {"arousal": 0.1}, 14).title == "slow"
    assert library.opener(crate, {"arousal": 0.9}, 14).title == "fast"
    assert library.opener(crate, {"arousal": 0.9}, 3).title == "mid"       # late: no faster than mid


def test_a_request_finds_a_record_by_its_words():
    crate = [rec("Drowning", 176, "8A"), rec("We Are Connected", 130, "2A")]
    assert library.find(crate, "connected").title == "We Are Connected"
    assert library.find(crate, "nothing like it") is None


# ── The mix ──────────────────────────────────────────────────────────

def tone(value: int, seconds: float):
    """A fake decoded record: every sample `value`."""
    frames = int(seconds * FRAMES_PER_S)
    data = np.full(frames * FRAME_BYTES // 2, value, dtype=np.int16).tobytes()
    return lambda path, ratio, gain=0.0, offset=0.0: io.BytesIO(data)


def level(frame: bytes) -> float:
    return float(np.frombuffer(frame, dtype=np.int16).astype(np.float32).mean())


def wait_for(deck, frames):
    deadline = time.time() + 2
    while time.time() < deadline and len(deck._frames) < frames and not deck._eof:
        time.sleep(0.01)


STEADY = Grid(bpm=120.0, downbeat=0.0, contrast=8.0)          # a bar every 2 s
LOOSE = Grid(bpm=120.0, downbeat=0.0, contrast=2.7)            # rock, breaks: Big Country measured 2.7


def nxt(grid=STEADY, seconds=20.0, name="two"):
    return Next(rec(name, 120, "8A"), seconds, 0.0, grid)


def test_a_blend_drops_the_incoming_downbeat_on_an_outgoing_bar():
    late_downbeat = Grid(bpm=120.0, downbeat=0.75, contrast=8.0)
    plan = plan_transition(3.1, 1.0, STEADY, 60.0, nxt(late_downbeat), "skip", 16, lead=2.0)
    assert plan.kind == "blend"
    assert plan.drop % 2.0 == pytest.approx(0.0, abs=1e-9)          # on a bar
    assert plan.drop >= 3.1 + 0.75 + 2.0                            # room to start the incoming
    assert plan.drop - plan.start == pytest.approx(0.75)            # its downbeat lands on the drop
    assert plan.length == pytest.approx(8.0)                        # sixteen beats


def test_an_end_blend_finishes_before_the_record_does():
    plan = plan_transition(10.0, 1.0, STEADY, 60.0, nxt(), "end", 16, lead=2.0)
    assert plan.kind == "blend" and plan.done <= 60.0 and plan.drop > 40.0


def test_a_loose_beat_is_faded_not_blended():
    """Beat against beat, a record without a steady kick is a clash — but a
    hard cut with a gap was worse. It is a fade: equal-power, from the new
    record's first sound, the basslines handed over halfway."""
    late = Next(rec("two", 120, "8A"), 20.0, 0.0, LOOSE, lead=1.7)
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, late, "skip")
    assert plan.kind == "fade" and plan.fallback == "beat" and plan.offset == pytest.approx(1.7)
    assert plan.drop % 2.0 == pytest.approx(0.0, abs=1e-9) and plan.length == pytest.approx(16.0)
    assert plan_transition(3.0, 1.0, LOOSE, 60.0, nxt(STEADY), "skip").kind == "fade"
    assert plan_transition(3.0, 1.0, None, 60.0, nxt(STEADY), "skip").kind == "fade"

def test_tempos_too_far_apart_are_faded_at_their_own_speed():
    fast = Grid(bpm=150.0, downbeat=0.0, contrast=8.0)
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(fast), "skip")
    assert plan.kind == "fade" and plan.fallback == "tempo" and plan.ratio == 1.0
    assert plan.drop % 2.0 == pytest.approx(0.0, abs=1e-9)

def test_a_fade_keeps_one_bassline_and_constant_power():
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(LOOSE), "skip")
    t = np.arange(plan.drop, plan.done, 0.01)
    out_low, out_mid, out_high, in_low, in_mid, in_high = gains(plan, t)
    assert np.allclose(out_low + in_low, 1.0)
    assert np.allclose(out_high ** 2 + in_high ** 2, 1.0)


def test_only_no_room_at_all_makes_a_cut():
    plan = plan_transition(9.0, 1.0, STEADY, 10.0, nxt(LOOSE), "end")
    assert plan.kind == "cut" and plan.fallback == "room"

def test_a_blend_swaps_the_bass_halfway_and_keeps_one_bassline():
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(), "skip")
    t = np.arange(plan.drop - 1, plan.done + 1, 0.001)
    out_low, out_mid, out_high, in_low, in_mid, in_high = gains(plan, t)
    assert np.allclose(out_low + in_low, 1.0)                       # never two basslines, never none
    swap = plan.drop + plan.length / 2
    assert np.all(in_low[t < swap] == 0) and np.all(in_low[t > swap + plan.beat] == 1)
    assert out_high[t <= plan.drop].min() == 1 and in_high[t >= plan.done].min() == pytest.approx(1)


def _source(first_value=1000, second_value=-1000, grid=STEADY, out_grid=STEADY, fine=None):
    first = Deck(rec("one", 120, "8A"), 1.0, 20.0, tone(first_value, 20.0))
    changed = []
    queue = [nxt(grid)]
    src = CrossfadeSource(first, lambda deck: queue.pop() if queue else None,
                          stream_factory=tone(second_value, 20.0), on_change=changed.append,
                          grid_at=lambda record, start, seconds: out_grid, mix_beats=16)
    src._fine = lambda deck, plan: fine
    wait_for(first, 100)
    deadline = time.time() + 2
    while src._queued is None and time.time() < deadline:
        time.sleep(0.01)
    return src, changed


def _plan(src, mode="skip"):
    src._begin_planning(mode)
    deadline = time.time() + 5
    while src.plan is None and time.time() < deadline:
        time.sleep(0.01)
    assert src.plan is not None
    return src.plan


def test_the_incoming_starts_on_the_sample_it_was_planned_for(monkeypatch):
    # A step instead of the fade's ramp, so the incoming's first sample shows.
    monkeypatch.setattr(R, "gains", lambda plan, t: ((t < plan.drop) * 1.0,) * 3 + ((t >= plan.drop) * 1.0,) * 3)
    src, changed = _source(grid=LOOSE)
    plan = _plan(src)
    out = []
    while len(out) < int((plan.drop + 1.0) * FRAMES_PER_S):
        out.append(src.read())
        if src.incoming is not None:
            wait_for(src.incoming, 30)
    samples = np.frombuffer(b"".join(out), dtype=np.int16).reshape(-1, 2)[:, 0]
    first_incoming = int(np.argmax(samples < 0))
    assert abs(first_incoming - plan.drop * RATE) <= 1


def test_a_blend_hands_over_to_the_next_record():
    src, changed = _source()
    plan = _plan(src)
    assert plan.kind == "blend"
    levels = []
    for _ in range(int((plan.done + 1.0) * FRAMES_PER_S)):
        levels.append(level(src.read()))
        if src.incoming is not None:
            wait_for(src.incoming, 30)
    assert levels[0] == pytest.approx(1000)
    assert any(-900 < x < 900 for x in levels)                     # a mix on the way
    assert levels[-1] == pytest.approx(-1000)
    assert [r.title for r in changed] == ["two"]


def test_a_kick_correction_too_large_to_trust_is_not_applied():
    a, _ = _source(fine=0.02)
    b, _ = _source(fine=0.2)
    c, _ = _source(fine=None)
    pa, pb, pc = _plan(a), _plan(b), _plan(c)
    assert pa.start == pytest.approx(pc.start + 0.02)
    assert pb.start == pytest.approx(pc.start)


def test_the_set_ends_when_nothing_comes_next():
    first = Deck(rec("one", 124, "8A"), 1.0, 0.4, tone(500, 0.4))
    src = CrossfadeSource(first, lambda deck: None, grid_at=lambda *a: None)
    wait_for(first, 20)
    frames = [src.read() for _ in range(60)]
    assert b"" in frames


def test_a_late_voice_thread_is_counted():
    first = Deck(rec("one", 124, "8A"), 1.0, 5.0, tone(500, 5.0))
    src = CrossfadeSource(first, lambda deck: None, grid_at=lambda *a: None)
    wait_for(first, 20)
    src.read()
    src.read()
    time.sleep(R.LATE_S + 0.03)
    src.read()
    assert len(src.late) == 1 and src.late[0] >= R.LATE_S


def test_a_quiet_record_is_raised_but_never_past_its_peak(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from utils.audio.records import gain_db
    quiet = tmp_path / "quiet.wav"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-af", "volume=-30dB", str(quiet)], check=True)
    g = gain_db(str(quiet))
    assert g == 12.0              # raised toward the target, never more than 12 dB
    assert gain_db(str(tmp_path / "missing.wav")) == 0.0


def test_the_next_record_is_one_with_a_steady_opening_where_one_fits(monkeypatch):
    from utils.audio import beatgrid
    crate = [rec("now", 120, "8A"), rec("loose", 120, "8A"), rec("steady", 120, "8A")]
    session = R.RecordsSession.__new__(R.RecordsSession)
    session.crate, session.played, session._rng, session.requests = crate, [crate[0].path], random.Random(1), []
    monkeypatch.setattr(R, "probe_seconds", lambda path: 200.0)
    monkeypatch.setattr(R, "gain_db", lambda path: 0.0)
    monkeypatch.setattr(beatgrid, "grid_for", lambda path, bpm: STEADY if "steady" in path else LOOSE)
    order = iter([crate[1], crate[2]])
    monkeypatch.setattr(library, "next_record", lambda *a, **k: next(order, None))
    deck = Deck(crate[0], 1.0, 1.0, tone(0, 1.0))
    assert session._choose(deck).record.title == "steady"
    order = iter([crate[1], None])
    assert session._choose(deck).record.title == "loose"          # nothing steadier: still a record
    assert "loose" not in " ".join(session.played)                 # passed over, not marked played


def test_a_bar_that_could_not_be_counted_is_faded():
    unsure = Grid(bpm=120.0, downbeat=0.0, contrast=8.0, bar_known=False)
    assert plan_transition(3.0, 1.0, unsure, 60.0, nxt(STEADY), "skip").kind == "fade"
    assert plan_transition(3.0, 1.0, STEADY, 60.0, nxt(unsure), "skip").kind == "fade"

def _clicks(path, bpm, first, seconds, rate=44100):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    x = np.zeros(int(seconds * rate), np.float32)
    k = np.arange(int(0.03 * rate))
    kick = np.sin(2 * np.pi * 55 * k / rate) * np.exp(-k / (0.008 * rate))
    t, n = first, 0
    while t < seconds - 0.1:
        i = int(round(t * rate))
        x[i:i + len(kick)] += (0.9 if n % 4 == 0 else 0.6) * kick
        t += 60 / bpm
        n += 1
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(rate), "-ac", "1",
                    "-i", "pipe:0", str(path)], input=pcm.tobytes(), check=True)
    return str(path)


@pytest.mark.parametrize("bpm, first", [(123, 1.13), (115, 2.4), (126, 0.0)])
def test_bar_one_is_the_first_beat_and_bars_are_counted_from_it(tmp_path, bpm, first):
    """The accent guess picked the wrong beat of the bar on two of these three:
    kicks met kicks, and the incoming record's bar began on beat 2, 3 or 4."""
    from utils.audio import beatgrid
    beatgrid.grid_for.cache_clear()
    path = _clicks(tmp_path / "c.wav", bpm, first, 120)
    g = beatgrid.grid_for(path, bpm)
    assert g.bar_known and g.downbeat == pytest.approx(first, abs=0.012)
    here = beatgrid.grid_at(path, bpm, 71.3, 40, anchor=g)
    bars = (here.downbeat - first) / (4 * 60 / bpm)
    assert here.bar_known and bars == pytest.approx(round(bars), abs=0.01)


def test_the_stretch_keeps_the_kicks_where_they_were(monkeypatch):
    """ffmpeg's atempo puts every onset ~20 ms early; rubberband does not. The
    fallback is compensated rather than trusted."""
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "_RUBBERBAND", True)
    assert beatgrid.stretch_filter(0.97).startswith("rubberband=") and beatgrid.stretch_latency(0.97) == 0
    assert beatgrid.stretch_filter(1.0) is None
    monkeypatch.setattr(beatgrid, "_RUBBERBAND", False)
    assert beatgrid.stretch_filter(0.97).startswith("atempo=")
    assert beatgrid.stretch_latency(0.97) == beatgrid.ATEMPO_EARLY_S and beatgrid.stretch_latency(1.0) == 0


def test_a_late_first_beat_is_seeked_to_not_waited_for():
    late = Grid(bpm=120.0, downbeat=12.7, contrast=8.0)            # a video intro before the beat
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(late), "skip", 16, lead=2.0)
    assert plan.kind == "blend" and plan.offset == pytest.approx(12.7 - R.PREROLL_S)
    assert plan.drop - plan.start == pytest.approx(R.PREROLL_S)
    assert plan.drop % 8.0 == pytest.approx(0.0, abs=1e-9)          # a skip lands on a four-bar phrase
    assert plan.drop <= 3.0 + R.PREROLL_S + 2.0 + 8.0               # the next one, not 13 s away


def test_a_deck_started_part_way_keeps_its_clock():
    d = Deck(rec("x", 120, "8A"), 1.25, 100.0, tone(0, 1.0), offset=10.0)
    assert d.at(0) == pytest.approx(8.0)                           # 10 s of record at 1.25x
    assert d.end == pytest.approx(80.0, abs=0.02)



def test_a_blend_comes_in_from_the_top_and_leaves_from_the_bottom():
    """The staging DJs use for a long EQ blend: incoming highs first, then
    mids (each record's thinned while both play), bass on the halfway bar;
    the outgoing loses bass at the swap, mids next, highs last."""
    plan = plan_transition(3.0, 1.0, STEADY, 120.0, nxt(), "skip", 64, lead=2.0)
    q = plan.length / 4
    at = lambda f: gains(plan, np.array([plan.drop + q * f]))
    ol, om, oh, il, im, ih = (float(x[0]) for x in at(1.0))           # end of Q1
    assert ih == pytest.approx(1) and im == pytest.approx(0) and il == 0 and om == pytest.approx(1)
    ol, om, oh, il, im, ih = (float(x[0]) for x in at(1.99))          # just before the swap
    assert im + om < 1.25 and il == 0 and ol == 1                      # thinned mids, one bassline
    ol, om, oh, il, im, ih = (float(x[0]) for x in at(2.6))           # after the swap
    assert ol == 0 and il == 1 and im == pytest.approx(1) and oh == pytest.approx(1) and om < 0.5
    ol, om, oh, il, im, ih = (float(x[0]) for x in at(3.5))
    assert om == pytest.approx(0, abs=1e-6) and 0.1 < oh < 0.9


def test_a_blend_plays_both_records_together_for_half_its_length():
    """16 beats with the highs crossing at once was "hamfisted": a blend now
    brings the incoming in over a quarter, holds both through the middle half
    (the bass swapping exactly halfway), and lets the outgoing go over the last."""
    plan = plan_transition(3.0, 1.0, STEADY, 120.0, nxt(), "skip", 64, lead=2.0)
    assert plan.kind == "blend" and plan.length == pytest.approx(32.0)
    q = plan.length / 4
    t = np.array([plan.drop + q * f for f in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0)])
    out_low, out_mid, out_high, in_low, in_mid, in_high = gains(plan, t)
    both = (in_high >= 0.999) & (out_high >= 0.999)
    assert both.tolist() == [False, False, True, True, True, True, True, False, False]
    assert in_low[t < plan.drop + 2 * q].max() == 0 and out_low[t > plan.drop + 2 * q + plan.beat].max() == 0
    assert 0.1 < in_high[1] < 0.9 and 0.1 < out_high[7] < 0.9          # eased in and out, not stepped


def test_an_end_blend_starts_on_an_eight_bar_phrase():
    plan = plan_transition(10.0, 1.0, STEADY, 200.0, nxt(), "end", 64, lead=2.0)
    assert plan.kind == "blend" and plan.done <= 200.0
    assert plan.drop % 16.0 == pytest.approx(0.0, abs=1e-9)          # eight bars of 2 s from bar one


def test_phrases_are_counted_from_the_records_bar_one():
    g = Grid(bpm=120.0, downbeat=10.0, contrast=8.0, bar0=5)        # bar 5 starts at 10 s
    assert g.next_bar(10.1, every=8) == pytest.approx(16.0)          # bar 8
    assert g.next_bar(10.1, every=4) == pytest.approx(16.0)
    assert g.next_bar(10.1) == pytest.approx(12.0)


def test_two_full_records_are_limited_not_clipped():
    loud = np.full((R.FRAME_SAMPLES, 2), 20000.0, dtype=np.float32)      # two loud records: 40,000 summed
    parts = (loud * 0, loud, loud * 0)
    y = np.frombuffer(R.mix_frames(parts, parts, (1.0, 1.0, 1.0, 1.0, 1.0, 1.0)), np.int16)
    assert y.max() < 32767 and y.max() > 0.8 * 32767


def test_the_mix_out_point_is_the_last_beat_not_the_end_of_the_file(tmp_path):
    """Mixxx-style: a blend is fitted before the outgoing's music ends. Clicks
    for 70 s then 40 s of silence: the last beat is at ~70 s, not 110."""
    import shutil, subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from utils.audio import beatgrid
    clicks = _clicks(tmp_path / "c.wav", 124, 0.5, 70)
    padded = tmp_path / "padded.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", clicks, "-af", "apad=pad_dur=40", str(padded)], check=True)
    last = beatgrid.last_strong_beat(str(padded), 124, 110.0)
    assert 68.5 < last < 70.1


def test_a_skip_calls_off_a_blend_planned_for_the_end_of_the_record():
    src, _ = _source()
    src._begin_planning("end")
    deadline = time.time() + 5
    while src.plan is None and time.time() < deadline:
        time.sleep(0.01)
    assert src.plan is not None and src.plan.mode == "end"
    src.skip()
    deadline = time.time() + 5
    while (src.plan is None or src.plan.mode != "skip") and time.time() < deadline:
        time.sleep(0.01)
    assert src.plan.mode == "skip" and src.plan.drop < 12.0
