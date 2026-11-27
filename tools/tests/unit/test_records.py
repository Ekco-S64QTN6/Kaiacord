"""!music records: choosing the next record, and mixing one into the next."""
import io
import json
import random
import threading
import time
import types

import numpy as np
import pytest

from utils.audio import library
from utils.audio import records as R
from utils.audio.beatgrid import Grid
from utils.audio.records import FRAME_BYTES, FRAME_SAMPLES, FRAMES_PER_S, RATE, CrossfadeSource, Deck, Next, plan_transition, gains


@pytest.fixture(autouse=True)
def _blends_measured_as_locked(monkeypatch):
    """These tests use fake records with no audio to measure; every planned
    blend is taken as measured and locked unless a test says otherwise."""
    from utils.audio import mixcheck, records as _R
    monkeypatch.setattr(_R, "_default_verify",
                        lambda *a: (mixcheck.Verdict(True, 16, 16, agree=16), 0.0))
    monkeypatch.setattr(_R, "_envelope", lambda path: None)


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


def wait_until(cond, seconds=5.0):
    deadline = time.time() + seconds
    while not cond() and time.time() < deadline:
        time.sleep(0.01)
    return cond()


def wait_for(deck, frames):
    deadline = time.time() + 2
    while time.time() < deadline and len(deck._frames) < frames and not deck._eof:
        time.sleep(0.01)


STEADY = Grid(bpm=120.0, downbeat=0.0, contrast=8.0)          # a bar every 2 s
LOOSE = Grid(bpm=120.0, downbeat=0.0, contrast=2.7)            # rock, breaks: Big Country measured 2.7


def nxt(grid=STEADY, seconds=300.0, name="two"):
    return Next(rec(name, 120, "8A"), seconds, 0.0, grid)

@pytest.fixture
def loop_source():
    frame_count = 1500
    frame_values = (np.arange(frame_count, dtype=np.int16) % 20000) + 1000
    samples = np.repeat(frame_values, FRAME_SAMPLES * 2)
    data = samples.tobytes()

    def factory(path, ratio, gain=0.0, offset=0.0, semitones=0):
        start = int(round(offset / ratio * FRAMES_PER_S))
        return io.BytesIO(data[start * FRAME_BYTES:])

    first = Deck(rec("loop-pattern", 120, "8A"), 1.0, 300.0, factory)
    first.grid = STEADY
    src = CrossfadeSource(first, lambda _deck: None, stream_factory=factory,
                          grid_at=lambda *_args: STEADY)
    src.rides = False
    wait_for(first, 150)
    yield src
    src.cleanup()


