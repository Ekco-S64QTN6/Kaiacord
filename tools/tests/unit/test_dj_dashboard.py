"""The DJ booth shows the mixer's own state and its one control is the real skip."""
import io
import json
import time
import types
import urllib.request

import numpy as np
import pytest

from utils.audio import dj_dashboard as D
from utils.audio import library
from utils.audio import records as R
from utils.audio.beatgrid import Grid

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
    first = R.Deck(rec("one"), 1.0, 120.0, tone(1000, 20.0))      # long enough not to plan its end yet
    first.grid = Grid(120.0, 0.0, 8.0)
    queue = [R.Next(rec("two"), 20.0, 0.0, Grid(120.0, 0.0, 8.0))]
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


def test_a_planned_blend_shows_on_both_decks_and_the_mixer(session):
    session.source.skip()
    deadline = time.time() + 5
    while session.source.plan is None and time.time() < deadline:
        time.sleep(0.01)
    snap = D.snapshot(session)
    assert snap["mix"]["kind"] == "blend" and snap["mix"]["out_slot"] == "1" and snap["mix"]["in_slot"] == "2"
    assert snap["decks"]["2"]["state"] in ("cued", "playing")
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
    session.request(other)
    deadline = time.time() + 3
    while (session.source._queued is None or session.source._queued.record.title != "asked") and time.time() < deadline:
        time.sleep(0.01)
    assert session.source._queued.record.title == "asked" and not session.requests
    listing = D.crate(session)
    assert listing["count"] == 1 and listing["genres"]["House"][0]["title"] == "asked"
