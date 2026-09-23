"""beliefs.json has two writers; neither may put back a stale copy."""
import json

import pytest

from utils.core import beliefs_store


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "beliefs.json"
    path.write_text(json.dumps([{"topic": "open source", "position": "good", "confidence": 0.8}]))
    monkeypatch.setattr(beliefs_store, "BELIEFS_PATH", path)
    return path


def test_a_chat_turn_does_not_undo_a_dream(store):
    """The turn read the file, the dream wrote a new belief, the turn wrote its
    copy back — and the new belief was gone."""
    seen_by_turn = beliefs_store.load()                     # the turn reads
    beliefs_store.update(lambda bs: bs.append(               # the dream writes
        {"topic": "ai labs", "position": "overpromise", "confidence": 0.7}))
    beliefs_store.bump_access([b["topic"] for b in seen_by_turn])   # the turn counts

    topics = {b["topic"]: b for b in beliefs_store.load()}
    assert "ai labs" in topics, "the chat turn wrote a stale copy over the dream"
    assert topics["open source"]["access_count"] == 1


def test_the_dream_engine_writes_through_the_store(store):
    from utils.core.kaia_dream import DreamEngine
    engine = DreamEngine.__new__(DreamEngine)
    engine._log_growth_event = lambda event: None
    engine._update_beliefs({"topic": "Open Source", "position": "complicated", "confidence": 0.6})
    engine._update_beliefs({"topic": "cron jobs", "position": "fragile", "confidence": 0.5})
    by_topic = {b["topic"]: b for b in beliefs_store.load()}
    assert by_topic["open source"]["position"] == "complicated"
    assert by_topic["cron jobs"]["position"] == "fragile"


def test_a_failing_change_writes_nothing(store):
    before = store.read_text()
    with pytest.raises(RuntimeError):
        beliefs_store.update(lambda bs: (bs.clear(), (_ for _ in ()).throw(RuntimeError()))[1])
    assert store.read_text() == before