def test_loop_repeats_exact_predecoded_pcm_and_wraps_only_the_source_clock(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None
    assert src.set_loop(1, 2)
    loop = deck._loop
    assert loop is not None and loop.beats == 2 and len(loop.frames) == 50
    start_frame = loop.start_played
    assert deck.at(start_frame) == pytest.approx(4.0)
    assert deck.at(start_frame + 50) == pytest.approx(4.0)
    assert deck.remaining == int(round((deck.end - 5.0) * FRAMES_PER_S))

    while deck.played < start_frame:
        src.read()
    first_cycle = [src.read() for _ in range(50)]
    assert deck.played == start_frame + 50
    assert deck.at() == pytest.approx(4.0)
    second_cycle = [src.read() for _ in range(50)]
    assert first_cycle == second_cycle
    assert deck.played == start_frame + 100
    assert deck.at() == pytest.approx(4.0)
    assert src.plan is None


def test_pfl_monitor_follows_loop_pcm_and_exits_with_the_program_deck(loop_source):
    src = loop_source
    assert src.current is not None
    src.controls.set(None, "phones", 1.0)
    src.controls.set(None, "phones_mix", 0.0)
    assert src.set_headphones(1)
    stream = src.attach_headphone_stream()
    assert stream is not None
    head_old = src._headphones_deck
    try:
        assert src.set_loop(1, 2)
        loop = src.current._loop
        assert loop is not None
        while src.current.played < loop.start_played:
            src.read()
            stream.get_nowait()
        program_cycle = []
        monitor_cycle = []
        for _ in range(len(loop.frames)):
            program_cycle.append(src.read())
            monitor_cycle.append(stream.get_nowait())
        assert all(np.allclose(np.frombuffer(a, np.int16), np.frombuffer(b, np.int16), atol=1)
                       for a, b in zip(program_cycle, monitor_cycle))
        old_program = src.current
        assert src.set_loop(1, None)
        for _ in range(len(loop.frames) + 3):
            if src.current is not old_program:
                break
            src.read()
            stream.get_nowait()
        assert src.current is not old_program
        assert src._headphones_deck is not None and src._headphones_deck is not head_old
        assert src._headphones_deck.at(0) == pytest.approx(5.0)
        next_program = src.read()
        next_monitor = stream.get_nowait()
        assert np.allclose(np.frombuffer(next_program, np.int16),
                           np.frombuffer(next_monitor, np.int16), atol=1)
    finally:
        src.detach_headphone_stream(stream)
        src.set_headphones(None)

def test_selecting_headphones_mid_loop_joins_the_current_loop_cursor(loop_source):
    src = loop_source
    assert src.current is not None and src.set_loop(1, 2)
    loop = src.current._loop
    assert loop is not None
    while src.current.played < loop.start_played + 7:
        src.read()
    expected_position = src.current.at()
    expected_index = (src.current.played - loop.start_played) % len(loop.frames)
    src.controls.set(None, "phones", 1.0)
    src.controls.set(None, "phones_mix", 0.0)
    assert src.set_headphones(1)
    head = src._headphones_deck
    assert head is not None and head._loop is not None
    assert head._loop.start_index == expected_index
    assert head.at() == pytest.approx(expected_position)
    stream = src.attach_headphone_stream()
    assert stream is not None
    try:
        program = src.read()
        monitor = stream.get_nowait()
        assert np.allclose(np.frombuffer(program, np.int16),
                           np.frombuffer(monitor, np.int16), atol=1)
    finally:
        src.detach_headphone_stream(stream)
        src.set_headphones(None)

def test_exiting_an_armed_loop_clears_the_matching_pfl_loop_too(loop_source):
    src = loop_source
    src.controls.set(None, "phones", 1.0)
    src.controls.set(None, "phones_mix", 0.0)
    assert src.set_headphones(1)
    stream = src.attach_headphone_stream()
    assert stream is not None
    deck = src.current
    head = src._headphones_deck
    assert deck is not None and head is not None
    try:
        assert src.set_loop(1, 2)
        loop = deck._loop
        assert loop is not None and head._loop is not None
        assert deck.played < loop.start_played
        assert src.set_loop(1, None)
        assert deck._loop is None and head._loop is None
        assert src._pending_loop_exit is None
    finally:
        src.detach_headphone_stream(stream)
        src.set_headphones(None)


def test_headphone_selection_is_refused_during_a_pending_loop_exit(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None and src.set_loop(1, 2)
    loop = deck._loop
    assert loop is not None
    while deck.played < loop.start_played:
        src.read()
    assert src.set_loop(1, None)
    pending = src._pending_loop_exit
    assert pending is not None
    assert not src.set_headphones(1)
    assert src._pending_loop_exit is pending and src.current is deck

def test_loop_exit_warms_after_the_loop_and_switches_only_at_a_wrap(loop_source):
    src = loop_source
    old = src.current
    assert old is not None and src.set_loop(1, 2)
    loop = old._loop
    assert loop is not None
    while old.played < loop.start_played + 1:
        src.read()
    assert old.at() == pytest.approx(4.02)
    assert src.set_loop(1, None)
    pending = src._pending_loop_exit
    assert pending is not None and pending.old is old
    boundary = pending.boundary
    assert boundary == loop.start_played + len(loop.frames)
    while src.current is old:
        src.read()
    current = src.current
    assert current is not None and current is not old
    assert current._loop is None
    assert current.at(0) == pytest.approx(5.0)
    assert current.played == 1
    assert old._closed


def test_hot_cue_recall_cannot_interrupt_an_active_or_exiting_loop(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None and src.set_loop(1, 2)
    loop = deck._loop
    assert loop is not None
    while deck.played < loop.start_played:
        src.read()
    assert not src.jump_to_cue(1, 8.0, expected_path=deck.record.path)
    assert src.current is deck and deck._loop is loop
    assert src.set_loop(1, None)
    pending = src._pending_loop_exit
    assert pending is not None
    assert not src.jump_to_cue(1, 12.0, expected_path=deck.record.path)
    assert src.current is deck and src._pending_loop_exit is pending

def test_loop_is_rejected_without_a_counted_grid_or_during_a_transition(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None
    deck.grid = Grid(bpm=120.0, downbeat=0.0, contrast=8.0, bar_known=False)
    assert not src.set_loop(1, 2)
    deck.grid = STEADY
    src._planning = True
    assert not src.set_loop(1, 2)
    src._planning = False
    src._pending_planning_mode = "skip"
    assert not src.set_loop(1, 2)
    src._pending_planning_mode = None
    plan = types.SimpleNamespace(kind="out", mode="end")
    src.plan = plan
    assert not src.set_loop(1, 2)
    assert deck._loop is None and src.plan is plan


def test_loop_arming_rechecks_transition_planning_after_pcm_preparation(loop_source):
    src = loop_source
    original_factory = src._factory
    entered = threading.Event()
    release = threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(target=lambda: result.append(src.set_loop(1, 2)), daemon=True)
    worker.start()
    assert entered.wait(timeout=1.0)
    with src._lock:
        src._planning = True
    release.set()
    worker.join(timeout=5.0)
    with src._lock:
        src._planning = False
    assert not worker.is_alive()
    assert result == [False]
    assert src.current is not None and src.current._loop is None

def test_loop_arming_rechecks_pitch_ownership_after_pcm_preparation(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None and src.set_headphones(1)
    head = src._headphones_deck
    assert head is not None

    original_factory = src._factory
    entered = threading.Event()
    release = threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(
        target=lambda: result.append(src.set_loop(1, 2)), daemon=True
    )
    worker.start()
    try:
        assert entered.wait(timeout=1.0)
        # The initial transport check has passed; a pitch-fader update races
        # the off-lock PCM preparation before the loop is committed.
        assert src.set_pitch(1, 1.05)
    finally:
        release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert result == [False]
    assert deck.pitch_control_active and head.pitch_control_active
    assert not deck.loop_active and not head.loop_active


def test_loop_lengths_are_strictly_bounded(loop_source):
    src = loop_source
    assert not src.set_loop(1, True)
    assert not src.set_loop(1, 16)
    assert not src.set_loop(True, 2)
    assert src.current._loop is None

@pytest.fixture
def hotcue_source():
    def factory(path, ratio, gain=0.0, offset=0.0, semitones=0):
        return tone(1000, 20.0)(path, ratio, gain=gain, offset=offset)

    first = Deck(rec("hotcue-current", 120, "8A"), 1.05, 300.0, factory,
                 gain=1.5, semitones=1)
    first.grid = STEADY
    src = CrossfadeSource(first, lambda _deck: None, stream_factory=factory,
                          grid_at=lambda *_args: STEADY)
    src._fine = lambda _deck, _plan: None
    wait_for(first, 50)
    yield src
    src.cleanup()


def test_hot_cue_rebuilds_the_active_deck_at_exact_source_time(hotcue_source):
    src = hotcue_source
    old = src.current
    for _ in range(4):
        src.read()
    old_played = old.played
    assert src.jump_to_cue(1, 5.25, expected_path=old.record.path)
    replacement = src.current
    assert replacement is not old
    assert replacement.slot == 1
    assert replacement.ratio == pytest.approx(1.05)
    assert replacement.semitones == 1
    assert replacement.grid == STEADY
    assert replacement.at() * replacement.ratio == pytest.approx(5.25, abs=0.02)
    assert old.played == old_played
    assert len(replacement._frames) >= 5




def test_hot_cue_preserves_persistent_pitch_and_rebuilds_selected_pfl_decoder(hotcue_source):
    src = hotcue_source
    assert src.set_headphones(1)
    assert src.set_pitch(1, 1.05)
    for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
        src.read()
    old = src.current
    assert old is not None and old.pitch_rate == pytest.approx(1.05)
    assert src._headphones_deck is not None
    assert src._headphones_deck.pitch_rate == pytest.approx(1.05)

    assert src.jump_to_cue(1, 5.25, expected_path=old.record.path)
    replacement = src.current
    preview = src._headphones_deck
    assert replacement is not old
    assert replacement is not None and replacement.pitch_rate == pytest.approx(1.05)
    assert replacement.at() * replacement.ratio == pytest.approx(5.25, abs=0.02)
    assert preview is not None and preview.pitch_rate == pytest.approx(1.05)
    assert preview.at() == pytest.approx(replacement.at(), abs=1 / R.FRAMES_PER_S)


def test_hot_cue_refuses_an_active_transition_without_mutating_it(hotcue_source):
    src = hotcue_source
    original = src.current
    plan = types.SimpleNamespace(kind="out", mode="end")
    src.plan = plan
    assert src.blend_started()
    assert not src.jump_to_cue(1, 8.0)
    assert src.current is original and src.plan is plan


def test_hot_cue_identity_guard_rejects_a_replaced_deck(hotcue_source):
    src = hotcue_source
    original = src.current
    assert not src.jump_to_cue(1, 8.0, expected_path="/music/other-track.mp3")
    assert src.current is original


def test_hot_cue_can_set_the_loaded_free_decks_next_play_position(hotcue_source):
    src = hotcue_source
    queued = nxt(seconds=120.0, name="queued-hotcue")
    src._queued = queued
    assert src.jump_to_cue(2, 37.5, expected_path=queued.record.path)
    assert src.cue == pytest.approx(37.5)
    assert src.by_hand


def test_hot_cue_does_not_cancel_a_transition_for_the_incoming_deck(hotcue_source):
    src = hotcue_source
    original = src.current
    incoming = Deck(rec("incoming-hotcue", 120, "8A"), 1.0, 120.0, tone(-1000, 20.0))
    incoming.slot = 2
    src.incoming = incoming
    plan = types.SimpleNamespace(kind="blend", mode="skip")
    src.plan = plan
    assert not src.jump_to_cue(2, 12.0)
    assert src.current is original and src.incoming is incoming and src.plan is plan
    src.incoming = None
    incoming.close()


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


def test_a_loose_beat_is_a_clean_switch_never_an_overlap():
    """Two beats that can't be matched never play at once: the outgoing fades
    over its last beat into a bar line and the incoming's bar one lands on it."""
    late = Next(rec("two", 120, "8A"), 20.0, 0.0, LOOSE, lead=1.7)
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, late, "skip")
    assert plan.kind == "cut" and plan.fallback == "beat" and plan.start == plan.drop
    assert plan.drop % 2.0 == pytest.approx(0.0, abs=1e-9)                 # on the outgoing's bar
    assert plan.offset == pytest.approx(LOOSE.downbeat)                    # from its first beat
    t = np.arange(plan.drop - 2.0, plan.drop + 2.0, 0.001)
    ol, om, oh, il, im, ih = gains(plan, t)
    assert not np.any((oh > 0) & (ih > 0))                                 # never both at once
    assert plan_transition(3.0, 1.0, LOOSE, 60.0, nxt(STEADY), "skip").kind == "cut"
    assert plan_transition(3.0, 1.0, None, 60.0, nxt(STEADY), "skip").kind == "cut"

def test_tempos_too_far_apart_switch_on_the_bar_at_their_own_speed():
    fast = Grid(bpm=150.0, downbeat=0.0, contrast=8.0)
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(fast), "skip")
    assert plan.kind == "cut" and plan.fallback == "tempo" and plan.ratio == 1.0
    assert plan.drop % 2.0 == pytest.approx(0.0, abs=1e-9)

def test_a_switch_carries_the_tempo_where_it_can():
    near = Grid(bpm=123.0, downbeat=0.5, contrast=8.0, bar_known=False)   # steady, bar not counted
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(near), "skip")
    assert plan.kind == "cut" and plan.ratio == pytest.approx(120.0 / 123.0)

def test_a_steady_pair_with_no_room_left_is_a_switch():
    plan = plan_transition(9.0, 1.0, STEADY, 10.0, nxt(STEADY), "end")
    assert plan.kind == "cut" and plan.fallback == "room"

def test_a_blend_swaps_the_bass_halfway_and_keeps_one_bassline():
    plan = plan_transition(3.0, 1.0, STEADY, 60.0, nxt(), "skip")
    t = np.arange(plan.drop - 1, plan.done + 1, 0.001)
    out_low, out_mid, out_high, in_low, in_mid, in_high = gains(plan, t)
    assert np.allclose(out_low ** 2 + in_low ** 2, 1.0)             # never none: the low end holds its power
    swap = plan.drop + plan.length / 2
    w = min(R.BASS_SWAP_BEATS * plan.beat, plan.length / 4)
    assert np.all(in_low[t < swap] == 0) and np.all(out_low[t < swap] == 1)
    assert np.allclose(in_low[t > swap + w], 1) and np.allclose(out_low[t > swap + w], 0, atol=1e-12)
    # Handed over across the window, not switched: halfway through it both basslines
    # sound at -3 dB, and the window is longer than the one beat that was a switch.
    mid = np.argmin(np.abs(t - (swap + w / 2)))
    assert w >= 4 * plan.beat
    assert in_low[mid] == pytest.approx(np.sqrt(0.5), abs=0.01) and out_low[mid] == pytest.approx(np.sqrt(0.5), abs=0.01)
    assert out_high[t <= plan.drop].min() == 1 and in_high[t >= plan.done].min() == pytest.approx(1)


def test_one_voice_at_a_time_the_presence_band_changes_hands_with_the_mids():
    """A voice is not only mids: its consonants sit above them. Brought in
    "highs first" as one band, the new record's singer came in over the one on
    air, and the old one's stayed up after its mids had gone."""
    plan = plan_transition(3.0, 1.0, STEADY, 120.0, nxt(), "skip", 64, lead=2.0)
    swap, b = plan.drop + plan.length / 2, plan.beat

    def at(x):
        t = np.array([x])
        g = gains(plan, t)
        return [float(v[0]) for v in g], [float(v[0]) for v in R.presence(plan, t, g)]
    g, (out_p, in_p) = at(swap - 8 * b)                    # the ride: the new record's air is up…
    assert g[5] == pytest.approx(1) and out_p == pytest.approx(1)
    assert in_p == pytest.approx(R.PRESENCE_HOLD)          # …its voice is not
    g, (out_p, in_p) = at(swap + 4 * b)                    # after the handoff
    assert g[2] == pytest.approx(1)                        # the old record's hats still ride
    assert out_p == pytest.approx(0) and in_p == pytest.approx(1)
    # any other transition has no handoff: the presence is simply the highs
    cut = plan_transition(3.0, 1.0, LOOSE, 60.0, nxt(), "skip")
    g = gains(cut, np.array([cut.drop - 0.1]))
    assert R.presence(cut, np.array([cut.drop - 0.1]), g) == (g[2], g[5])


def test_the_four_bands_sum_back_to_the_frame_and_the_high_knob_turns_both_halves():
    deck = Deck(rec("one", 120, "8A"), 1.0, 5.0, tone(1000, 5.0))
    try:
        rng = np.random.default_rng(1)
        frame = (rng.standard_normal((R.FRAME_SAMPLES, 2)) * 3000).astype(np.int16).tobytes()
        parts = deck.split(frame)
        assert len(parts) == 4
        x = np.frombuffer(frame, dtype=np.int16).astype(np.float32).reshape(-1, 2)
        assert np.allclose(sum(parts), x, atol=1e-2)
        whole = np.frombuffer(R.mix_frames(parts, None, R.SOLO), dtype=np.int16).reshape(-1, 2)
        assert np.abs(whole - x).max() <= 1
        # HIGH killed at the booth: presence and air both go
        no_high = np.frombuffer(R.mix_frames(parts, None, R.SOLO, (1.0, 1.0, 0.0, 1.0)), dtype=np.int16).reshape(-1, 2)
        assert np.abs(no_high - (parts[0] + parts[1])).max() <= 1
        # the automix's presence gain reaches only the presence band
        no_pres = np.frombuffer(R.mix_frames(parts, None, R.SOLO, pres=(0.0, 0.0)), dtype=np.int16).reshape(-1, 2)
        assert np.abs(no_pres - (x - parts[2])).max() <= 1
    finally:
        deck.close()


def test_after_the_swap_the_old_record_leaves_and_a_long_blend_is_a_long_ride_in():
    """A 256-beat blend kept the old record for 128 beats after its bass and
    its singer had gone — a record played too long. It is gone within
    TAIL_BEATS (a quarter of a long blend), and the deck is free then."""
    g125 = Grid(bpm=120.0, downbeat=0.0, contrast=8.0)
    for beats, tail_beats in ((32, 16), (64, 32), (128, 32), (256, 64)):
        plan = plan_transition(3.0, 1.0, g125, 900.0, nxt(g125, seconds=900.0), "skip", beats, lead=2.0)
        b, swap = plan.beat, plan.drop + plan.length / 2
        assert plan.kind == "blend" and R.tail(plan) == pytest.approx(tail_beats * b)
        assert plan.done == pytest.approx(swap + tail_beats * b)
        out_high = lambda x: float(gains(plan, np.array([x]))[2][0])
        assert out_high(swap) == pytest.approx(1) and out_high(plan.done) == pytest.approx(0, abs=1e-6)
        assert float(gains(plan, np.array([plan.done]))[5][0]) == pytest.approx(1)
    # and it needs only that much of the outgoing: 128 beats fit in 50 s (64 s of blend)
    fits = plan_transition(0.0, 1.0, g125, 50.0, nxt(g125, seconds=900.0), "end", 128, lead=0.5)
    assert fits.kind == "blend" and fits.done <= 50.0


def test_the_swap_is_put_where_it_is_asked_for_or_the_plan_says_there_is_no_room():
    plan = plan_transition(10.0, 1.0, STEADY, 300.0, nxt(), "end", 64, lead=2.0, swap_at=201.0)
    assert plan.kind == "blend"
    assert plan.drop + plan.length / 2 == pytest.approx(200.0)       # the four-bar phrase nearest
    late = plan_transition(190.0, 1.0, STEADY, 300.0, nxt(), "end", 64, lead=2.0, swap_at=201.0)
    assert late.kind == "cut" and late.fallback == "room"            # the drop for it has passed
    past = plan_transition(10.0, 1.0, STEADY, 300.0, nxt(), "end", 64, lead=2.0, swap_at=296.0)
    assert past.kind == "cut" and past.fallback == "room"            # no room after it for the way out


def test_a_record_is_left_near_its_end_before_anywhere_further_back():
    """The search took the first lock walking back from the end at the longest
    length: a 64-beat blend two minutes early over a 32-beat one on the last
    phrase. Records were left mid-verse (one after 55 s) with the next one's
    vocal over theirs."""
    from utils.audio import mixcheck, setlist
    tried = []

    def verify(out_path, out_ratio, in_path, plan):
        beats = round(plan.length / plan.beat)
        tried.append((beats, round(plan.done)))
        ok = (beats == 64 and plan.done < 150) or (beats == 32 and plan.done > 280)
        return mixcheck.Verdict(ok, 16, 16, agree=16 if ok else 2), 0.0
    plan, _, _, how = setlist.find_blend(60.0, "/o.mp3", 1.0, STEADY, 300.0, nxt(), "end", 64, verify_fn=verify)
    assert how["beats"] == 32 and plan.done > 280
    # nothing near the end at all: further back is still better than no blend
    far = lambda o, r, i, plan: (mixcheck.Verdict(plan.done < 300.0 - setlist.NEAR_END_S, 16, 16, agree=16), 0.0)
    plan, _, _, how = setlist.find_blend(60.0, "/o.mp3", 1.0, STEADY, 300.0, nxt(), "end", 64, verify_fn=far)
    assert plan.done < 300.0 - setlist.NEAR_END_S


def test_the_swap_goes_where_the_record_changes_when_a_blend_locks_there():
    from utils.audio import mixcheck, setlist
    yes = lambda *a: (mixcheck.Verdict(True, 16, 16, agree=16), 0.0)
    plan, _, _, how = setlist.find_blend(60.0, "/o.mp3", 1.0, STEADY, 300.0, nxt(), "end", 64, verify_fn=yes,
                                         swaps=[(240.0, "outro")])
    assert plan.where == "outro" and how["where"] == "outro"
    assert plan.drop + plan.length / 2 == pytest.approx(240.0) and plan.done == pytest.approx(256.0)
    # it does not lock there: the end of the record, as before, and it says so
    not_there = lambda o, r, i, p: (mixcheck.Verdict(p.where != "outro", 16, 16, agree=16), 0.0)
    plan, _, _, how = setlist.find_blend(60.0, "/o.mp3", 1.0, STEADY, 300.0, nxt(), "end", 64, verify_fn=not_there,
                                         swaps=[(240.0, "outro")])
    assert plan.where == "" and "where" not in how and plan.done > 280


def test_keys_that_fight_get_the_short_blend_first():
    assert R.blend_lengths(64, "8A", "9A") == [64, 32, 16]
    assert R.blend_lengths(256, "8A", "8B") == [256, 128, 64, 32, 16]
    assert R.blend_lengths(64, "8A", "3A") == [32, 64, 16]            # far apart on the wheel
    assert R.blend_lengths(256, "8A", "10A") == [32, 256, 128, 64, 16]
    assert R.blend_lengths(64, "8A", None) == [64, 32, 16]            # a key not known is not a clash


def test_she_plans_early_enough_to_leave_at_the_outro_and_tries_the_breakdown_when_eager(monkeypatch):
    from utils.audio import songmap
    monkeypatch.setattr(songmap, "out_points", lambda path, end, bpm, length: [("outro", 15.0), ("break", 9.0)])
    monkeypatch.setattr(R, "_music_end", lambda deck: 19.0)
    src, _ = _source()
    try:
        deck = src.current
        assert wait_until(lambda: deck.outs is not None)
        assert deck.out_lead == pytest.approx(10.0)                    # the earliest way out, before its music ends
        assert src._plan_ahead(deck) == pytest.approx(16 * 0.6 + 90 + 10.0)
        src.energy = 0.2
        monkeypatch.setattr("zlib.crc32", lambda b: 1)
        assert src._swaps(deck) == [(15.0, "outro")]
        src.energy = 0.9                                               # the energy to skip the lull
        assert src._swaps(deck) == [(9.0, "break"), (15.0, "outro")]
        src.energy = 0.2
        monkeypatch.setattr("zlib.crc32", lambda b: 3)                 # one record in three, whatever her mood
        assert [w for _, w in src._swaps(deck)] == ["break", "outro"]
    finally:
        src.cleanup()


def _source(first_value=1000, second_value=-1000, grid=STEADY, out_grid=STEADY, verify=None):
    first = Deck(rec("one", 120, "8A"), 1.0, 20.0, tone(first_value, 20.0))
    changed = []
    queue = [nxt(grid)]
    src = CrossfadeSource(first, lambda deck: queue.pop() if queue else None,
                          stream_factory=tone(second_value, 20.0), on_change=changed.append,
                          grid_at=lambda record, start, seconds: out_grid, mix_beats=16, verify=verify)
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


def test_a_blend_is_measured_before_it_plays():
    """Ticks put the bars within tens of ms; the records decide. A blend whose
    bars all agree it is 54 ms late is started 54 ms earlier, whatever the size;
    one with no common beat anywhere is an echo-out, never laid over."""
    from utils.audio import mixcheck
    locked = mixcheck.Verdict(True, 16, 16, agree=14)
    unlocked = mixcheck.Verdict(False, 16, 5, why="no common beat — only 5 of 16 bars line up clearly")
    seen = []

    def measured(verdict, shift):
        def v(out_path, out_ratio, in_path, plan):
            seen.append((out_path, in_path, plan.kind))
            return verdict, shift
        return v
    a, _ = _source(verify=measured(locked, -0.054))
    b, _ = _source(verify=measured(locked, 0.0))
    c, _ = _source(verify=measured(unlocked, 0.0))
    pa, pb, pc = _plan(a), _plan(b), _plan(c)
    assert pa.kind == pb.kind == "blend" and pa.start == pytest.approx(pb.start - 0.054)
    assert "moved -54 ms" in pa.check
    assert pc.kind == "echo" and pc.fallback == "unlocked" and "no common beat" in pc.why
    assert seen[0][0].endswith("one.mp3") and seen[0][1].endswith("two.mp3")


def test_the_set_ends_when_nothing_comes_next():
    first = Deck(rec("one", 124, "8A"), 1.0, 0.4, tone(500, 0.4))
    src = CrossfadeSource(first, lambda deck: None, grid_at=lambda *a: None)
    wait_for(first, 20)
    # This is an EOF-only test: wait for the explicit no-next result rather
    # than letting a speculative end planner race the synthetic frame loop.
    deadline = time.monotonic() + 1.0
    while src._picking and time.monotonic() < deadline:
        time.sleep(0.001)
    assert not src._picking and src._exhausted
    src._begin_planning = lambda _mode: None
    try:
        frames = [src.read() for _ in range(60)]
        assert b"" in frames
    finally:
        src.cleanup()


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
    session._listener_intent_lock = threading.Lock()
    session._listener_intent = None
    session._listener_pick_generation = 0
    session._listener_intent_min_pick_generation = 1
    monkeypatch.setattr(R, "probe_seconds", lambda path: 200.0)
    monkeypatch.setattr(R, "gain_db", lambda path: 0.0)
    monkeypatch.setattr(beatgrid, "grid_for", lambda path, bpm: STEADY if "steady" in path else LOOSE)
    order = iter([crate[1], crate[2]])
    monkeypatch.setattr(library, "next_record", lambda *a, **k: next(order, None))
    deck = Deck(crate[0], 1.0, 1.0, tone(0, 1.0))
    assert session._choose(deck).record.title == "steady"
    order = iter([crate[1], None])
    assert session._choose(deck).record.title == "steady"         # found by the pass over the whole crate
    session.crate = crate[:2]
    order = iter([crate[1], None])
    assert session._choose(deck).record.title == "loose"          # nothing steady anywhere: still a record
    assert "loose" not in " ".join(session.played)                 # passed over, not marked played


def test_a_bar_that_could_not_be_counted_is_a_switch():
    unsure = Grid(bpm=120.0, downbeat=0.0, contrast=8.0, bar_known=False)
    assert plan_transition(3.0, 1.0, unsure, 60.0, nxt(STEADY), "skip").kind == "cut"
    assert plan_transition(3.0, 1.0, STEADY, 60.0, nxt(unsure), "skip").kind == "cut"

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



def test_pfl_channel_gain_keeps_eq_and_trim_but_bypasses_fader_and_crossfader():
    controls = R.Controls()
    assert controls.set(1, "trim", 6.0)
    assert controls.set(1, "low", 0.5)
    assert controls.set(1, "fader", 0.0)
    assert controls.set(None, "xfader", 1.0)
    low, mid, high, gain = controls.channel_pre_fader(1)
    assert low == pytest.approx(0.5) and mid == high == pytest.approx(1.0)
    assert gain == pytest.approx(10 ** (6.0 / 20))
    assert controls.channel(1)[3] == 0.0  # the program channel is still silent


def test_headphone_bus_blends_cue_and_post_master_at_equal_power():
    cue = np.full((R.FRAME_SAMPLES, 2), 2000, dtype=np.int16).tobytes()
    master = np.full((R.FRAME_SAMPLES, 2), 4000, dtype=np.int16).tobytes()

    def peak(frame):
        return int(np.abs(np.frombuffer(frame, dtype=np.int16)).max())

    assert peak(R.headphone_frame(cue, master, 0.0, 1.0)) == 2000
    assert peak(R.headphone_frame(cue, master, 1.0, 1.0)) == 4000
    midpoint = peak(R.headphone_frame(cue, master, 0.5, 1.0))
    assert midpoint == pytest.approx(round((2000 + 4000) / np.sqrt(2)), abs=1)
    assert peak(R.headphone_frame(cue, master, 0.5, 0.5)) == pytest.approx(round(midpoint / 2), abs=1)
    assert peak(R.headphone_frame(None, master, 0.0, 1.0)) == 4000


@pytest.fixture
def headphone_source():
    first = Deck(rec("monitor", 120, "8A"), 1.0, 300.0, tone(1000, 20.0))
    first.grid = STEADY
    src = CrossfadeSource(first, lambda _deck: None, stream_factory=tone(-1000, 20.0),
                          grid_at=lambda *_args: STEADY)
    src._fine = lambda _deck, _plan: None
    wait_for(first, 50)
    yield src
    src.cleanup()


def test_pfl_uses_a_separate_decoder_without_advancing_the_program_deck(headphone_source):
    src = headphone_source
    assert src.set_headphones(1)
    stream = src.attach_headphone_stream()
    assert stream is not None
    try:
        src.controls.set(1, "fader", 0.0)
        src.controls.set(None, "xfader", 1.0)
        before = src.current.played
        program = src.read()
        preview = src._headphones_deck
        monitor = stream.get_nowait()
        assert src.current.played == before + 1
        assert preview is not None and preview.played == 1
        assert np.count_nonzero(np.frombuffer(program, dtype=np.int16)) == 0
        assert np.max(np.abs(np.frombuffer(monitor, dtype=np.int16))) > 0
    finally:
        src.detach_headphone_stream(stream)
        assert src.set_headphones(None)


def test_headphone_stream_queues_are_bounded_and_drop_oldest(headphone_source):
    src = headphone_source
    stream = src.attach_headphone_stream()
    second = src.attach_headphone_stream()
    assert stream is not None and second is not None
    assert src.attach_headphone_stream() is None
    try:
        for _ in range(60):
            src.read()
        assert stream.qsize() == 50 and second.qsize() == 50
        assert stream.get_nowait() == list(src._headphone_history)[-50]
    finally:
        src.detach_headphone_stream(stream)
        src.detach_headphone_stream(second)


def test_a_blend_comes_in_from_the_top_and_hands_the_vocals_over_at_the_swap():
    """The DJ's EQ blend: the incoming's highs first with its mids held low,
    the outgoing playing on whole — vocal and all — until the bar halfway,
    where the basslines swap and the mids change hands around the downbeat;
    the outgoing's highs last. Both records' mids at 55% through the middle
    put two vocals on top of each other, and the outgoing's was cut mid-phrase."""
    plan = plan_transition(3.0, 1.0, STEADY, 120.0, nxt(), "skip", 64, lead=2.0)
    q, b = plan.length / 4, plan.beat
    swap = plan.drop + plan.length / 2
    at = lambda x: [float(v[0]) for v in gains(plan, np.array([x]))]
    ol, om, oh, il, im, ih = at(plan.drop + q)                        # end of Q1
    assert ih == pytest.approx(1) and im == pytest.approx(R.MID_HOLD) and il == 0 and om == 1
    h = R.MID_HANDOFF_BEATS * b
    ol, om, oh, il, im, ih = at(swap - h / 2)                          # where the handoff begins
    assert om == pytest.approx(1) and im == pytest.approx(R.MID_HOLD) and ol == 1 and il == 0
    ol, om, oh, il, im, ih = at(swap)                                  # on the one: halfway through the handoff
    assert om == pytest.approx(0.5, abs=0.01) and im > om
    ol, om, oh, il, im, ih = at(swap + h / 2 * 1.01)                   # vocals handed over
    assert om == pytest.approx(0) and im == pytest.approx(1) and oh == 1
    w = min(R.BASS_SWAP_BEATS * b, plan.length / 4)
    ol, om, oh, il, im, ih = at(swap + w * 1.01)                       # bass handed over
    assert ol == pytest.approx(0, abs=1e-9) and il == pytest.approx(1)
    ol, om, oh, il, im, ih = at(plan.drop + 3.5 * q)
    assert 0.1 < oh < 0.9                                              # the outgoing's highs on their way out
    t = np.arange(plan.drop, plan.done, 0.001)
    _, om_, _, _, im_, _ = gains(plan, t)
    assert not np.any((om_ > 0.6) & (im_ > 0.6))                       # never two vocals near full


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
    w = min(R.BASS_SWAP_BEATS * plan.beat, plan.length / 4)
    assert in_low[t < plan.drop + 2 * q].max() == 0 and out_low[t > plan.drop + 2 * q + w].max() < 1e-9
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


def test_an_epic_blend_rides_both_records_up_together_for_a_minute():
    """EPIC is the DJ's long blend: a short way in, a minute and more with
    both records up and locked (bass swapped halfway through it), a short way out."""
    g125 = Grid(bpm=125.0, downbeat=0.0, contrast=8.0)
    plan = plan_transition(3.0, 1.0, g125, 600.0, nxt(g125, seconds=600.0), "skip", 256, lead=2.0)
    assert plan.kind == "blend" and plan.length == pytest.approx(256 * 0.48)
    t = np.arange(plan.drop, plan.done, 0.01)
    ol, om, oh, il, im, ih = gains(plan, t)
    both = (oh > 0.99) & (ih > 0.99) & (np.maximum(om, im) > 0.99)        # both up, one vocal at full
    assert both.sum() * 0.01 >= 60.0
    assert np.allclose(ol ** 2 + il ** 2, 1.0)            # the low end's power held throughout


def test_a_cue_moved_on_her_own_pick_is_where_it_comes_in():
    src, _ = _source()
    assert wait_until(lambda: src._queued is not None)
    assert not src.by_hand and src.set_cue(6.1) and src.cue == pytest.approx(6.0)
    src.skip()
    assert wait_until(lambda: src.plan is not None)
    assert src.plan.offset == pytest.approx(6.0 - R.PREROLL_S)          # from the cue, not the top


def test_kaia_trades_the_hats_in_a_long_ride_and_never_kills_the_bass():
    g125 = Grid(bpm=125.0, downbeat=0.0, contrast=8.0)
    plan = plan_transition(3.0, 1.0, g125, 600.0, nxt(g125, seconds=600.0), "skip", 256, lead=2.0)
    r, b, swap = R.ramp(plan), plan.beat, plan.drop + plan.length / 2
    at = lambda x: [float(f[0]) for f in R.kaia_hands(plan, np.array([x]), energy=0.8)[0]]
    first, second = at(plan.drop + 2 * r + 4 * b), at(plan.drop + 2 * r + 36 * b)   # two trade phrases
    assert first[2] > first[5] and second[5] > second[2]                    # the lead changes hands
    assert first[1] == pytest.approx(R.STAGE) and first[4] == pytest.approx(R.STAGE)   # vocals untouched
    assert first[0] < 1 and first[0] == pytest.approx(R.STAGE)              # both a touch down
    into = at(swap - b / 2)
    assert into[0] > 0.5 and into[3] > 0                                    # no bass kill into the swap
    assert 0.7 < into[2] / R.STAGE < 1.0                                    # the old air eased back, a little
    assert at(swap - 8 * b)[3] == pytest.approx(R.STAGE)                    # staged for as long as both are up
    assert at(swap + 4 * b)[3] == pytest.approx(1.0)                        # the new record whole once it has the room


def test_alone_she_gestures_rarely_and_lets_go_over_a_bar():
    """A move into every phrase, snapped back on the one, was a beginner riding
    the EQ: now at most every second phrase, small, eased off over a bar."""
    g = Grid(bpm=120.0, downbeat=0.0, contrast=8.0)          # bar 2 s, phrase 32 s
    seen = set()
    for seed in range(12):
        f_in, label = R.kaia_hands(None, np.array([63.9]), 0.9, g, 1.0, seed)    # last of phrase 2
        f_on, _ = R.kaia_hands(None, np.array([64.05]), 0.9, g, 1.0, seed)       # the one
        f_bar, _ = R.kaia_hands(None, np.array([66.1]), 0.9, g, 1.0, seed)       # a bar later
        moved = [abs(float(x[0]) - 1) for x in f_in[:3]]
        assert sum(m > 0.01 for m in moved) == 1 and label and max(moved) <= 0.2
        seen.add(max(range(3), key=lambda i: moved[i]))
        k = max(range(3), key=lambda i: moved[i])
        assert abs(float(f_on[k][0]) - 1) > 0.5 * moved[k]                  # not snapped back on the one
        assert abs(float(f_bar[k][0]) - 1) < 0.02                           # back by the end of the bar
        lone, _ = R.kaia_hands(None, np.array([31.9]), 0.9, g, 1.0, seed)  # the phrase before: no move
        assert all(abs(float(x[0]) - 1) < 1e-9 for x in lone[:3])
    assert seen == {0, 1, 2}                                 # all three gestures turn up
    quiet = R.kaia_hands(None, np.array([31.9]), 0.1, g, 1.0, 3)[0]
    assert all(abs(float(x[0]) - 1) < 1e-9 for x in quiet)   # no energy, no hands
    mid_phrase = R.kaia_hands(None, np.array([10.0]), 0.9, g, 1.0, 3)
    assert all(abs(float(x[0]) - 1) < 1e-9 for x in mid_phrase[0]) and mid_phrase[1] == ""


def test_a_blend_leaves_the_incoming_room_to_play_on_its_own():
    g125 = Grid(bpm=125.0, downbeat=0.0, contrast=8.0)
    fits = plan_transition(3.0, 1.0, g125, 600.0, nxt(g125, seconds=160.0), "skip", 256, lead=2.0)
    assert fits.kind == "blend"                          # 123 s of blend, 37 s left over
    short = plan_transition(3.0, 1.0, g125, 600.0, nxt(g125, seconds=140.0), "skip", 256, lead=2.0)
    assert short.kind != "blend" and short.fallback == "room"   # the planner halves it


def test_the_bass_swap_lands_where_the_new_bassline_comes_in():
    """Bassline in at bar 16 of the incoming, a 64-beat blend swaps at its
    bar 8: the incoming starts 8 bars into its intro, so bar 16 is the swap."""
    late = Next(rec("two", 120, "8A"), 300.0, 0.0, STEADY, bass_in=16)
    plan = plan_transition(3.0, 1.0, STEADY, 600.0, late, "skip", 64, lead=2.0)
    assert plan.kind == "blend"
    bar16 = STEADY.downbeat + 16 * 4 * STEADY.beat                     # incoming's own seconds
    swap = plan.drop + plan.length / 2                                  # outgoing seconds
    at_swap = plan.offset + (swap - plan.start) * plan.ratio            # incoming position there
    assert at_swap == pytest.approx(bar16, abs=1e-6)
    early = Next(rec("two", 120, "8A"), 300.0, 0.0, STEADY, bass_in=4)
    assert plan_transition(3.0, 1.0, STEADY, 600.0, early, "skip", 64, lead=2.0).offset == 0.0


def test_the_bassline_is_found_on_a_phrase(tmp_path):
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from scipy.io import wavfile
    from utils.audio import beatgrid
    # 120 bpm kicks from 0.5 s; a 55 Hz bassline joins at bar 16 (32.5 s).
    rate, seconds = 44100, 70
    x = np.zeros(seconds * rate, np.float32)
    k = np.arange(int(0.03 * rate))
    kick = np.sin(2 * np.pi * 55 * k / rate) * np.exp(-k / (0.008 * rate))
    for n, t in enumerate(np.arange(0.5, seconds - 0.1, 0.5)):
        i = int(round(t * rate))
        x[i:i + len(kick)] += (0.9 if n % 4 == 0 else 0.6) * kick
    j = int(32.5 * rate)
    x[j:] += 0.4 * np.sin(2 * np.pi * 55 * np.arange(len(x) - j) / rate)
    path = tmp_path / "bass.wav"
    wavfile.write(path, rate, (x / np.abs(x).max() * 0.9 * 32767).astype(np.int16))
    assert beatgrid.bass_entry(str(path), 120) == 16


def test_a_new_blend_length_replans_a_blend_not_yet_started():
    src, _ = _source()
    src.skip()
    assert wait_until(lambda: src.plan is not None)
    old = src.plan
    assert src.set_mix_beats(32)
    assert src.plan is not old
    assert wait_until(lambda: src.plan is not None) and round(src.plan.length / src.plan.beat) == 32


def test_key_sync_moves_a_clash_a_semitone_into_key():
    assert library.shift_key("8A", 1) == "3A" and library.shift_key("8A", -1) == "1A"
    assert library.key_sync("8A", "8A") == 0 and library.key_sync("8A", "9A") == 0 and library.key_sync("8A", "8B") == 0
    assert library.key_sync("8A", "3A") == -1                # a semitone up from 8A: brought back down
    assert library.key_sync("8A", "1A") == 1
    assert library.key_sync("8A", "5A") == 0                 # no single semitone fixes it
    assert library.key_sync(None, "5A") == 0


def test_a_shifted_key_reaches_rubberband_as_a_pitch(monkeypatch):
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "has_rubberband", lambda: True)
    f = beatgrid.stretch_filter(1.0, 1)
    assert f.startswith("rubberband=tempo=1.00000:pitch=1.059463")
    assert beatgrid.stretch_filter(1.0, 0) is None
    monkeypatch.setattr(beatgrid, "has_rubberband", lambda: False)
    assert beatgrid.stretch_filter(1.0, 1) is None            # atempo cannot move a key


def test_a_clashing_incoming_is_key_synced_in_the_blend(monkeypatch):
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "has_rubberband", lambda: True)
    first = Deck(rec("one", 120, "8A"), 1.0, 20.0, tone(1000, 20.0))
    seen = {}

    def factory(path, ratio, gain=0.0, offset=0.0, semitones=0):
        seen[path] = semitones
        return tone(-1000, 20.0)(path, ratio)
    src = CrossfadeSource(first, lambda d: Next(rec("two", 120, "3A"), 300.0, 0.0, STEADY),
                          stream_factory=factory, grid_at=lambda *a: STEADY, mix_beats=16)
    wait_for(first, 100)
    src.skip()
    assert wait_until(lambda: src.plan is not None)
    assert src.incoming.semitones == -1 and src.incoming.key == "8A" and seen["/music/two.mp3"] == -1


