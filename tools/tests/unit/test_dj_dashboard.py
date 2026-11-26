"""Unit and HTTP tests for the DJ booth's real mixer and deck controls."""
import io
import json
import time
import threading
import types
import urllib.request

import numpy as np
import pytest

from utils.audio import dj_dashboard as D
from utils.audio import library
from utils.audio import records as R
from utils.audio.beatgrid import Grid


@pytest.fixture(autouse=True)
def _blends_measured_as_locked(monkeypatch):
    """These tests use fake records with no audio to measure; every planned
    blend is taken as measured and locked unless a test says otherwise."""
    from utils.audio import mixcheck, records as _R
    monkeypatch.setattr(_R, "_default_verify",
                        lambda *a: (mixcheck.Verdict(True, 16, 16, agree=16), 0.0))
    monkeypatch.setattr(_R, "_envelope", lambda path: None)

FB = R.FRAME_BYTES


def tone(value, seconds):
    data = np.full(int(seconds * R.FRAMES_PER_S) * FB // 2, value, dtype=np.int16).tobytes()
    return lambda path, ratio, gain=0.0, offset=0.0: io.BytesIO(data)


def rec(name):
    return library.Record(path=f"/music/{name}.mp3", artist="A", title=name, bpm=120, key="8A", genre="House")


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(D, "_want_wave", lambda path: D.track_id(path))
    monkeypatch.setattr(D, "_mood", lambda: {"arousal": 0.5})
    first = R.Deck(rec("one"), 1.0, 300.0, tone(1000, 20.0))      # long enough not to plan its end yet
    first.grid = Grid(120.0, 0.0, 8.0)
    queue = [R.Next(rec("two"), 300.0, 0.0, Grid(120.0, 0.0, 8.0))]
    vc = types.SimpleNamespace(guild=types.SimpleNamespace(id=7), channel=types.SimpleNamespace(name="General", members=[]))
    s = R.RecordsSession(vc, [], "Ekco")
    s.source = R.CrossfadeSource(first, lambda d: queue.pop() if queue else None, stream_factory=tone(-1000, 20.0),
                                 grid_at=lambda *a: Grid(120.0, 0.0, 8.0))
    s.source._fine = lambda deck, plan: None
    s._humans = lambda: ["Ekco"]
    s.names = ["A — one"]
    deadline = time.time() + 2
    while (s.source._queued is None or not first.ready(50)) and time.time() < deadline:
        time.sleep(0.01)
    monkeypatch.setitem(R._sessions, 7, s)
    yield s
    R._sessions.pop(7, None)


def test_the_snapshot_is_the_mixers_state(session):
    for _ in range(25):
        session.source.read()
    snap = D.snapshot(session)
    assert snap["live"] and snap["channel"] == "General"
    one = snap["decks"]["1"]
    assert one["state"] == "playing" and one["title"] == "one" and one["tempo"] == 120.0
    assert one["pos"] == pytest.approx(0.5, abs=0.03)
    assert snap["decks"]["2"]["state"] == "loaded"          # the next record, on the other deck
    assert snap["channels"]["1"]["high"] == 1.0 and snap["mix"] is None
    assert snap["master"] == pytest.approx(20 * np.log10(1000 / 32768), abs=0.2)   # the tone, in dBFS
    json.dumps(snap)


def test_the_stream_says_which_frame_is_being_heard(session):
    """The mixer renders ahead of the voice thread by its buffer. The meters
    were timed by the newest frame: 300 ms before the sound, and often a frame
    the page had not been sent yet, which it skipped."""
    src = session.source
    session.voice_source = types.SimpleNamespace(_frames=types.SimpleNamespace(qsize=lambda: 15),
                                                 late_count=0, worst_late=0.0)
    for _ in range(60):
        src.read()
    snap = D.snapshot(session)
    assert snap["frame"] == 60 and snap["buffered"] == 15 and snap["heard"] == 45
    rows = [r[0] for r in snap["meter"]]
    assert rows[-1] == 59 and rows[0] <= snap["heard"] - 20      # the frame being heard, and the half second before it
    session.voice_source = None
    snap = D.snapshot(session)
    assert snap["heard"] == snap["frame"] and snap["buffered"] == 0


def test_a_blend_says_where_in_the_outgoing_record_the_swap_was_put(session):
    session.source.skip()
    assert _wait(lambda: session.source.plan is not None)
    assert D.snapshot(session)["mix"]["where"] == ""
    session.source.plan.where = "outro"
    assert D.snapshot(session)["mix"]["where"] == "outro"


def test_a_planned_blend_shows_on_both_decks_and_the_mixer(session):
    session.source.skip()
    deadline = time.time() + 5
    while session.source.plan is None and time.time() < deadline:
        time.sleep(0.01)
    snap = D.snapshot(session)
    assert snap["mix"]["kind"] == "blend" and snap["mix"]["out_slot"] == "1" and snap["mix"]["in_slot"] == "2"
    assert snap["decks"]["2"]["state"] in ("cued", "playing")
    deadline = time.time() + 2                # the history entry follows the plan by a moment
    while not session.source.history and time.time() < deadline:
        time.sleep(0.01)
    assert session.source.history[-1]["to"] == "A — two"


def test_the_booth_serves_state_and_skips(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    called = []
    monkeypatch.setattr(session, "skip", lambda: called.append(1))
    base = D.serve()
    try:
        with urllib.request.urlopen(base + "state", timeout=5) as r:
            assert json.loads(r.read())["live"]
        with urllib.request.urlopen(base, timeout=5) as r:
            assert b"KAIA" in r.read()
        req = urllib.request.Request(base + "skip", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 204
        assert called == [1]
    finally:
        srv, D._server = D._server, None
        srv.shutdown()


def test_headphone_route_serves_pfl_pcm_and_reports_selected_deck(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    src = session.source
    base = D.serve()
    response = None
    worker = None
    try:
        request = urllib.request.Request(
            base + "phones",
            data=json.dumps({"slot": 1}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as result:
            assert result.status == 204
        assert src._headphones_slot == 1
        assert D.snapshot(session)["headphones"] == {"slot": 1, "id": D.track_id(src._headphones_deck.record.path)}

        response = urllib.request.urlopen(base + "phones/stream", timeout=5)
        assert response.status == 200
        assert response.headers.get("X-Kaia-PCM") == "s16le;rate=48000;channels=2;frame_ms=20"
        assert response.headers.get("Transfer-Encoding") == "chunked"

        def render():
            for _ in range(20):
                src.read()

        worker = threading.Thread(target=render, daemon=True)
        worker.start()
        frame = response.read(R.FRAME_BYTES)
        assert len(frame) == R.FRAME_BYTES
        assert np.max(np.abs(np.frombuffer(frame, dtype=np.int16))) > 0
    finally:
        if response is not None:
            response.close()
        if worker is not None:
            worker.join(timeout=2)
        src.set_headphones(None)
        server, D._server = D._server, None
        if server:
            server.shutdown()


def test_booth_asset_routes_phones_through_audio_worklet_not_track_files():
    page = D.PAGE.read_text(encoding="utf-8")
    assert 'id="phmix"' in page
    assert 'phones_mix' in page
    assert '"/phones/stream"' in page
    assert "AudioWorkletNode" in page
    assert 'new Audio("/audio/' not in page
    assert "phonesTick" not in page
    assert 'data-cue-kind="memory"' in page
    assert 'data-cue-kind="hot"' in page
    assert 'post("/cuebank"' in page
    assert 'e.shiftKey ? "store" : "toggle"' in page
    assert 'e.preventDefault(); sendCueBank("hot", index, "clear")' in page
    assert 'data-loop-beats="1"' in page
    assert 'data-loop-beats="8"' in page
    assert 'post("/loop"' in page
    assert 'data-loop-exit' in page


def test_hot_and_memory_cue_http_controls_store_recall_clear_and_publish_state(session, monkeypatch, tmp_path):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    monkeypatch.setattr(D.record_cues, "record_key", lambda record: record.path)
    monkeypatch.setattr(D.record_cues, "telemetry_path", lambda _path: str(tmp_path / "cues.json"))
    D.record_cues.clear_cache()
    src = session.source
    for _ in range(20):
        src.read()
    record = src.current.record
    base = D.serve()

    def send(payload):
        request = urllib.request.Request(
            base + "cuebank",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    try:
        expected = src.current.at() * src.current.ratio
        stored = send({"slot": 1, "kind": "hot", "index": 0, "action": "toggle"})
        assert stored["action"] == "stored"
        assert stored["cue_bank"]["hot"][0] == pytest.approx(expected)
        memory = send({"slot": 1, "kind": "memory", "action": "toggle"})
        assert memory["action"] == "stored"
        snapshot = D.snapshot(session)
        assert snapshot["decks"]["1"]["cue_bank"]["memory"] == pytest.approx(expected)

        assert D.record_cues.set_hot(record, 0, 5.0)
        old_deck = src.current
        jumped = send({"slot": 1, "kind": "hot", "index": 0, "action": "toggle"})
        assert jumped["action"] == "jumped"
        assert src.current is not old_deck
        assert src.current.at() * src.current.ratio == pytest.approx(5.0, abs=0.03)

        cleared = send({"slot": 1, "kind": "hot", "index": 0, "action": "clear"})
        assert cleared["action"] == "cleared"
        assert cleared["cue_bank"]["hot"][0] is None
    finally:
        D.record_cues.clear_cache()
        server, D._server = D._server, None
        if server:
            server.shutdown()

def test_loop_http_route_validates_lengths_and_delegates_to_the_renderer(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    calls = []
    monkeypatch.setattr(session.source, "set_loop", lambda slot, beats: calls.append((slot, beats)) or True)
    base = D.serve()

    def request(payload):
        req = urllib.request.Request(
            base + "loop",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(req, timeout=5)

    try:
        with request({"slot": 1, "action": "set", "beats": 4}) as response:
            assert response.status == 204
        with request({"slot": "2", "action": "exit"}) as response:
            assert response.status == 204
        assert calls == [(1, 4), (2, None)]
        for invalid in (
            {"slot": 1, "action": "set", "beats": 16},
            {"slot": True, "action": "set", "beats": 2},
            {"slot": 1, "action": "set", "beats": True},
            {"slot": 1, "action": "other"},
        ):
            with pytest.raises(urllib.error.HTTPError) as error:
                request(invalid)
            assert error.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as error:
            req = urllib.request.Request(
                base + "loop", data=json.dumps({"slot": 1, "action": "set", "beats": 2}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            monkeypatch.setattr(session.source, "set_loop", lambda *_args: False)
            urllib.request.urlopen(req, timeout=5)
        assert error.value.code == 409
    finally:
        server, D._server = D._server, None
        if server:
            server.shutdown()

def test_decks_alternate_like_a_pair_of_cdjs(session):
    session.source.skip()
    deadline = time.time() + 5
    while session.source.incoming is None and time.time() < deadline:
        time.sleep(0.01)
    assert session.source.current.slot == 1 and session.source.incoming.slot == 2


def test_the_mixer_obeys_the_booth(session):
    """A channel fader pulled down silences that deck; the crossfader all the
    way to one side silences the other; the hand-back restores the automix."""
    src = session.source
    for _ in range(5):
        src.read()
    assert src.levels["master"] > -40
    src.controls.set(1, "fader", 0.0)
    frames = [src.read() for _ in range(4)]
    assert max(abs(int(x)) for x in np.frombuffer(frames[-1], np.int16)) == 0
    src.controls.reset()
    src.controls.set(None, "xfader", 1.0)                 # all channel 2: deck 1 is out
    assert np.frombuffer(src.read(), np.int16).max() == 0
    src.controls.set(None, "xfader", 0.5)                 # both full in the middle
    assert np.frombuffer(src.read(), np.int16).max() == pytest.approx(1000, abs=2)
    src.controls.set(1, "low", 0.0)                       # a constant tone is all low band
    out = np.frombuffer(src.read(), np.int16)
    assert np.abs(out).max() < 600


def test_a_paused_deck_holds_its_place(session):
    src = session.source
    for _ in range(10):
        src.read()
    at = src.current.played
    src.paused.add(1)
    assert all(f == R.SILENCE for f in (src.read() for _ in range(5)))
    assert src.current.played == at
    src.paused.discard(1)
    src.read()
    assert src.current.played == at + 1


def test_a_record_asked_for_at_the_booth_comes_next(session, monkeypatch):
    other = rec("asked")
    session.crate = [other]
    monkeypatch.setattr(R, "probe_seconds", lambda p: 200.0)
    monkeypatch.setattr(R, "gain_db", lambda p: 0.0)
    from utils.audio import beatgrid
    monkeypatch.setattr(beatgrid, "grid_for", lambda p, b: Grid(120.0, 0.0, 8.0))
    session.load(other)
    deadline = time.time() + 3
    while (session.source._queued is None or session.source._queued.record.title != "asked") and time.time() < deadline:
        time.sleep(0.01)
    assert session.source._queued.record.title == "asked" and not session.requests
    assert session.last_load["result"] == "loaded"
    listing = D.crate(session)
    assert listing["count"] == 1 and listing["genres"]["House"][0]["title"] == "asked"


def test_the_blend_length_is_chosen_at_the_booth_and_shortened_when_there_is_no_room(session):
    src = session.source
    assert src.set_mix_beats(256) and src._mix_beats == 256
    assert not src.set_mix_beats(48)                         # only the booth's three lengths
    # 40 s of record has no room for 256 beats or 128 (the outgoing is in a 128-beat
    # blend for 48 s: to the swap, and its tail): the planner halves it rather than cutting.
    src.current.total_frames = 40 * R.FRAMES_PER_S
    src.skip()
    deadline = time.time() + 5
    while src.plan is None and time.time() < deadline:
        time.sleep(0.01)
    assert src.plan.kind == "blend" and src.plan.length == pytest.approx(32.0)     # 64 beats at 120 bpm


def _wait(cond, seconds=5.0):
    deadline = time.time() + seconds
    while not cond() and time.time() < deadline:
        time.sleep(0.01)
    return cond()


def test_loading_a_record_puts_it_on_the_free_deck_now_and_calls_off_her_plan(session):
    src = session.source
    src.skip()
    assert _wait(lambda: src.plan is not None)          # Kaia's blend, planned but not started
    mine = R.Next(rec("mine"), 20.0, 0.0, Grid(120.0, 0.0, 8.0))
    assert src.load(mine) == "loaded"
    assert src.plan is None and src.incoming is None and src._queued is mine
    assert src.controls.channels[2]["fader"] == 0.0     # down, as a DJ loads a deck
    snap = D.snapshot(session)
    assert snap["decks"]["2"]["title"] == "mine" and snap["decks"]["2"]["hand"]


def test_a_deck_played_by_hand_starts_synced_on_the_bar_from_its_cue(session):
    src = session.source
    for _ in range(20):
        src.read()
    src.load(R.Next(rec("mine"), 20.0, 0.0, Grid(120.0, 0.0, 8.0)))
    assert src.set_cue(5.1) and src.cue == pytest.approx(6.0)      # snapped to its bar
    assert src.play_hand() == "starting"
    assert _wait(lambda: src.hand is not None)
    k = src._hand_k
    landing = (k * R.FRAME_SAMPLES + src.hand.pad) / R.RATE        # on-air seconds its cue plays at
    assert landing % 2.0 == pytest.approx(0.0, abs=1e-3) or landing % 2.0 == pytest.approx(2.0, abs=1e-3)
    assert src.hand.offset == pytest.approx(6.0) and src.hand_synced
    while src.current.played < k + 5:
        src.read()
    assert src._hand_on and src.levels["b"] > -60          # playing, heard pre-fader (its fader is down)


def test_a_hand_deck_takes_over_once_the_record_on_air_is_faded_down(session):
    src = session.source
    src.load(R.Next(rec("mine"), 20.0, 0.0, Grid(120.0, 0.0, 8.0)))
    src.play_hand()
    assert _wait(lambda: src.hand is not None)
    while not src._hand_on:
        src.read()
    src.controls.set(2, "fader", 1.0)
    for _ in range(10):
        src.read()
    assert src.current.record.title == "one"            # both up: nothing hands over
    src.controls.set(1, "fader", 0.0)
    for _ in range(int(R.HANDOVER_S * R.FRAMES_PER_S) + 2):
        src.read()
    assert src.current.record.title == "mine" and src.hand is None
    assert src.controls.channels[1]["fader"] == 1.0      # the empty channel is ready for her next one
    assert src.history[-1]["kind"] == "hand"


def test_next_with_a_hand_deck_playing_has_kaia_finish_the_mix(session):
    src = session.source
    src.load(R.Next(rec("mine"), 20.0, 0.0, Grid(120.0, 0.0, 8.0)))
    src.play_hand()
    assert _wait(lambda: src.hand is not None)
    while not src._hand_on:
        src.read()
    session.skip()
    assert src.plan.kind == "out" and src.incoming.record.title == "mine"
    assert src.controls.channels[2]["fader"] == 1.0      # never leaves the record she keeps silent
    for _ in range(int((src.plan.done - src.current.at()) * R.FRAMES_PER_S) + 3):
        src.read()
    assert src.current.record.title == "mine"


def test_cue_while_playing_stops_the_hand_deck_back_at_its_cue(session):
    src = session.source
    src.load(R.Next(rec("mine"), 20.0, 0.0, Grid(120.0, 0.0, 8.0)))
    src.set_cue(4.0)
    src.play_hand()
    assert _wait(lambda: src.hand is not None)
    for _ in range(80):
        src.read()
    assert src.stop_hand(back_to_cue=True)
    assert src.hand is None and src._queued.record.title == "mine" and src.cue == pytest.approx(4.0)


def test_the_booth_serves_a_record_for_the_headphones_with_ranges(session, monkeypatch, tmp_path):
    f = tmp_path / "x.mp3"
    f.write_bytes(bytes(range(256)) * 10)
    other = library.Record(path=str(f), artist="A", title="x", bpm=120, key="8A", genre="House")
    session.crate = [other]
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    base = D.serve()
    try:
        req = urllib.request.Request(base + "audio/" + D.track_id(str(f)), headers={"Range": "bytes=10-19"})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 206 and r.read() == bytes(range(10, 20))
            assert r.headers["Content-Range"] == "bytes 10-19/2560"
    finally:
        srv, D._server = D._server, None
        srv.shutdown()


def test_kaia_raises_a_hand_loaded_fader_only_when_her_blend_starts(session):
    src = session.source
    src.load(R.Next(rec("mine"), 300.0, 0.0, Grid(120.0, 0.0, 8.0)))
    src.skip()
    assert _wait(lambda: src.plan is not None)
    assert src.controls.channels[2]["fader"] == 0.0          # planned, not started: still down
    while src.current.played <= src._start_frame:
        src.read()
    assert src.controls.channels[2]["fader"] == 1.0


def test_cueing_the_record_already_in_her_plan_moves_the_cue(session):
    """She plans the end of a record minutes ahead, so the free deck's record
    is usually inside a plan; a cue there was refused and the jog snapped back."""
    src = session.source
    src.skip()
    assert _wait(lambda: src.plan is not None and src._queued is None)
    assert src.set_cue(6.1) and src.cue == pytest.approx(6.0)
    assert _wait(lambda: src.plan is not None)
    assert src.plan.offset == pytest.approx(6.0 - R.PREROLL_S)          # replanned from the cue


def test_the_sets_tab_lists_kaias_sets_and_plays_one(session, monkeypatch):
    """SETS: every pre-measured set, which one is playing, which the rotation
    starts next; PLAY makes the set's first unplayed record the next pick."""
    from utils.audio import setlist
    one, two = rec("one"), rec("two")
    a, b, c = rec("a"), rec("b"), rec("c")
    session.crate = [one, two, a, b, c]
    session._by_path = {r.path: r for r in session.crate}
    session.graph = {"sets": [[one.path, two.path, a.path, b.path], [a.path, b.path, c.path, two.path]]}
    session.set_list = session.graph["sets"][0]
    monkeypatch.setattr(setlist, "peek_rotation", lambda n: 1)
    data = D.sets(session)
    assert [len(x["tracks"]) for x in data["sets"]] == [4, 4] and data["next"] == 1
    assert data["sets"][0]["playing"] and not data["sets"][1]["playing"]
    assert data["sets"][0]["tracks"][0]["on_air"]

    assert session.play_set(1) == ("A — a", False)          # "one" is on air and not in set 2
    assert session.set_list == session.graph["sets"][1] and session.requests[0] == a.path
    assert session.play_set(0) == ("A — one", True)         # on air already: carry on along it
    assert session.play_set(9) is None


def test_an_open_booth_window_is_used_again_not_a_second_one(monkeypatch):
    """Flatpak Chrome's launcher exits after handing the window over, so the
    process we started reads as closed while the window is on screen. An open
    booth page is one connected to the stream; while there is one, nothing new
    is launched."""
    import threading, urllib.request
    from utils.infrastructure.system import app_window
    launched = []
    monkeypatch.setattr(app_window, "launch", lambda *a, **k: launched.append(a) or types.SimpleNamespace(poll=lambda: 0))
    monkeypatch.setattr(D, "_browser", lambda: None)
    monkeypatch.setattr(D, "_cfg", lambda key, default=None: 0 if key == "dj_dashboard_port" else default)
    monkeypatch.setattr(D, "_window", None)
    D.serve()
    try:
        monkeypatch.setattr(D, "_served_at", 0.0)             # no reconnect grace in a test
        stop = threading.Event()

        def page():
            with urllib.request.urlopen(D.url() + "events", timeout=5) as r:
                while not stop.is_set():
                    r.readline()
        t = threading.Thread(target=page, daemon=True)
        t.start()
        deadline = time.time() + 3
        while D.viewers() == 0 and time.time() < deadline:
            time.sleep(0.02)
        assert D.viewers() == 1
        D.open_window()
        assert launched == []                                  # the open window shows the set
        stop.set()
        t.join(3)
        deadline = time.time() + 3
        while D.viewers() and time.time() < deadline:
            time.sleep(0.05)
        D.open_window()
        assert len(launched) == 1                              # nothing open: one window
    finally:
        srv, D._server = D._server, None
        if srv:
            srv.shutdown()

def test_the_booth_reflows_in_compact_and_short_viewports():
    """Keep the dashboard panels accessible when the app window is resized."""
    page = D.PAGE.read_text(encoding="utf-8")
    assert "@media (max-width: 1050px)" in page
    assert "@media (max-width: 650px)" in page
    assert '@media (max-height: 720px) and (min-width: 1051px)' in page
    assert 'grid-template-areas: "deck1 deck2" "mixer mixer"' in page
    assert "overflow-y: auto" in page
    assert "@media (prefers-reduced-motion: reduce)" in page

def test_the_snapshot_uses_buffered_voice_callback_diagnostics(session):
    """Callback timing belongs to the buffered source, not the mix renderer."""
    session.voice_source = types.SimpleNamespace(late_count=3, worst_late=0.125)
    snap = D.snapshot(session)
    assert snap["late"] == {"count": 3, "worst_ms": 125}


def test_the_snapshot_defaults_lateness_when_no_buffer_or_legacy_counter_exists(session):
    """Synthetic/unbuffered sessions should still render state without diagnostics."""
    session.voice_source = None
    assert "late" in D.snapshot(session)
    assert D.snapshot(session)["late"] == {"count": 0, "worst_ms": 0}



def test_every_booth_launch_is_counted_so_an_open_page_shows_a_new_portrait(monkeypatch):
    """The booth window is reused across sets; the page reloads (and picks a
    new portrait of her) when the launch count it saw changes."""
    monkeypatch.setattr(D, "_launch", 0)
    monkeypatch.setattr(D, "_cfg", lambda _key, default=None: default)
    monkeypatch.setattr(D, "serve", lambda: "http://127.0.0.1:1/")
    monkeypatch.setattr(D, "viewers", lambda: 1)              # a page already open: reused
    monkeypatch.setattr(D, "_served_at", 0.0)
    D.open_window()
    D.open_window()
    assert D._launch == 2 and D.snapshot(None)["launch"] == 2


def test_the_booth_opens_in_chromium_before_google_chrome(monkeypatch):
    """A Chrome flatpak with wrappers on PATH was found first and opened in
    place of the system Chromium Ekco uses (31 Oct)."""
    installed = {"google-chrome-stable": "/opt/wrappers/google-chrome-stable",
                 "google-chrome": "/opt/wrappers/google-chrome", "chromium": "/usr/bin/chromium"}
    monkeypatch.setattr(D, "_chromium", None)
    monkeypatch.setattr(D, "_cfg", lambda key, default=None: "" if key == "dj_browser" else default)
    monkeypatch.setattr(D.shutil, "which", lambda name: installed.get(name))
    assert D._browser() == "/usr/bin/chromium"


def test_a_configured_booth_browser_still_wins(monkeypatch):
    monkeypatch.setattr(D, "_chromium", None)
    monkeypatch.setattr(D, "_cfg", lambda key, default=None: "/opt/brave/brave" if key == "dj_browser" else default)
    monkeypatch.setattr(D.shutil, "which", lambda name: "/usr/bin/" + name)
    assert D._browser() == "/opt/brave/brave"


def test_snapshot_exposes_skill_catalog_and_manual_lane_ownership(session):
    src = session.source
    before = D.snapshot(session)["skills"]
    assert before["enabled"] is True
    assert "solo_build_pressure" in before["catalog"]
    assert "blend_headroom_ride" in before["catalog"]
    assert "eq.low" in before["engine_capabilities"]
    assert "transition.echo_tail" in before["engine_capabilities"]
    assert before["manual_overrides"] == []

    assert src.set_control(1, "high", 0.7)
    after = D.snapshot(session)["skills"]
    assert ("1", "high") in [tuple(item) for item in after["manual_overrides"]]
    assert after["active"]["id"] == "manual_override"
    assert after["active"]["parameters"] == {"high": 0.7}
    assert after["active"]["phrase"]["kind"] == "manual release window"

    src.skill_scheduler.hand_back_all()
    handed_back = D.snapshot(session)["skills"]
    assert handed_back["manual_overrides"] == []
    assert handed_back["enabled"] is True


def test_booth_asset_exposes_crossfader_curve_and_assignment_controls():
    page = D.PAGE.read_text(encoding="utf-8")
    assert 'id="xfcurve"' in page
    assert 'id="xfassign1"' in page
    assert 'id="xfassign2"' in page
    assert 'value="constant_power"' in page
    assert 'value="cut"' in page
    assert 'post("/control", { slot, name, value: $(id).value })' in page


def test_booth_asset_displays_skill_name_and_explanation():
    page = D.PAGE.read_text(encoding="utf-8")
    assert "S.skills && S.skills.active" in page
    assert "skill.name" in page
    assert "skill.label" in page
    assert "skill.parameters" in page
    assert "skill.phrase" in page
    assert "parameterText" in page
    assert "phraseText" in page
    assert "manualText" in page
    assert "manual_overrides" in page




def test_booth_control_rides_and_reset_routes_transfer_skill_ownership(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    src = session.source
    base = D.serve()

    def post(path, payload=None):
        data = json.dumps(payload or {}).encode()
        req = urllib.request.Request(
            base + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            assert response.status == 204

    try:
        # The real booth control route must use CrossfadeSource.set_control,
        # not write directly around the scheduler's ownership tracking.
        post("/control", {"slot": 1, "name": "high", "value": 0.65})
        assert src.controls.channels[1]["high"] == pytest.approx(0.65)
        state = D.snapshot(session)["skills"]
        assert ("1", "high") in [tuple(item) for item in state["manual_overrides"]]
        assert state["active"]["parameters"] == {"high": 0.65}

        # String-valued mixer configuration must pass through set_control
        # without being misread as an EQ/fader value for manual ownership.
        manual_before = list(src.skill_scheduler.snapshot()["manual_overrides"])
        post("/control", {"slot": None, "name": "xfader_curve", "value": "constant_power"})
        post("/control", {"slot": 2, "name": "xfader_assignment", "value": "THRU"})
        post("/control", {"slot": None, "name": "xfader", "value": 0.15})
        controls = D.snapshot(session)["controls"]
        assert controls["xfader_curve"] == "constant_power"
        assert controls["xfader_assignments"] == {"1": "A", "2": "THRU"}
        assert controls["xfader"] == pytest.approx(0.15)
        assert src.skill_scheduler.snapshot()["manual_overrides"] == manual_before

        # HANDS off pauses skills; turning it back on resumes Kaia automation.
        post("/rides")
        assert src.rides is False and src.skill_scheduler.enabled is False
        post("/rides")
        assert src.rides is True and src.skill_scheduler.enabled is True

        # KAIA MIX clears paused decks, restores defaults, and explicitly
        # removes manual lane ownership before the next rendered frame.
        src.paused.add(1)
        post("/reset")
        assert not src.paused
        assert src.rides is True and src.skill_scheduler.enabled is True
        assert src.skill_scheduler.snapshot()["manual_overrides"] == []
        assert src.controls.channels[1]["high"] == pytest.approx(1.0)
        assert src.controls.state()["xfader_curve"] == "standard"
        assert src.controls.state()["xfader_assignments"] == {"1": "A", "2": "B"}
        assert src.controls.state()["xfader"] is None
    finally:
        server, D._server = D._server, None
        if server:
            server.shutdown()


def test_track_change_clears_previous_phrase_actions_before_new_profile_finishes(session):
    import zlib

    src = session.source
    phrase = types.SimpleNamespace(
        start=0.0, end=8.0, aligned=True, bars=4,
        section="drop_candidate", section_strength=0.9,
    )
    profile = types.SimpleNamespace(
        duration=300.0, aligned=True, phrase_bars=4, phrases=(phrase,),
    )
    src.skill_scheduler.set_solo_profile(profile, fingerprint=123)
    assert src.skill_scheduler.snapshot()["profile_loaded"] is True
    assert src.skill_scheduler.snapshot()["solo_actions"] == 2

    next_record = rec("next")
    src.current.record = next_record
    session._changed(next_record)

    state = src.skill_scheduler.snapshot()
    assert state["profile_loaded"] is False
    assert state["solo_actions"] == 0
    assert src.skill_scheduler.solo_fingerprint == (
        zlib.crc32(next_record.path.encode("utf-8")) & 0xFFFFFFFF
    )
    # The new profile request is queued, but the outgoing record's timeline is
    # already gone before the worker can read or compile the incoming record.
    assert session._skill_profile_queue.qsize() == 1


def test_master_echo_http_control_changes_real_pcm_and_releases_its_tail(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    src = session.source
    src.rides = False
    base = D.serve()

    def post(payload):
        request = urllib.request.Request(
            base + "fx/echo",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        assert post({
            "action": "on", "beats": 1, "feedback": 0.5, "wet": 0.30,
        }) == 204
        state = D.snapshot(session)
        assert state["fx"]["echo"]["enabled"] is True
        assert state["fx"]["echo"]["bpm"] == pytest.approx(120.0)
        assert state["fx"]["echo"]["delay_s"] == pytest.approx(0.5)

        # This fixture is a constant 1000-count signal. At 120 BPM a one-beat
        # repeat lands on rendered frame 25: dry 1000 + wet (1000 * .30) = 1300.
        frames = [src.read() for _ in range(26)]
        assert np.frombuffer(frames[0], np.int16).max() == pytest.approx(1000, abs=2)
        assert np.frombuffer(frames[25], np.int16).max() == pytest.approx(1300, abs=3)

        assert post({"action": "off"}) == 204
        tail = D.snapshot(session)["fx"]["echo"]
        assert tail["enabled"] is False and tail["tail"] is True
        assert post({"action": "on", "beats": 16, "feedback": 0.5, "wet": 0.3}) == 409

        # Hand-back is an explicit abort path: no wet state survives reset.
        request = urllib.request.Request(base + "reset", method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 204
        reset = D.snapshot(session)["fx"]["echo"]
        assert reset["enabled"] is False and reset["tail"] is False
    finally:
        server, D._server = D._server, None
        if server:
            server.shutdown()


def test_live_jog_http_control_updates_the_deck_and_releases_to_neutral(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    src = session.source
    base = D.serve()

    def post(payload):
        request = urllib.request.Request(
            base + "bend",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        assert post({"slot": 1, "action": "set", "rate": 1.05}) == 204
        assert src.current.bend["active"] is True
        assert src.current.bend["target"] == pytest.approx(1.05)
        # Dashboard tempo reports the applied sample rate, after the eight-frame ramp.
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
            src.read()
        state = D.snapshot(session)["decks"]["1"]
        assert state["bend"]["active"] is True
        assert state["tempo"] == pytest.approx(126.0)
        assert state["pitch"] == pytest.approx(5.0)

        assert post({"slot": 1, "action": "set", "rate": 1.081}) == 400
        assert post({"slot": 1, "action": "set", "rate": True}) == 400
        assert post({"slot": 1, "action": "set", "rate": float("nan")}) == 400
        assert post({"slot": 1, "action": "set", "rate": 10 ** 1000}) == 400

        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 5):
            src.read()
        assert src.current.bend["rate"] == pytest.approx(1.05)

        assert post({"slot": 1, "action": "release"}) == 204
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
            src.read()
        assert src.current.bend["active"] is False
        assert src.current.bend["rate"] == pytest.approx(1.0)
        assert post({"slot": 1, "action": "release"}) == 204
    finally:
        server, D._server = D._server, None
        if server:
            server.shutdown()
            server.server_close()


def test_pause_and_kaia_mix_release_an_active_live_jog_bend(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda k, d: 0 if k == "dj_dashboard_port" else d)
    src = session.source
    base = D.serve()

    def post(path, payload):
        request = urllib.request.Request(
            base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    try:
        assert post("bend", {"slot": 1, "action": "set", "rate": 1.04}) == 204
        assert src.current.bend_active
        assert post("pause", {"slot": 1}) == 204
        assert src.current.bend["target"] == pytest.approx(1.0)
        assert 1 in src.paused

        assert post("play", {"slot": 1}) == 204
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
            src.read()
        assert not src.current.bend_active
        assert post("bend", {"slot": 1, "action": "set", "rate": 0.96}) == 204
        assert src.current.bend_active
        assert post("reset", {}) == 204
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
            src.read()
        assert not src.current.bend_active
        assert not src.paused
    finally:
        server, D._server = D._server, None
        if server:
            server.shutdown()
            server.server_close()


def test_booth_elapsed_and_remaining_clocks_use_the_live_jog_rate():
    page = D.PAGE.read_text(encoding="utf-8")
    assert "const effectiveRate = ratio * (d && d.playback_rate ? d.playback_rate : (d && d.bend && d.bend.rate ? d.bend.rate : 1));" in page
    assert "fmt(pos / effectiveRate)" in page
    assert "const rem = d ? (d.length - pos) / effectiveRate : NaN;" in page



def test_persistent_pitch_http_control_keeps_program_and_new_pfl_decoder_aligned(session, monkeypatch):
    monkeypatch.setattr(D, "_cfg", lambda key, default=None: 0 if key == "dj_dashboard_port" else default)
    src = session.source
    base = D.serve()

    def post(path, payload):
        request = urllib.request.Request(
            base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    stream = None
    try:
        # Set the persistent ride before selecting PHONES. The newly created PFL
        # decoder must inherit the stable rate and catch up through its own ring.
        assert post("pitch", {"slot": 1, "rate": 1.06}) == 204
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 1):
            src.read()
        deck = src.current
        assert deck is not None and deck.pitch_rate == pytest.approx(1.06)
        assert src.set_headphones(1)
        head = src._headphones_deck
        assert head is not None
        assert head.pitch_rate == pytest.approx(1.06)
        assert head.playback_rate == pytest.approx(1.06)
        assert head.at() == pytest.approx(deck.at(), abs=2 / R.RATE)

        stream = src.attach_headphone_stream()
        assert stream is not None
        for _ in range(12):
            src.read()
            monitor = stream.get_nowait()
            assert monitor is not None and len(monitor) == R.FRAME_BYTES
        assert deck._source_samples == pytest.approx(head._source_samples, abs=R.FRAME_SAMPLES * 1.1)

        # A live fader movement updates both program and already-selected PFL.
        assert post("pitch", {"slot": 1, "rate": 1.03}) == 204
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 2):
            src.read()
        assert deck.pitch_rate == pytest.approx(1.03)
        assert head.pitch_rate == pytest.approx(1.03)
        state = D.snapshot(session)["decks"]["1"]
        assert state["pitch_control"]["target"] == pytest.approx(1.03)
        assert state["tempo"] == pytest.approx(123.6)
        assert state["pitch"] == pytest.approx(3.0)
        assert post("pitch", {"slot": 1, "rate": 1.081}) == 400
        assert post("pitch", {"slot": 1, "rate": True}) == 400
        assert post("pitch", {"slot": 1, "rate": float("nan")}) == 400
        assert post("pitch", {"slot": 2, "rate": 1.03}) == 409

        assert post("pitch", {"slot": 1, "rate": 1.0}) == 204
        for _ in range(R.PITCH_BEND_RAMP_FRAMES + 2):
            src.read()
        assert deck.pitch_rate == pytest.approx(1.0)
        assert head.pitch_rate == pytest.approx(1.0)
    finally:
        if stream is not None:
            src.detach_headphone_stream(stream)
        src.set_headphones(None)
        server, D._server = D._server, None
        if server:
            server.shutdown()
            server.server_close()
