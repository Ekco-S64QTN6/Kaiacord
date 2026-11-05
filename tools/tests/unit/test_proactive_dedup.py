"""Regression tests for recent opener deduplication across trigger sources."""
import json
import time

from utils.core.kaia_proactive import (
    OPENER_DEDUPE_WINDOW_SECONDS,
    ProactiveEngine,
)


class _BotState:
    relationships = {}

    def save(self):
        pass


def _engine(tmp_path, monkeypatch):
    import utils.core.kaia_proactive as proactive

    path = tmp_path / "proactive_topics.json"
    monkeypatch.setattr(proactive, "DIVERSITY_LOG_PATH", str(path))
    engine = ProactiveEngine.__new__(ProactiveEngine)
    return engine, path


def test_same_opener_from_different_trigger_categories_is_suppressed(tmp_path, monkeypatch):
    engine, path = _engine(tmp_path, monkeypatch)
    now = time.time()
    path.write_text(json.dumps({"history": [{
        "timestamp": now - 60,
        "source": "conversation_followup",
        "channel_id": 123,
        "summary": "it's funny how often people assume a fondness for one thing means an automatic allegiance to everything around it.",
    }]}), encoding="utf-8")

    assert engine.has_recent_duplicate_opener(
        "It's funny how often people assume a fondness for one thing means an automatic allegiance to everything around it.",
        channel_id=123,
        now=now,
    )


def test_near_duplicate_opening_phrase_is_suppressed_but_new_opener_is_allowed(tmp_path, monkeypatch):
    engine, path = _engine(tmp_path, monkeypatch)
    now = time.time()
    path.write_text(json.dumps({"history": [{
        "timestamp": now - 30,
        "source": "conversation_followup",
        "channel_id": 123,
        "summary": "it's funny how often people assume a fondness for one thing means an automatic allegiance to everything around it.",
    }]}), encoding="utf-8")

    assert engine.has_recent_duplicate_opener(
        "it's funny how often people assume that a fondness for one thing means an automatic allegiance to everything around it.",
        123,
        now=now,
    )
    assert not engine.has_recent_duplicate_opener(
        "the strange part is how quickly a routine becomes invisible once everyone relies on it.",
        123,
        now=now,
    )


def test_old_or_other_channel_opener_does_not_suppress(tmp_path, monkeypatch):
    engine, path = _engine(tmp_path, monkeypatch)
    now = time.time()
    phrase = "it's funny how often people assume a fondness for one thing means an automatic allegiance to everything around it."
    path.write_text(json.dumps({"history": [{
        "timestamp": now - OPENER_DEDUPE_WINDOW_SECONDS - 1,
        "source": "conversation_followup",
        "channel_id": 123,
        "summary": phrase,
    }]}), encoding="utf-8")

    assert not engine.has_recent_duplicate_opener(phrase, 123, now=now)

    path.write_text(json.dumps({"history": [{
        "timestamp": now - 10,
        "source": "conversation_followup",
        "channel_id": 456,
        "summary": phrase,
    }]}), encoding="utf-8")
    assert not engine.has_recent_duplicate_opener(phrase, 123, now=now)


def test_record_sent_persists_channel_and_message_for_future_dedup(tmp_path, monkeypatch):
    engine, path = _engine(tmp_path, monkeypatch)
    from utils.core.kaia_proactive import ProactiveTrigger

    trigger = ProactiveTrigger(
        trigger_type="mood_reflection",
        channel_id=789,
        context="idle thought",
        source_category="mood_reflection",
    )
    engine.record_sent(_BotState(), trigger, "a distinct thought about the rain.")

    saved = json.loads(path.read_text(encoding="utf-8"))["history"]
    assert saved[-1]["channel_id"] == 789
    assert saved[-1]["summary"] == "a distinct thought about the rain."