def _glider(ratio=0.95):
    from utils.audio import beatgrid
    first = Deck(rec("one", 120, "8A"), ratio, 600.0, tone(1000, 200.0))
    first.grid = STEADY
    src = CrossfadeSource(first, lambda d: None, stream_factory=tone(1000, 200.0),
                          grid_at=lambda *a: STEADY, mix_beats=16)
    src._glide_next = 0
    wait_for(first, 100)
    return src


def test_the_tempo_glides_back_toward_the_records_own_on_a_bar(monkeypatch):
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "has_rubberband", lambda: True)
    src = _glider(0.95)
    old = src.current
    deadline = time.time() + 5
    while src._splice is None and time.time() < deadline:
        src.read()
        time.sleep(0.002)
    assert src._splice is not None
    new, k_pre, k_cut = src._splice
    own_old = old.at(k_cut) * old.ratio                         # the record's own seconds at the join
    while src.current is old:
        src.read()
    assert src.current is new and new.ratio == pytest.approx(0.955)
    own_new = new.at(k_cut - k_pre) * new.ratio
    assert own_new == pytest.approx(own_old, abs=1.5 / RATE)    # no jump in the record
    when = (k_cut * R.FRAME_SAMPLES + 0) / RATE                 # the join's frame starts on/just before a bar
    bar = 4 * STEADY.beat / old.ratio
    assert (own_old / old.ratio) % bar == pytest.approx(0.0, abs=0.02) or (own_old / old.ratio) % bar > bar - 0.02


