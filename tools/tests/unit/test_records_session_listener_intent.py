"""One-shot request lifecycle and candidate steering in RecordsSession."""
import asyncio
import threading
import time
from types import SimpleNamespace

from utils.audio import records_intent
from utils.audio import records as R
from utils.audio import library
from utils.audio.beatgrid import Grid


def _profile(bass, section="groove_candidate"):
    phrase = SimpleNamespace(
        start=0.0, end=64.0, aligned=True, section=section,
        bass_db=bass, upper_db=-12.0, full_db=-12.0,
    )
    return SimpleNamespace(duration=64.0, phrases=(phrase,))


def _bare_session():
    session = R.RecordsSession.__new__(R.RecordsSession)
    current = library.Record("/music/current.mp3", "Current Artist", "Current", 120.0, "8A", "House")
    session._closing = False
    session.source = SimpleNamespace(
        current=SimpleNamespace(record=current),
        _queued=None, _picking=False, incoming=None, plan=None, _planning=False,
    )
    session.requests = ["/music/booth-picked.mp3"]
    session._listener_intent_lock = threading.Lock()
    session._listener_intent_sequence = 0
    session._listener_pick_generation = 0
    session._listener_intent_min_pick_generation = 1
    session._listener_intent = None
    session.last_listener_intent = None
    session._listener_profile_lock = threading.Lock()
    session._listener_profile_cache = {}
    return session, current


def test_musical_request_uses_a_separate_slot_from_booth_track_requests():
    session, _ = _bare_session()
    result = asyncio.run(session.request("more bass", "listener"))

    assert result.understood
    assert not result.queued_after_current
    assert "more bass" in result.reply
    assert session.requests == ["/music/booth-picked.mp3"]
    assert session._listener_intent.kind == "more_bass"
    assert session.last_listener_intent["status"] == "pending"


def test_latest_request_replaces_previous_and_explicitly_defers_behind_queued_pick():
    session, _ = _bare_session()
    first = asyncio.run(session.request("more bass", "one"))
    first_id = session._listener_intent.request_id
    session.source._queued = SimpleNamespace(record=SimpleNamespace(name="Already chosen"))
    second = asyncio.run(session.request("darker", "two"))

    assert first.understood and second.understood
    assert second.queued_after_current
    assert "following choice" in second.reply
    assert session._listener_intent.request_id != first_id
    assert session._listener_intent.kind == "darker"
    assert session.requests == ["/music/booth-picked.mp3"]


def test_only_the_matching_successfully_prepared_pick_consumes_the_intent():
    session, current = _bare_session()
    asyncio.run(session.request("more bass", "listener"))
    intent = session._listener_intent
    next_record = library.Record("/music/next.mp3", "Next Artist", "Next", 120.0, "8A", "House")
    nxt = R.Next(next_record, 180.0)
    nxt.listener_intent_id = intent.request_id
    nxt.listener_intent_score = 0.75
    nxt.listener_intent_reason = "relative low-end feature level changes in requested direction"

    session._listener_intent_selected(nxt)

    assert session._listener_intent is None
    assert session.last_listener_intent["status"] == "selected"
    assert session.last_listener_intent["record"] == "Next"
    assert session.last_listener_intent["score"] == 0.75





def test_request_during_an_in_progress_pick_applies_to_the_following_pick():
    session, _ = _bare_session()
    session.source._picking = True
    result = asyncio.run(session.request("more bass", "listener"))

    assert result.understood and result.queued_after_current
    # The pick worker enters _choose after _picking is set. Its generation is
    # skipped even if the command arrived just before that worker started.
    session._listener_pick_started()
    assert session._current_listener_intent() is None
    session._listener_pick_started()
    assert session._current_listener_intent() is session._listener_intent


def test_an_old_pick_cannot_consume_a_newer_listener_request():
    session, _ = _bare_session()
    asyncio.run(session.request("more bass", "listener"))
    old_id = session._listener_intent.request_id
    asyncio.run(session.request("brighter", "listener"))
    new_id = session._listener_intent.request_id

    old_pick = R.Next(library.Record("/music/old.mp3", "Artist", "Old", 120, "8A"), 120)
    old_pick.listener_intent_id = old_id
    session._listener_intent_selected(old_pick)

    assert session._listener_intent.request_id == new_id
    assert session._listener_intent.kind == "brighter"


def test_measured_partner_frontier_is_reordered_by_the_requested_feature(monkeypatch):
    from utils.audio import beatgrid, setlist

    session, current = _bare_session()
    strong = library.Record("/music/strong.mp3", "Beta", "Strong bass", 120.0, "8A", "House")
    weak = library.Record("/music/weak.mp3", "Gamma", "Light bass", 120.0, "8A", "House")
    edges = {
        strong.path: {"beats": 64, "back": 0, "cue": 0, "agree": 16, "bars": 16, "ratio": 1.0},
        weak.path: {"beats": 64, "back": 0, "cue": 0, "agree": 16, "bars": 16, "ratio": 1.0},
    }
    session.graph = {"edges": {current.path: edges}, "sets": []}
    session._by_path = {current.path: current, strong.path: strong, weak.path: weak}
    session.played = []
    session.crate = [current, weak, strong]
    session.set_list = None
    session._rng = __import__("random").Random(1)
    session.say = lambda *_args: None
    session._listener_profile_cache = {
        current.path: _profile(-18.0),
        strong.path: _profile(-2.0),
        weak.path: _profile(-22.0),
    }
    session._listener_pick_generation = 1
    session._listener_intent_min_pick_generation = 1
    session._listener_intent = records_intent.ListenerIntent(
        request_id=9, kind="more_bass", label="more bass",
        requested_by="listener", created_at=time.time(),
        expires_at=time.time() + 300,
    )

    monkeypatch.setattr(setlist, "partners", lambda _graph, _path: edges)
    monkeypatch.setattr(setlist, "family", lambda _record: "house")
    monkeypatch.setattr(setlist, "transition_rank",
                        lambda _a, candidate, *_args, **_kwargs: 0 if candidate.path == weak.path else 1)
    monkeypatch.setattr(R, "probe_seconds", lambda _path: 180.0)
    monkeypatch.setattr(R, "gain_db", lambda _path: 0.0)
    monkeypatch.setattr(R, "_envelope", lambda _path: None)
    monkeypatch.setattr(beatgrid, "ensure_ticks", lambda *_args: None)
    monkeypatch.setattr(beatgrid, "grid_for", lambda *_args: Grid(120.0, 0.0, 8.0))
    monkeypatch.setattr(beatgrid, "first_sound", lambda _path: 0.0)
    monkeypatch.setattr(beatgrid, "bass_entry", lambda *_args: None)

    deck = SimpleNamespace(record=current, grid=Grid(120.0, 0.0, 8.0), ratio=1.0)
    chosen = session._partner(deck)

    assert chosen is not None
    assert chosen.record.path == strong.path
    assert chosen.listener_intent_id == 9
    assert chosen.listener_intent_score is not None and chosen.listener_intent_score > 0.9
    # It is still a measured graph edge; the intent only changed ranking.
    assert chosen.source == "partner"