def test_the_glide_waits_for_a_blend_and_stops_at_its_own_tempo(monkeypatch):
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "has_rubberband", lambda: True)
    src = _glider(0.998)
    src._planning = True                                        # a blend being planned: no glide
    for _ in range(200):
        src.read()
    assert src._splice is None and src.current.ratio == 0.998
    src._planning = False
    deadline = time.time() + 5
    while src.current.ratio != 1.0 and time.time() < deadline:
        src.read()
        time.sleep(0.002)
    assert src.current.ratio == 1.0                             # within a step: straight to its own
    src._glide_next = 0
    for _ in range(100):
        src.read()
    assert src._splice is None                                  # nothing left to glide


# ── Beats counted on the tracker's ticks ─────────────────────────────

def _drifting_ticks(bpm, downbeat, n=600, drift=0.0):
    """Ticks of a record whose tempo is `bpm` with a slow wander of `drift`
    seconds over its length, as a real one has against one straight line."""
    beat = 60.0 / bpm
    i = np.arange(n)
    return downbeat + i * beat + drift * np.sin(i / n * np.pi)


def test_a_blend_lands_on_both_records_real_beats_not_the_extrapolated_line():
    out_t = _drifting_ticks(122.0, 0.30, drift=0.18)
    in_t = _drifting_ticks(124.0, 0.55, drift=-0.15)
    out_g = Grid(122.0, 0.30, 8.0, ticks=out_t)
    in_g = Grid(124.0, 0.55, 8.0, ticks=in_t)
    plan = plan_transition(100.0, 1.0, out_g, 290.0, Next(rec("two", 124, "8A"), 300.0, 0.0, in_g, bass_in=16),
                           "skip", 64)
    assert plan.kind == "blend"
    assert np.min(np.abs(out_t - plan.drop)) < 0.002                     # on an outgoing tick
    in_at_drop = plan.offset + (plan.drop - plan.start) * plan.ratio
    assert np.min(np.abs(in_t - in_at_drop)) < 0.002                     # on an incoming tick
    k = int(np.argmin(np.abs(in_t - in_at_drop)))
    assert k == 4 * (16 - 64 // 8)                                       # counted: the bar its bassline needs


def test_the_stretch_comes_from_a_line_through_all_the_ticks_not_a_median_of_quantised_steps():
    hop = 512 / 44100                                                    # the tracker's resolution
    t = np.round(_drifting_ticks(123.4, 0.2) / hop) * hop
    g = Grid(123.0, 0.2, 8.0, ticks=t)
    assert 60.0 / g.local_beat() == pytest.approx(123.4, abs=0.02)
    assert 60.0 / float(np.median(np.diff(t))) != pytest.approx(123.4, abs=0.3)   # what the median gave


def test_a_switch_lands_the_incoming_first_beat_on_the_outgoing_beat_where_tracked():
    out_t = _drifting_ticks(120.0, 0.0)
    in_t = _drifting_ticks(121.0, 1.37)
    out_g = Grid(120.0, 0.0, 8.0, bar_known=False, ticks=out_t)          # bar not found: a switch
    in_g = Grid(121.0, 1.37, 8.0, ticks=in_t)
    plan = plan_transition(50.0, 1.0, out_g, 200.0, Next(rec("two", 121, "8A"), 300.0, 0.0, in_g, lead=1.2), "skip")
    assert plan.kind == "cut" and plan.start == plan.drop
    assert plan.offset == pytest.approx(float(in_t[np.searchsorted(in_t, 1.37 - 0.05)]), abs=1e-6)
    assert np.min(np.abs(out_t - plan.drop)) < 1e-6                     # on the outgoing's tracked beat


def test_two_tracked_beats_that_would_drift_apart_are_not_blended():
    out_t = np.arange(0.0, 400.0, 0.5)                                   # 120.00 bpm
    in_t = np.arange(0.0, 400.0, 60.0 / 119.8)                           # drifts 64 beats * ~0.8 ms = 54 ms
    out_g = Grid(120.0, 0.0, 8.0, ticks=out_t)
    in_g = Grid(120.0, 0.0, 8.0, ticks=in_t)                             # the catalog says the same tempo
    plan = plan_transition(3.0, 1.0, out_g, 600.0, Next(rec("two", 120, "8A"), 600.0, 0.0, in_g), "skip", 64)
    assert plan.kind == "blend"                                          # the stretch from the ticks absorbs it
    in_g2 = Grid(120.0, 0.0, 8.0, ticks=np.arange(0.0, 400.0, 0.5) * np.linspace(1, 1.012, 800))   # tempo moves 1.2%
    plan2 = plan_transition(3.0, 1.0, out_g, 600.0, Next(rec("two", 120, "8A"), 600.0, 0.0, in_g2), "skip", 64)
    assert plan2.kind in ("blend", "cut")
    if plan2.kind == "cut":
        assert plan2.fallback == "drift"

def test_a_switch_without_ticks_starts_at_bar_one():
    plan = plan_transition(50.0, 1.0, Grid(120.0, 0.0, 8.0, bar_known=False), 200.0,
                           Next(rec("two", 121, "8A"), 300.0, 0.0, Grid(121.0, 1.37, 8.0), lead=1.2), "skip")
    assert plan.kind == "cut" and plan.start == plan.drop and plan.offset == pytest.approx(1.37)

def test_a_blend_called_off_mid_frame_does_not_stop_playback():
    """A skip or a crate load from the booth calls a planned blend off on its
    own thread; a frame that read the plan before it and the incoming deck after
    it raised "'NoneType' object has no attribute 'slot'" and discord.py stopped
    the set (twice on 4 Oct)."""
    src, _ = _source()
    src.skip()
    assert wait_until(lambda: src.plan is not None)
    assert not src.blend_started()
    real_split = src.current.split
    fired = []

    def split_then_call_off(frame):
        if not fired:
            fired.append(1)
            with src._lock:
                src._call_off_plan()                 # the booth's thread, mid-frame
        return real_split(frame)
    src.current.split = split_then_call_off
    for _ in range(5):
        assert src.read()                            # no exception, frames keep coming
    assert fired and src.current is not None


def sine(freq: float, amp: float, seconds: float):
    """A fake decoded record: a steady tone (stereo), in the mids/highs."""
    n = int(seconds * FRAMES_PER_S) * R.FRAME_SAMPLES
    x = (amp * np.sin(2 * np.pi * freq * np.arange(n) / RATE)).astype(np.int16)
    data = np.repeat(x, 2).tobytes()
    return lambda path, ratio, gain=0.0, offset=0.0, **kw: io.BytesIO(data)


def test_an_unlocked_transition_echoes_out_under_the_next_record():
    """A failed blend verification falls back without losing an active pitch rate."""
    from utils.audio import mixcheck
    unlocked = lambda *a: (mixcheck.Verdict(False, 16, 3, why="no common beat"), 0.0)
    first = Deck(rec("one", 120, "8A"), 1.0, 20.0, sine(3000, 8000, 20.0))
    assert first.set_pitch(1.04)
    for _ in range(R.PITCH_BEND_RAMP_FRAMES):
        assert first.frame()  # settle the rate before the planner takes ownership
    assert first.pitch_rate == pytest.approx(1.04)
    queue = [nxt(STEADY)]
    src = CrossfadeSource(first, lambda deck: queue.pop() if queue else None, stream_factory=tone(0, 20.0),
                          grid_at=lambda record, start, seconds: STEADY, mix_beats=16, verify=unlocked)
    wait_for(first, 100)
    wait_until(lambda: src._queued is not None)
    plan = _plan(src)
    assert plan.kind == "echo" and plan.fallback == "unlocked"
    assert plan.playback_rate == pytest.approx(1.04)
    wall_drop = plan.drop / plan.playback_rate
    wall_beat = plan.beat / plan.playback_rate
    rms = []
    for _ in range(int((wall_drop + 4.0) * FRAMES_PER_S)):
        f = src.read()
        x = np.frombuffer(f, dtype=np.int16).astype(np.float32) if f else np.zeros(1)
        rms.append(float(np.sqrt(np.mean(x * x))))
        if len(rms) % 10 == 0:
            time.sleep(0.005)                    # let the incoming deck's reader keep up
    at = lambda t: rms[int(t * FRAMES_PER_S)]
    assert at(wall_drop - 0.3) > 4000                          # the outgoing, full
    first_repeat, third_repeat = at(wall_drop + 0.2 * wall_beat), at(wall_drop + 2.2 * wall_beat)
    assert first_repeat > 1000 and third_repeat < first_repeat  # it rings on, and dies away
    assert at(wall_drop + (R.ECHO_REPEATS + 1) * wall_beat) < 50  # gone after the repeats


class _SlowRenderer:
    def __init__(self, frames, delay=0.0, block_event=None, entered=None):
        self.frames = iter(frames)
        self.delay = delay
        self.block_event = block_event
        self.entered = entered

    def read(self):
        if self.entered is not None:
            self.entered.set()
        if self.block_event is not None:
            self.block_event.wait(timeout=2.0)
        if self.delay:
            time.sleep(self.delay)
        return next(self.frames, b"")

    def cleanup(self):
        pass


def test_buffered_records_read_never_waits_for_a_slow_mixer(monkeypatch):
    import threading
    from utils.audio.records import BufferedRecordsSource, SILENCE

    def forbidden_log(*args, **kwargs):
        pytest.fail("the Discord audio callback must not log synchronously")

    monkeypatch.setattr(R, "log_debug", forbidden_log)
    monkeypatch.setattr(R, "log_warning", forbidden_log)
    release = threading.Event()
    entered = threading.Event()
    renderer = _SlowRenderer([b"frame"], block_event=release, entered=entered)
    source = BufferedRecordsSource(renderer, buffer_frames=3)
    try:
        assert entered.wait(1.0)
        before = time.perf_counter()
        assert source.read() == SILENCE
        elapsed = time.perf_counter() - before
        assert elapsed < 0.02
        assert source.underruns == 1

        release.set()
        assert source.wait_ready(1, timeout=1.0)
        assert source.read() == b"frame"
        assert source.wait_ready(1, timeout=1.0)  # renderer has reached EOF
        assert source.read() == b""
    finally:
        release.set()
        source.cleanup()


def test_buffered_records_source_preserves_frame_order_and_bounds_memory():
    from utils.audio.records import BufferedRecordsSource

    frames = [f"frame-{i}".encode() for i in range(20)]
    renderer = _SlowRenderer(frames, delay=0.001)
    source = BufferedRecordsSource(renderer, buffer_frames=3)
    try:
        assert source.wait_ready(3, timeout=1.0)
        assert source._frames.qsize() <= 3
        assert [source.read(), source.read(), source.read()] == frames[:3]
        assert source.wait_ready(3, timeout=1.0)
        assert [source.read(), source.read(), source.read()] == frames[3:6]
        assert source._frames.qsize() <= 3
    finally:
        source.cleanup()


def test_buffered_records_source_tracks_late_voice_reads(monkeypatch):
    from utils.audio.records import BufferedRecordsSource

    def forbidden_log(*args, **kwargs):
        pytest.fail("the Discord audio callback must not log synchronously")

    monkeypatch.setattr(R, "log_debug", forbidden_log)
    monkeypatch.setattr(R, "log_warning", forbidden_log)
    renderer = _SlowRenderer([b"a", b"b", b"c"], delay=0.001)
    source = BufferedRecordsSource(renderer, buffer_frames=3)
    try:
        assert source.wait_ready(3, timeout=1.0)
        assert source.read() == b"a"
        time.sleep(R.LATE_S + 0.02)
        assert source.read() == b"b"
        assert source.late_count == 1
        assert source.late[0] >= R.LATE_S
        assert source.worst_late >= R.LATE_S
    finally:
        source.cleanup()

def test_deck_close_reaps_ffmpeg_and_closes_its_pipe():
    """A retired deck must not leave a killed ffmpeg child or stdout handle."""
    class Decoder:
        def __init__(self):
            self.stdout = io.BytesIO()
            self.returncode = None
            self.kill_calls = 0
            self.wait_calls = 0

        def poll(self):
            return self.returncode

        def kill(self):
            self.kill_calls += 1
            self.returncode = -9

        def wait(self, timeout=None):
            self.wait_calls += 1
            assert timeout is not None
            return self.returncode

    decoder = Decoder()
    deck = Deck(rec("decoder-cleanup", 120, "8A"), 1.0, 1.0,
                stream_factory=lambda *_args, **_kwargs: decoder)

    deck.close()
    deck.close()  # cleanup is safe if transition and session shutdown both retire it

    assert decoder.kill_calls == 1
    assert decoder.wait_calls == 1
    assert decoder.stdout.closed
    assert not deck._pump_thread.is_alive()



def test_a_cued_record_keeps_who_chose_it_and_its_bassline():
    """Moving the cue rebuilt the record field by field and dropped its source:
    a record loaded at the booth then counted as her pick, and a replan swapped
    it for one that locked (22 Oct: DVRST loaded, Dirty Laundry mixed in)."""
    from types import SimpleNamespace
    from utils.audio import beatgrid
    rec = R.library.Record(path="/m/a.mp3", artist="A", title="a", bpm=120, key="8A", genre="House")
    nxt = R.Next(rec, 240.0, -1.0, beatgrid.Grid(120.0, 0.5, 6.0, bar_known=True), 0.5, bass_in=16, source="hand")
    fake = SimpleNamespace(cue=32.3, snap=R.CrossfadeSource.snap,
                           _grid_at=lambda *a, **k: beatgrid.Grid(120.0, 0.5, 6.0, bar_known=True))
    out = R.CrossfadeSource._cued(fake, nxt)
    assert out.source == "hand" and out.bass_in == 16 and out.gain == -1.0
    assert abs(out.lead - 32.5) < 1e-9 and out.grid.downbeat == out.lead      # snapped to a bar
    fake_none = SimpleNamespace(cue=10.0, snap=R.CrossfadeSource.snap, _grid_at=lambda *a, **k: None)
    assert R.CrossfadeSource._cued(fake_none, R.Next(rec, 240.0, source="hand")).source == "hand"


def test_next_pressed_while_a_booth_load_is_reading_waits_for_it():
    """A NEXT during the seconds a crate pick is being read planned with
    nothing loaded, and she mixed in her own record instead."""
    import threading
    import time as _t
    from types import SimpleNamespace
    calls = []
    session = R.RecordsSession.__new__(R.RecordsSession)
    session._load_lock = threading.Lock()
    session._closing = False
    session.loading = "Cam Wales — Ambulance"
    session.source = SimpleNamespace(skip=lambda: calls.append(("skip", session.loading)))
    session.skip()
    _t.sleep(0.15)
    assert calls == []                                   # still reading: nothing planned yet
    session.loading = None
    for _ in range(40):
        if calls:
            break
        _t.sleep(0.05)
    assert calls == [("skip", None)]
    session.skip()                                       # nothing loading: at once
    assert calls[-1] == ("skip", None) and len(calls) == 2


def test_short_gaps_and_the_buffer_low_water_are_counted_too():
    """"No late frames" counted only gaps over LATE_S; what a listener's jitter
    buffer may not hide, and how close the mixer came to running dry, were
    invisible."""
    renderer = _SlowRenderer([b"a", b"b", b"c", b"d"], delay=0.001)
    source = R.BufferedRecordsSource(renderer, buffer_frames=4)
    try:
        assert source.wait_ready(4, timeout=1.0)
        assert source.read() == b"a"
        time.sleep((R.JITTER_S + R.LATE_S) / 2)
        assert source.read() == b"b"
        assert source.jitter_count == 1 and source.late_count == 0
    finally:
        source.cleanup()
    slow = R.BufferedRecordsSource(_SlowRenderer([b"x"] * 40, delay=0.05), buffer_frames=4)
    try:
        assert slow.wait_ready(4, timeout=2.0)
        for _ in range(4):                     # faster than the mixer refills
            slow.read()
        assert slow.low_water <= 2
    finally:
        slow.cleanup()


def test_a_key_shift_keeps_the_voice_and_both_channels_move_together(monkeypatch):
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "has_rubberband", lambda: True)
    shifted = beatgrid.stretch_filter(0.95, 1)
    assert "formant=preserved" in shifted and "pitchq=quality" in shifted
    assert "channels=together" in beatgrid.stretch_filter(0.95)
    assert "formant" not in beatgrid.stretch_filter(0.95)            # nothing to keep without a shift


def test_a_record_loaded_by_hand_is_not_scrubbed_a_minute_in_to_find_a_lock(monkeypatch):
    """Cued 32 bars in, Urgent came in mid-song (24 Oct). A booth load or a
    request comes in from its start or a phrase in; her own picks may still be
    scrubbed further."""
    from utils.audio import setlist
    tried = []

    def fake_plan(*a, in_bars=None, **k):
        tried.append(in_bars)
        return R.Plan("cut", 0.0, 0.0, 0.5, 0.5, 1.0, a[4], fallback="bar")     # not a blend; try the next cue

    monkeypatch.setattr(R, "plan_transition", fake_plan)
    record = rec("hand", 120, "8A")
    for source, allowed in (("hand", set(setlist.HAND_CUES)), ("partner", set(setlist.CUES))):
        tried.clear()
        nxt = Next(record, 200.0, source=source)
        setlist.find_blend(10.0, "/o.mp3", 1.0, STEADY, 200.0, nxt, "skip", 32,
                           verify_fn=lambda *a: (None, 0.0), lengths=[32])
        assert set(tried) <= allowed and (32 in tried) == (source == "partner")


def test_a_decoder_behind_is_counted_not_hidden():
    """A deck whose decoder is behind plays silence; the voice thread's meters
    see a frame on time and nothing else."""
    import threading
    gate = threading.Event()

    class SlowPipe:
        def read(self, n):
            gate.wait(2.0)
            return b""

    before = R.DECKS_STARVED
    deck = Deck(rec("slow", 120, "8A"), 1.0, 10.0, stream_factory=lambda *a, **k: SlowPipe())
    try:
        assert deck.frame() == R.SILENCE and deck.frame() == R.SILENCE
        assert R.DECKS_STARVED - before == 2 and deck.played == 0
    finally:
        gate.set()
        deck.close()


def test_a_set_waits_for_its_first_record_to_buffer():
    import threading
    calls = {"n": 0}

    class FakeDeck:
        def ready(self, frames):
            calls["n"] += 1
            return calls["n"] > 3
    assert R._wait_deck(FakeDeck(), 25, 1.0) is True and calls["n"] >= 4
    class Never:
        def ready(self, frames):
            return False
    t0 = time.monotonic()
    assert R._wait_deck(Never(), 25, 0.1) is False and time.monotonic() - t0 < 0.5




def _load_race_session():
    import threading
    from types import SimpleNamespace

    session = R.RecordsSession.__new__(R.RecordsSession)
    session._closing = False
    session._load_lock = threading.Lock()
    session._load_generation = 0
    session.loading = None
    session.last_load = None
    session.requests = []
    session.requested_by = "tester"
    session.say = lambda *_args: None
    session.voice_source = None
    session._task = None
    session.started_at = time.time()
    session.names = []

    class Mixer:
        def __init__(self):
            self.loaded = []
            self._lock = threading.RLock()

        def load(self, nxt):
            with self._lock:
                self.loaded.append(nxt.record.title)
                return "loaded"

        def cleanup(self):
            pass

    session.source = Mixer()
    return session


def _new_load_thread(previous):
    import threading
    current = set(threading.enumerate()) - previous
    return next(t for t in current if t.name == "kaia-records-load")


def test_newest_booth_load_wins_when_older_analysis_finishes_last():
    import threading
    from types import SimpleNamespace

    session = _load_race_session()
    started = {name: threading.Event() for name in ("Old", "New")}
    release = {name: threading.Event() for name in ("Old", "New")}

    def prepare(rec):
        started[rec.title].set()
        assert release[rec.title].wait(timeout=3.0)
        return R.Next(rec, 60.0)

    session._prepare = prepare
    old = SimpleNamespace(name="Old record", title="Old", path="/old.mp3")
    new = SimpleNamespace(name="New record", title="New", path="/new.mp3")

    before = set(threading.enumerate())
    session.load(old)
    old_worker = _new_load_thread(before)
    assert started["Old"].wait(timeout=1.0)

    before = set(threading.enumerate())
    session.load(new)
    new_worker = _new_load_thread(before)
    assert started["New"].wait(timeout=1.0)

    release["New"].set()
    new_worker.join(timeout=1.0)
    assert not new_worker.is_alive()
    assert session.loading is None
    assert session.source.loaded == ["New"]

    # The old worker finishes only after the latest choice has committed.
    release["Old"].set()
    old_worker.join(timeout=1.0)
    assert not old_worker.is_alive()
    assert session.source.loaded == ["New"]
    assert session.last_load["name"] == "New record"


def test_after_load_waits_for_the_latest_booth_load_not_an_older_worker():
    import threading
    from types import SimpleNamespace

    session = _load_race_session()
    started = {name: threading.Event() for name in ("Old", "New")}
    release = {name: threading.Event() for name in ("Old", "New")}
    callbacks = []
    callback_done = threading.Event()

    def prepare(rec):
        started[rec.title].set()
        assert release[rec.title].wait(timeout=3.0)
        return R.Next(rec, 60.0)

    session._prepare = prepare
    old = SimpleNamespace(name="Old record", title="Old", path="/old.mp3")
    new = SimpleNamespace(name="New record", title="New", path="/new.mp3")

    before = set(threading.enumerate())
    session.load(old)
    old_worker = _new_load_thread(before)
    assert started["Old"].wait(timeout=1.0)

    before = set(threading.enumerate())
    session.load(new)
    new_worker = _new_load_thread(before)
    assert started["New"].wait(timeout=1.0)

    def after():
        callbacks.append(tuple(session.source.loaded))
        callback_done.set()

    session.after_load(after)
    release["Old"].set()
    old_worker.join(timeout=1.0)
    assert not old_worker.is_alive()
    assert session.loading == "New record"
    assert not callback_done.wait(timeout=0.15)

    release["New"].set()
    new_worker.join(timeout=1.0)
    assert not new_worker.is_alive()
    assert callback_done.wait(timeout=1.0)
    assert callbacks == [("New",)]


def test_records_session_stop_invalidates_outstanding_booth_loads():
    import asyncio
    import threading
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    session = _load_race_session()
    started = threading.Event()
    release = threading.Event()
    rec = SimpleNamespace(name="Late record", title="Late", path="/late.mp3")

    def prepare(_rec):
        started.set()
        assert release.wait(timeout=3.0)
        return R.Next(rec, 60.0)

    session._prepare = prepare
    session.vc = SimpleNamespace(
        guild=SimpleNamespace(id=99117),
        is_playing=lambda: False,
        disconnect=AsyncMock(),
    )
    before = set(threading.enumerate())
    session.load(rec)
    worker = _new_load_thread(before)
    assert started.wait(timeout=1.0)

    asyncio.run(session.stop(disconnect=False))
    assert session.loading is None
    release.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()
    assert session.source.loaded == []
    assert session.last_load is None


def test_skip_is_deferred_until_an_in_progress_end_planner_releases_ownership(monkeypatch):
    import threading

    src, _ = _source()
    entered = threading.Event()
    release = threading.Event()
    original = R._music_end
    calls = []

    def blocked_end(deck):
        calls.append(threading.get_ident())
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=3.0)
        return original(deck)

    monkeypatch.setattr(R, "_music_end", blocked_end)
    src._begin_planning("end")
    assert entered.wait(timeout=1.0)
    assert src._planning and src.planning_mode == "end"

    src.skip()
    assert src._planning
    assert src.planning_mode == "end"
    assert src._pending_planning_mode == "skip"
    assert src.plan is None

    # Repeated NEXTs while one is already queued do not move it or spawn another
    # deferred planner.
    src.skip()
    assert src._pending_planning_mode == "skip"

    release.set()
    deadline = time.time() + 5.0
    while (src.plan is None or src.plan.mode != "skip") and time.time() < deadline:
        time.sleep(0.01)

    assert src.plan is not None and src.plan.mode == "skip"
    assert src._pending_planning_mode is None
    assert not src._planning or src.planning_mode == "skip"



def _blocking_frame_source():
    import threading
    from types import SimpleNamespace

    entered = threading.Event()
    release = threading.Event()

    class BlockingDeck:
        def __init__(self):
            self.record = SimpleNamespace(path="/tmp/records-frame-lock.mp3", name="Current")
            self.remaining = 20_000
            self.slot = 1
            self.played = 0
            self.ratio = 1.0
            self.grid = None
            self.closed = False

        def at(self, frames=None):
            return 0.0

        def frame(self):
            entered.set()
            assert release.wait(timeout=3.0), "test did not release the rendered frame"
            self.played += 1
            return bytes(FRAME_BYTES)

        def close(self):
            self.closed = True

    deck = BlockingDeck()
    source = CrossfadeSource(deck, pick=lambda _deck: None)
    source.rides = False
    return source, deck, entered, release


def test_booth_load_waits_for_the_current_audio_frame_boundary():
    import threading
    from types import SimpleNamespace

    source, deck, entered, release = _blocking_frame_source()
    frame_result = []
    read_thread = threading.Thread(target=lambda: frame_result.append(source.read()), daemon=True)
    read_thread.start()
    assert entered.wait(timeout=1.0)

    record = SimpleNamespace(path="/tmp/next.mp3", name="Next")
    nxt = Next(record, 180.0)
    mutation_done = threading.Event()
    mutation_thread = threading.Thread(
        target=lambda: (source.load(nxt), mutation_done.set()), daemon=True
    )
    mutation_thread.start()
    try:
        assert not mutation_done.wait(timeout=0.15), "booth load mutated the mixer during a rendered frame"
    finally:
        release.set()
        read_thread.join(timeout=1.0)
        mutation_thread.join(timeout=1.0)

    assert not read_thread.is_alive() and not mutation_thread.is_alive()
    assert frame_result == [bytes(FRAME_BYTES)]
    assert mutation_done.is_set()
    assert source._queued is nxt
    source.cleanup()
    assert deck.closed


def test_dashboard_fader_change_waits_for_audio_frame_boundary(monkeypatch):
    import threading
    from types import SimpleNamespace
    from utils.audio import dj_dashboard

    source, _deck, entered, release = _blocking_frame_source()
    frame_thread = threading.Thread(target=source.read, daemon=True)
    frame_thread.start()
    assert entered.wait(timeout=1.0)

    sent = []
    handler = object.__new__(dj_dashboard._Handler)
    handler.path = "/control"
    handler._body = lambda: {"slot": 1, "name": "fader", "value": 0.0}
    handler._local = lambda: True                    # the request came from the booth's own page
    handler._send = lambda *args: sent.append(args)
    monkeypatch.setattr(dj_dashboard, "_session", lambda: SimpleNamespace(source=source))

    request_done = threading.Event()
    request_thread = threading.Thread(
        target=lambda: (handler.do_POST(), request_done.set()),
        daemon=True,
    )
    request_thread.start()
    try:
        assert not request_done.wait(timeout=0.15), "dashboard changed a fader during a rendered frame"
    finally:
        release.set()
        frame_thread.join(timeout=1.0)
        request_thread.join(timeout=1.0)

    assert not frame_thread.is_alive() and not request_thread.is_alive()
    assert request_done.is_set()
    assert sent == [(204, b"", "text/plain")]
    assert source.controls.channels[1]["fader"] == 0.0
    source.cleanup()


def test_renderer_cleanup_waits_for_in_progress_frame():
    import threading

    source, deck, entered, release = _blocking_frame_source()
    frame_thread = threading.Thread(target=source.read, daemon=True)
    frame_thread.start()
    assert entered.wait(timeout=1.0)

    cleanup_done = threading.Event()
    cleanup_thread = threading.Thread(
        target=lambda: (source.cleanup(), cleanup_done.set()), daemon=True
    )
    cleanup_thread.start()
    try:
        assert not cleanup_done.wait(timeout=0.15), "cleanup retired the current deck mid-frame"
    finally:
        release.set()
        frame_thread.join(timeout=1.0)
        cleanup_thread.join(timeout=1.0)

    assert not frame_thread.is_alive() and not cleanup_thread.is_alive()
    assert cleanup_done.is_set()
    assert deck.closed


def test_dashboard_snapshot_waits_for_a_committed_audio_frame(monkeypatch):
    import threading
    from types import SimpleNamespace
    from utils.audio import dj_dashboard

    source, _deck, entered, release = _blocking_frame_source()
    frame_thread = threading.Thread(target=source.read, daemon=True)
    frame_thread.start()
    assert entered.wait(timeout=1.0)

    snapshot_read = threading.Event()
    snapshot_done = threading.Event()
    monkeypatch.setattr(
        dj_dashboard, "_snapshot_locked",
        lambda _session, _source, _mood=None: (snapshot_read.set() or {"live": True}),
    )
    session = SimpleNamespace(source=source)
    result = []
    snapshot_thread = threading.Thread(
        target=lambda: (result.append(dj_dashboard.snapshot(session)), snapshot_done.set()),
        daemon=True,
    )
    snapshot_thread.start()
    try:
        assert not snapshot_done.wait(timeout=0.15), "dashboard snapshot read a half-rendered mixer frame"
        assert not snapshot_read.is_set()
    finally:
        release.set()
        frame_thread.join(timeout=1.0)
        snapshot_thread.join(timeout=1.0)

    assert not frame_thread.is_alive() and not snapshot_thread.is_alive()
    assert snapshot_done.is_set() and snapshot_read.is_set()
    assert result == [{"live": True}]
    source.cleanup()


def test_records_load_worker_obeys_mixer_then_load_lock_order():
    import threading
    from types import SimpleNamespace

    session = _load_race_session()
    prepared = threading.Event()
    release_prepare = threading.Event()
    first_mixer_attempt = threading.Event()
    inversion_seen = threading.Event()

    class OwnedLock:
        def __init__(self):
            self._lock = threading.Lock()
            self._owner = None

        def __enter__(self):
            self._lock.acquire()
            self._owner = threading.get_ident()
            return self

        def __exit__(self, *_args):
            self._owner = None
            self._lock.release()

        def held_by_current_thread(self):
            return self._owner == threading.get_ident()

    owned_load_lock = OwnedLock()
    session._load_lock = owned_load_lock

    class ObservedRLock:
        def __init__(self):
            self._lock = threading.RLock()
            self._first_worker_attempt = set()

        def __enter__(self):
            ident = threading.get_ident()
            if threading.current_thread().name == "kaia-records-load" and ident not in self._first_worker_attempt:
                self._first_worker_attempt.add(ident)
                first_mixer_attempt.set()
                if owned_load_lock.held_by_current_thread():
                    inversion_seen.set()
            self._lock.acquire()
            return self

        def __exit__(self, *_args):
            self._lock.release()

    session.source._lock = ObservedRLock()

    def prepare(record):
        prepared.set()
        assert release_prepare.wait(timeout=2.0)
        return R.Next(record, 60.0)

    session._prepare = prepare
    record = SimpleNamespace(name="Chosen record", title="Chosen", path="/chosen.mp3")

    # Simulate the dashboard already holding the mixer lock when it requests
    # another load. The worker must wait for that lock without holding the
    # session lock, otherwise this route and the worker form a lock cycle.
    with session.source._lock:
        before = set(threading.enumerate())
        session.load(record)
        worker = _new_load_thread(before)
        assert prepared.wait(timeout=1.0)
        release_prepare.set()
        assert first_mixer_attempt.wait(timeout=1.0)
        assert not inversion_seen.is_set(), "load worker held _load_lock while waiting for mixer lock"

    worker.join(timeout=1.0)
    assert not worker.is_alive()
    assert session.source.loaded == ["Chosen"]


def test_measured_alternatives_use_normalized_lock_quality_and_artist_variety(monkeypatch):
    import random
    from types import SimpleNamespace
    from utils.audio import beatgrid

    current = rec("current", 124, "8A", "House")
    current = library.Record(current.path, "Alpha", current.title, current.bpm, current.key, current.genre)
    good = library.Record("/music/good.mp3", "Beta", "good", 124.0, "8A", "House")
    same_artist = library.Record("/music/repeat.mp3", "Alpha", "repeat", 124.0, "8A", "House")
    lower_confidence = library.Record("/music/lower.mp3", "Gamma", "lower", 124.0, "8A", "House")

    graph = {"edges": {current.path: {
        good.path: {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0},
        same_artist.path: {"beats": 64, "agree": 14, "bars": 16, "ratio": 1.0},
        # More raw agreeing bars, but a lower share of its longer overlap.
        lower_confidence.path: {"beats": 128, "agree": 20, "bars": 32, "ratio": 1.0},
    }}}
    session = R.RecordsSession.__new__(R.RecordsSession)
    session.played = []
    session._by_path = {r.path: r for r in (current, good, same_artist, lower_confidence)}
    session.graph = graph
    session.crate = [current, good, same_artist, lower_confidence]
    session._rng = random.Random(4)
    session._listener_intent_lock = threading.Lock()
    session._listener_intent = None
    session._listener_pick_generation = 0
    session._listener_intent_min_pick_generation = 1
    monkeypatch.setattr(beatgrid, "ticks_for", lambda _path, _bpm=None: [0.0])

    deck = SimpleNamespace(record=current, grid=SimpleNamespace(bpm=124.0), ratio=1.0)
    ordered = session._candidates(deck)

    assert [r.path for r in ordered[:3]] == [good.path, same_artist.path, lower_confidence.path]


def test_loudness_gain_cache_is_keyed_by_audio_identity(monkeypatch):
    identity = {"value": "audio-one"}
    calls = []
    monkeypatch.setattr(R.library, "audio_signature", lambda _path, **_kwargs: identity["value"])

    def fake_run(*_args, **_kwargs):
        calls.append(identity["value"])
        return types.SimpleNamespace(stderr="I: -15.0 LUFS\nPeak: -2.0 dBFS\n")

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    R.gain_db.cache_clear()
    first = R.gain_db("/same/path.mp3")
    identity["value"] = "audio-two"
    second = R.gain_db("/same/path.mp3")

    assert first == second
    assert calls == ["audio-one", "audio-two"]
    R.gain_db.cache_clear()


def test_records_session_checks_audio_graph_identity_off_event_loop(monkeypatch):
    import threading

    from utils.audio import setlist

    checked = threading.Event()
    thread_names = []
    monkeypatch.setattr(setlist, "needs_build",
                        lambda *_args: thread_names.append(threading.current_thread().name) or checked.set() or False)

    vc = types.SimpleNamespace(
        guild=types.SimpleNamespace(id=1),
        channel=types.SimpleNamespace(name="General", members=[]),
    )
    session = R.RecordsSession(vc, [], "Ekco")
    assert checked.wait(2.0)
    assert thread_names == ["kaia-records-graph-check"]
    assert session.graph is not None




def test_crossfader_rejects_non_finite_values_without_poisoning_mixer_state():
    controls = R.Controls()
    for value in (float("nan"), float("inf"), float("-inf")):
        assert not controls.set(None, "xfader", value)
        assert not controls.set(None, "master", value)
        assert not controls.set(1, "fader", value)
    assert controls.xfader is None
    assert controls.master == 1.0
    assert controls.channels[1]["fader"] == 1.0


def test_source_advances_configuration_ramp_once_per_rendered_frame():
    deck = Deck(rec("crossfade-ramp", 120, "8A"), 1.0, 600.0, tone(1000, 600.0))
    src = CrossfadeSource(deck, pick=lambda _deck: None, stream_factory=tone(-1000, 600.0), mix_beats=16)
    src.rides = False
    wait_for(deck, 12)
    try:
        assert src.controls.set(None, "xfader", 0.25)
        start = (src.controls.channel(1)[3], src.controls.channel(2)[3])
        assert start == pytest.approx((1.0, 0.5))
        assert src.controls.set(None, "xfader_curve", "constant_power")

        src.read()
        after_one = (src.controls.channel(1)[3], src.controls.channel(2)[3])
        assert after_one[0] < start[0] and after_one[0] > 0.9238795
        assert after_one[1] < start[1] and after_one[1] > 0.3826834

        for _ in range(src.controls.XFADER_RAMP_FRAMES - 1):
            src.read()
        finished = (src.controls.channel(1)[3], src.controls.channel(2)[3])
        assert finished == pytest.approx((0.9238795325, 0.3826834324), abs=1e-8)
        assert src.controls._xfader_ramp is None
    finally:
        src.cleanup()


def test_crossfader_default_curve_preserves_the_existing_overlap_law():
    controls = R.Controls()
    assert controls.xfader is None
    assert controls.xfader_curve == "standard"
    assert controls.xfader_assignments == {1: "A", 2: "B"}

    controls.set(None, "xfader", 0.25)
    # The old law holds A full for the first half of travel and B full for
    # the second half, with both decks full at the centre.
    assert controls.channel(1)[3] == pytest.approx(1.0)
    assert controls.channel(2)[3] == pytest.approx(0.5)
    controls.set(None, "xfader", 0.5)
    assert controls.channel(1)[3] == pytest.approx(1.0)
    assert controls.channel(2)[3] == pytest.approx(1.0)


def test_crossfader_constant_power_curve_ramps_to_equal_power_targets():
    controls = R.Controls()
    controls.set(None, "xfader", 0.25)
    before = (controls.channel(1)[3], controls.channel(2)[3])
    assert before == pytest.approx((1.0, 0.5))

    assert controls.set(None, "xfader_curve", "constant_power")
    # Configuration is staged until the next committed PCM frame.
    controls.advance_frame()
    first = (controls.channel(1)[3], controls.channel(2)[3])
    assert first[0] < before[0] and first[0] > 0.9238795
    assert first[1] < before[1] and first[1] > 0.3826834

    for _ in range(controls.XFADER_RAMP_FRAMES - 1):
        controls.advance_frame()
    final = (controls.channel(1)[3], controls.channel(2)[3])
    assert final == pytest.approx((0.9238795325, 0.3826834324), abs=1e-8)
    assert final[0] ** 2 + final[1] ** 2 == pytest.approx(1.0, abs=1e-8)


def test_crossfader_cut_curve_switches_at_a_defined_midpoint():
    controls = R.Controls()
    controls.set(None, "xfader_curve", "cut")
    controls.set(None, "xfader", 0.499)
    assert controls.channel(1)[3] == 1.0
    assert controls.channel(2)[3] == 0.0
    controls.set(None, "xfader", 0.5)
    assert controls.channel(1)[3] == 0.0
    assert controls.channel(2)[3] == 1.0


def test_crossfader_assignment_can_route_a_deck_to_either_side_or_thru():
    controls = R.Controls()
    controls.set(None, "xfader", 0.25)

    assert controls.set(1, "xfader_assignment", "B")
    for _ in range(controls.XFADER_RAMP_FRAMES):
        controls.advance_frame()
    assert controls.channel(1)[3] == pytest.approx(0.5)
    assert controls.channel(2)[3] == pytest.approx(0.5)

    assert controls.set(2, "xfader_assignment", "THRU")
    for _ in range(controls.XFADER_RAMP_FRAMES):
        controls.advance_frame()
    assert controls.channel(2)[3] == pytest.approx(1.0)
    assert controls.state()["xfader_assignments"] == {"1": "B", "2": "THRU"}


def test_crossfader_curve_and_assignment_validation_rejects_unknown_values():
    controls = R.Controls()
    assert not controls.set(None, "xfader_curve", "exponential")
    assert not controls.set(1, "xfader_assignment", "C")
    assert not controls.set(3, "xfader_assignment", "A")
    assert controls.xfader_curve == "standard"
    assert controls.xfader_assignments == {1: "A", 2: "B"}


def test_crossfader_direct_fader_movement_is_immediate_during_config_ramp():
    controls = R.Controls()
    controls.set(None, "xfader", 0.5)
    controls.set(None, "xfader_curve", "cut")
    controls.advance_frame()
    assert controls._xfader_ramp is not None

    controls.set(None, "xfader", 0.25)
    assert controls._xfader_ramp is None
    assert controls.channel(1)[3] == 1.0
    assert controls.channel(2)[3] == 0.0


def _slip_live_position(deck):
    """The source clock that keeps moving underneath a slip roll."""
    return (deck.played * FRAME_SAMPLES - deck.pad) / RATE + deck.offset / deck.ratio


def test_slip_roll_repeats_predecoded_pcm_while_the_live_deck_clock_advances(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None

    assert src.set_roll(1, 1, pressed=True)
    roll = deck._roll
    assert roll is not None and roll.beats == 1
    assert len(roll.frames) == 25
    assert roll.release_played is None

    while deck.played < roll.start_played:
        deck.frame()
    first_cycle = [deck.frame() for _ in range(len(roll.frames))]
    second_cycle = [deck.frame() for _ in range(len(roll.frames))]
    assert first_cycle == second_cycle
    assert deck.played == roll.start_played + 2 * len(roll.frames)

    # Deck.at() reports the repeated roll cursor; the independent live clock
    # has continued beyond the segment and will be restored on release.
    assert deck.at() == pytest.approx(roll.start_own / deck.ratio)
    live_before_release = _slip_live_position(deck)
    assert live_before_release > roll.end_own / deck.ratio

    assert src.set_roll(1, 1, pressed=False)
    assert deck._roll is not None and deck._roll.release_played == deck.played
    release_start = deck._roll.release_played
    deadline = time.monotonic() + 1.0
    while deck._roll is not None and time.monotonic() < deadline:
        before = deck.played
        deck.frame()
        if deck.played == before:
            # A temporarily empty decoder returns silence without advancing
            # the source clock; give its pump time to refill before retrying.
            time.sleep(0.002)
    assert deck._roll is None
    assert deck.played == release_start + R.SLIP_ROLL_RELEASE_FRAMES
    assert deck.at() == pytest.approx(_slip_live_position(deck))
    assert deck.at() > roll.end_own / deck.ratio


def test_slip_roll_keeps_program_and_pfl_on_the_same_repeating_and_live_frames(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None
    src.controls.set(None, "phones", 1.0)
    src.controls.set(None, "phones_mix", 0.0)
    assert src.set_headphones(1)
    stream = src.attach_headphone_stream()
    assert stream is not None

    try:
        assert src.set_roll(1, 2, pressed=True)
        roll = deck._roll
        head = src._headphones_deck
        assert roll is not None and head is not None and head._roll is not None
        while deck.played < roll.start_played:
            program = src.read()
            monitor = stream.get_nowait()
            assert np.allclose(np.frombuffer(program, np.int16),
                               np.frombuffer(monitor, np.int16), atol=1)

        # The program and isolated PFL repeat exactly the same phrase.
        for _ in range(len(roll.frames) * 2):
            program = src.read()
            monitor = stream.get_nowait()
            assert np.allclose(np.frombuffer(program, np.int16),
                               np.frombuffer(monitor, np.int16), atol=1)

        assert deck.played > roll.start_played + len(roll.frames)
        assert deck.at() == pytest.approx(roll.start_own / deck.ratio)
        assert _slip_live_position(deck) > roll.end_own / deck.ratio

        assert src.set_roll(1, 2, pressed=False)
        assert deck._roll is not None and head._roll is not None
        for _ in range(R.SLIP_ROLL_RELEASE_FRAMES):
            program = src.read()
            monitor = stream.get_nowait()
            assert np.allclose(np.frombuffer(program, np.int16),
                               np.frombuffer(monitor, np.int16), atol=1)
        assert deck._roll is None and head._roll is None
        assert deck.at() == pytest.approx(_slip_live_position(deck))
    finally:
        src.detach_headphone_stream(stream)
        src.set_headphones(None)


def test_slip_roll_times_out_and_crossfades_back_when_pointer_release_is_lost(loop_source):
    from dataclasses import replace

    deck = loop_source.current
    assert deck is not None
    src = loop_source
    assert src.set_roll(1, 1, pressed=True)
    roll = deck._roll
    assert roll is not None
    deck._roll = replace(roll, max_frames=3)

    while deck.played < roll.start_played:
        deck.frame()
    for _ in range(3 + R.SLIP_ROLL_RELEASE_FRAMES + 1):
        deck.frame()
    assert deck._roll is None
    assert deck.at() == pytest.approx(_slip_live_position(deck))


def test_slip_roll_rejects_conflicting_loop_transition_pause_and_unusable_grids(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None

    src._planning = True
    assert not src.set_roll(1, 1, pressed=True)
    src._planning = False

    src._pending_planning_mode = "skip"
    assert not src.set_roll(1, 1, pressed=True)
    src._pending_planning_mode = None

    src.paused.add(1)
    assert not src.set_roll(1, 1, pressed=True)
    src.paused.clear()

    deck.grid = Grid(bpm=120.0, downbeat=0.0, contrast=8.0, bar_known=False)
    assert not src.set_roll(1, 1, pressed=True)
    deck.grid = STEADY

    assert src.set_loop(1, 2)
    assert not src.set_roll(1, 1, pressed=True)


def test_loop_arming_rechecks_jog_ownership_after_pcm_preparation(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None and src.set_headphones(1)
    head = src._headphones_deck
    assert head is not None

    original_factory = src._factory
    entered, release = threading.Event(), threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(target=lambda: result.append(src.set_loop(1, 2)), daemon=True)
    worker.start()
    try:
        assert entered.wait(timeout=1.0)
        assert src.set_bend(1, 1.05)
    finally:
        release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert result == [False]
    assert deck.bend_active and head.bend_active
    assert not deck.loop_active and not head.loop_active


def test_slip_roll_arming_rechecks_pitch_ownership_after_pcm_preparation(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None and src.set_headphones(1)
    head = src._headphones_deck
    assert head is not None

    original_factory = src._factory
    entered = threading.Event()
    release = threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(
        target=lambda: result.append(src.set_roll(1, 2, pressed=True)),
        daemon=True,
    )
    worker.start()
    try:
        assert entered.wait(timeout=1.0)
        # A pitch ramp started while the counted phrase is being decoded.
        assert src.set_pitch(1, 1.05)
    finally:
        release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert result == [False]
    assert deck.pitch_control_active and head.pitch_control_active
    assert not deck.roll_active and not head.roll_active


def test_slip_roll_arming_rechecks_jog_ownership_after_pcm_preparation(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None and src.set_headphones(1)
    head = src._headphones_deck
    assert head is not None

    original_factory = src._factory
    entered, release = threading.Event(), threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(
        target=lambda: result.append(src.set_roll(1, 2, pressed=True)), daemon=True
    )
    worker.start()
    try:
        assert entered.wait(timeout=1.0)
        assert src.set_bend(1, 1.05)
    finally:
        release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert result == [False]
    assert deck.bend_active and head.bend_active
    assert not deck.roll_active and not head.roll_active


@pytest.mark.parametrize("target,expected_direction", [(1.08, 1), (0.92, -1)])
def test_live_jog_bend_resamples_the_pcm_and_tracks_the_real_source_cursor(target, expected_direction):
    values = np.arange(30_000, dtype=np.int16)
    pcm = np.repeat(values, 2).tobytes()

    def ramp_factory(_path, _ratio, **_kwargs):
        return io.BytesIO(pcm)

    deck = Deck(rec("jog-ramp", 120, "8A"), 1.0, 0.6, ramp_factory)
    wait_for(deck, 30)
    try:
        start = deck.at()
        assert deck.set_bend(target)
        assert deck.bend["active"] is True

        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 12):
            frame = deck.frame()
            assert frame is not None and len(frame) == FRAME_BYTES

        assert deck.bend["rate"] == pytest.approx(target, abs=1e-5)
        output = np.frombuffer(deck.frame(), dtype=np.int16).reshape(-1, 2)[:, 0].astype(np.float32)
        mean_step = float(np.mean(np.diff(output[100:850])))
        assert mean_step > 1.04 if expected_direction > 0 else mean_step < 0.96

        consumed = deck._source_samples
        rendered_frames = R.PITCH_BEND_RAMP_FRAMES + 13
        neutral_consumption = rendered_frames * FRAME_SAMPLES
        if expected_direction > 0:
            assert consumed > neutral_consumption
        else:
            assert consumed < neutral_consumption
        assert deck.at() > start if expected_direction > 0 else deck.at() < start + rendered_frames * FRAME_SAMPLES / RATE

        # Releasing the platter ramps back to 1.0 without jumping the source cursor.
        before_release = deck._source_samples
        assert deck.set_bend(1.0, release=True)
        for _ in range(R.PITCH_BEND_RAMP_FRAMES):
            assert deck.frame() is not None
        assert deck.bend["active"] is False
        assert deck.bend["rate"] == pytest.approx(1.0)
        assert deck._source_samples > before_release
        assert deck.at() == pytest.approx(
            (deck._source_samples - deck.pad) / RATE + deck.offset / deck.ratio
        )
    finally:
        deck.close()


def test_live_jog_ring_stays_bounded_across_repeated_slow_holds():
    values = np.arange(720_000, dtype=np.int16)
    pcm = np.column_stack((values, values)).astype(np.int16).tobytes()

    def ramp_factory(_path, _ratio, **_kwargs):
        return io.BytesIO(pcm)

    deck = Deck(rec("repeated-jog", 120, "8A"), 1.0, 15.0, ramp_factory)
    wait_for(deck, 25)
    try:
        for _ in range(5):
            assert deck.set_bend(0.92)
            for _ in range(40):
                frame = deck.frame()
                assert frame is not None and len(frame) == FRAME_BYTES
            assert deck.set_bend(1.0, release=True)
            for _ in range(R.PITCH_BEND_RAMP_FRAMES):
                frame = deck.frame()
                assert frame is not None and len(frame) == FRAME_BYTES
            assert deck.bend_active is False
            # The ring contains only the interpolation look-ahead, not a
            # growing backlog from each 8% slow-down.
            buffered = deck._bend_write_pos - deck._bend_read_pos
            assert 0 <= buffered < 2 * FRAME_SAMPLES
            assert deck._bend_capacity == R.PITCH_BEND_BUFFER_FRAMES * FRAME_SAMPLES + 2 * FRAME_SAMPLES
        assert deck.played == 5 * (40 + R.PITCH_BEND_RAMP_FRAMES)
        assert deck._source_samples > 0
    finally:
        deck.close()


def test_live_jog_bend_keeps_program_and_pfl_decoders_in_lockstep(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None
    src.controls.set(None, "phones", 1.0)
    src.controls.set(None, "phones_mix", 0.0)
    assert src.set_headphones(1)
    stream = src.attach_headphone_stream()
    assert stream is not None
    head = src._headphones_deck
    assert head is not None
    try:
        assert src.set_bend(1, 1.06)
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 15):
            program = src.read()
            monitor = stream.get_nowait()
            assert np.allclose(np.frombuffer(program, np.int16),
                               np.frombuffer(monitor, np.int16), atol=1)
        assert deck.bend["rate"] == head.bend["rate"] == pytest.approx(1.06)
        assert deck._source_samples == pytest.approx(head._source_samples, abs=1.0)
        assert deck.at() == pytest.approx(head.at(), abs=1.0 / R.RATE)

        assert src.set_bend(1, 1.0, release=True)
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 2):
            program = src.read()
            monitor = stream.get_nowait()
            assert np.allclose(np.frombuffer(program, np.int16),
                               np.frombuffer(monitor, np.int16), atol=1)
        assert not deck.bend_active and not head.bend_active
        assert deck._source_samples == pytest.approx(head._source_samples, abs=1.0)
    finally:
        src.detach_headphone_stream(stream)
        src.set_headphones(None)


def test_live_jog_start_guard_reserves_fastest_rate_timeout_and_release_headroom(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None
    original = deck._source_samples
    try:
        # At base speed 540 output frames appear to exceed the old 518-frame
        # guard, but a +8% hold can consume those samples before its 500-frame
        # timeout and eight-frame return ramp have completed.
        with src._lock:
            deck._source_samples = (
                deck.total_frames * FRAME_SAMPLES - 540 * FRAME_SAMPLES
            )
        assert deck.remaining == 540
        assert not src.set_bend(1, 1.08)

        # Once the same hold has started with sufficient headroom, subsequent
        # platter updates are not re-rejected as its remaining time decreases.
        with src._lock:
            deck._source_samples = (
                deck.total_frames * FRAME_SAMPLES
                - (R.PITCH_BEND_START_HEADROOM_FRAMES + 1) * FRAME_SAMPLES
            )
        assert src.set_bend(1, 1.08)
        with src._lock:
            deck._source_samples = (
                deck.total_frames * FRAME_SAMPLES - 540 * FRAME_SAMPLES
            )
        assert src.set_bend(1, 1.04)
        assert deck.bend["target"] == pytest.approx(1.04)
        assert src.set_bend(1, 1.0, release=True)
    finally:
        with src._lock:
            deck._source_samples = original


def test_live_jog_bend_validation_conflicts_timeout_and_skip_release(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None

    for bad in (True, False, float("nan"), float("inf"), 10 ** 1000, 0.91, 1.09, "1.02", None):
        assert not src.set_bend(1, bad)

    src._planning = True
    assert not src.set_bend(1, 1.04)
    src._planning = False

    # The glide worker can be preparing a splice before _splice is published.
    src._gliding = True
    assert not src.set_bend(1, 1.04)
    src._gliding = False

    src.paused.add(1)
    assert not src.set_bend(1, 1.04)
    src.paused.clear()

    assert src.set_loop(1, 2)
    assert not src.set_bend(1, 1.04)
    assert src.set_loop(1, None)
    while src._pending_loop_exit is not None:
        src.read()

    assert src.set_bend(1, 1.04)
    assert deck.bend_active
    assert not src.set_loop(1, 2)
    assert not src.set_roll(1, 1, pressed=True)
    assert not src.jump_to_cue(1, 5.0)
    src.skip()
    assert deck.bend["target"] == pytest.approx(1.0)


def test_live_jog_timeout_covers_the_whole_hold_across_the_neutral_crossing(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None

    assert src.set_bend(1, 1.05)
    for _ in range(R.PITCH_BEND_RAMP_FRAMES + 2):
        src.read()
    assert deck.bend["rate"] == pytest.approx(1.05)

    # Returning to the platter centre is not a pointer release.
    assert src.set_bend(1, 1.0)
    assert deck._bend_hold_active is True
    deck._bend_frames = R.PITCH_BEND_MAX_FRAMES - 1
    src.read()
    assert deck._bend_expired is True
    assert deck._bend_hold_active is False
    assert src.set_bend(1, 1.06) is False

    # The rate returns to unity and the planner may proceed after the ramp.
    for _ in range(R.PITCH_BEND_RAMP_FRAMES + 2):
        src.read()
    assert deck.bend_active is False
    assert deck._bend_expired is True
    assert src.plan is None
    assert src.set_bend(1, 1.06) is False
    assert not src.set_loop(1, 2)
    assert not src.set_roll(1, 1, pressed=True)
    assert not src.jump_to_cue(1, 5.0)

    # The expired hold stays latched until an explicit release arrives.
    assert src.set_bend(1, 1.0, release=True)
    assert deck._bend_expired is False
    assert src.set_bend(1, 1.04)
    assert src.set_bend(1, 1.0, release=True)


def test_live_jog_bend_defers_automatic_planning_until_neutral(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None
    src._glide_next = 0
    assert src.set_bend(1, 1.04)

    for _ in range(15):
        src.read()
    assert src.plan is None
    assert deck.bend_active

    assert src.set_bend(1, 1.0, release=True)
    for _ in range(R.PITCH_BEND_RAMP_FRAMES):
        src.read()
    assert not deck.bend_active



def test_persistent_pitch_fader_composes_with_live_jog_and_returns_to_its_setting():
    deck = Deck(rec("pitch-ride", 120, "8A"), 1.0, 5.0, tone(1000, 5.0))
    wait_for(deck, 30)
    try:
        start = deck.at()
        assert deck.set_pitch(1.06)
        assert deck.pitch_ramping
        for _ in range(R.PITCH_BEND_RAMP_FRAMES):
            frame = deck.frame()
            assert frame is not None and len(frame) == FRAME_BYTES
        assert deck.pitch_rate == pytest.approx(1.06)
        assert deck.playback_rate == pytest.approx(1.06)

        assert deck.set_bend(1.04)
        for _ in range(R.PITCH_BEND_RAMP_FRAMES):
            frame = deck.frame()
            assert frame is not None and len(frame) == FRAME_BYTES
        assert deck.playback_rate == pytest.approx(1.06 * 1.04)
        assert deck.at() > start
        assert deck.remaining == int(
            max(0.0, deck.total_frames * FRAME_SAMPLES - deck._source_samples)
            // (FRAME_SAMPLES * deck.playback_rate)
        )

        # Jog release returns to the persistent fader, not to unity.
        assert deck.set_bend(1.0, release=True)
        for _ in range(R.PITCH_BEND_RAMP_FRAMES):
            frame = deck.frame()
            assert frame is not None and len(frame) == FRAME_BYTES
        assert deck.bend["rate"] == pytest.approx(1.0)
        assert deck.pitch_rate == pytest.approx(1.06)
        assert deck.playback_rate == pytest.approx(1.06)

        assert deck.set_pitch(1.0)
        for _ in range(R.PITCH_BEND_RAMP_FRAMES):
            frame = deck.frame()
            assert frame is not None and len(frame) == FRAME_BYTES
        assert deck.pitch_rate == pytest.approx(1.0)
        assert deck.playback_rate == pytest.approx(1.0)
        assert deck.set_pitch(1.081) is False
        assert deck.set_pitch(True) is False
        assert deck.set_pitch(float("nan")) is False
    finally:
        deck.close()


def test_pitch_fader_waits_until_the_tempo_echo_tail_clears(loop_source):
    src = loop_source
    deck = src.current
    assert deck is not None

    assert src.set_echo(True, beats=1.0)
    assert src.effects.active
    assert src.set_pitch(1, 1.04) is False
    assert deck.pitch_rate == pytest.approx(1.0)

    # The input gate is off, but changing tempo during this fixed-delay tail
    # would still detune its repeats from the beat it was armed against.
    assert src.set_echo(False)
    assert src.effects.tail_active
    assert src.set_pitch(1, 1.04) is False

    for _ in range(200):
        if not src.effects.tail_active:
            break
        src.read()
    assert not src.effects.tail_active
    assert src.set_pitch(1, 1.04)


def test_transition_planner_matches_the_incoming_deck_to_the_persistent_pitch_rate():
    plan = plan_transition(
        3.1, 1.0, STEADY, 60.0, nxt(), "skip", 16, lead=2.0,
        playback_rate=1.04,
    )
    assert plan.kind == "blend"
    assert plan.playback_rate == pytest.approx(1.04)
    assert plan.ratio == pytest.approx(1.04)
    # Transition coordinates remain in decoded-source time; wall BPM changes.
    assert plan.beat == pytest.approx(0.5)
    assert plan.length == pytest.approx(8.0)
    assert plan.drop >= 3.1 + 0.75 + 2.0 * 1.04



def test_transition_without_outgoing_grid_scales_lead_to_pitch_source_clock():
    plan = plan_transition(
        10.0, 1.0, None, 30.0, nxt(), "skip", 16, lead=0.4,
        playback_rate=1.04,
    )
    assert plan.kind == "cut"
    assert plan.playback_rate == pytest.approx(1.04)
    assert plan.drop == pytest.approx(10.0 + 0.4 * 1.04)

def test_pfl_replacement_rechecks_pitch_ramp_after_off_lock_decoder_prepare(headphone_source):
    src = headphone_source
    assert src.set_headphones(1)
    old_head = src._headphones_deck
    assert old_head is not None

    original_factory = src._factory
    entered = threading.Event()
    release = threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(
        target=lambda: result.append(src.set_headphones(1, force=True)),
        daemon=True,
    )
    worker.start()
    try:
        # The preview has captured the current 1.0 pitch rate and is building
        # outside the mixer lock. Change the fader before the next render frame
        # moves the instantaneous rate away from 1.0.
        assert entered.wait(timeout=1.0)
        assert src.set_pitch(1, 1.05)
        assert src.current is not None and src.current.pitch_ramping
        assert old_head.pitch_ramping
    finally:
        release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert result == [False]
    assert src._headphones_deck is old_head
    assert src.current is not None and src.current.pitch_ramping
    assert old_head.pitch_ramping

def test_pfl_replacement_rechecks_jog_ownership_after_off_lock_decoder_prepare(headphone_source):
    src = headphone_source
    assert src.set_headphones(1)
    old_head = src._headphones_deck
    assert old_head is not None

    original_factory = src._factory
    entered = threading.Event()
    release = threading.Event()

    def blocking_factory(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=3.0)
        return original_factory(*args, **kwargs)

    src._factory = blocking_factory
    result = []
    worker = threading.Thread(
        target=lambda: result.append(src.set_headphones(1, force=True)),
        daemon=True,
    )
    worker.start()
    try:
        assert entered.wait(timeout=1.0)
        # A momentary jog starts after the preview captured the old rate but
        # before the replacement decoder can be committed.
        assert src.set_bend(1, 1.05)
        assert src.current is not None and src.current.bend_active
        assert old_head.bend_active
    finally:
        release.set()
        worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert result == [False]
    assert src._headphones_deck is old_head
    assert src.current is not None and src.current.bend_active
    assert old_head.bend_active

def test_pfl_can_be_rebuilt_at_a_steady_non_unity_pitch(headphone_source):
    src = headphone_source
    assert src.set_headphones(1)
    assert src.set_pitch(1, 1.05)
    for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
        src.read()

    program = src.current
    old_head = src._headphones_deck
    assert program is not None and old_head is not None
    assert not program.pitch_ramping and not old_head.pitch_ramping
    assert program.pitch_rate == pytest.approx(1.05)
    assert old_head.pitch_rate == pytest.approx(1.05)

    # A steady fader setting is inherited by a fresh decoder; only a ramp
    # in flight should make the off-lock preview stale.
    assert src.set_headphones(1, force=True)
    preview = src._headphones_deck
    assert preview is not None and preview is not old_head
    assert preview.pitch_rate == pytest.approx(1.05)
    assert not preview.pitch_ramping
    assert preview.at() == pytest.approx(program.at(), abs=1 / R.FRAMES_PER_S)

