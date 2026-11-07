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



def test_opener_signature_does_not_truncate_at_common_abbreviations():
    from utils.core.kaia_proactive import _opener_signature

    signature = _opener_signature(
        "Dr. Smith asked e.g. whether A. B. agreed before the review."
    )
    assert signature.startswith("dr smith asked e g whether a b agreed")


def test_digest_with_same_preface_but_distinct_observation_is_not_suppressed():
    from utils.core.kaia_proactive import (
        _opener_signature,
        _opener_signatures_match,
    )

    previous = (
        "I have been thinking about this more than usual. "
        "The weather changed before the power failed."
    )
    candidate = (
        "I have been thinking about this more than usual. "
        "The network recovered after the maintenance window."
    )
    assert not _opener_signatures_match(
        _opener_signature(previous), _opener_signature(candidate)
    )


def test_legacy_trigger_without_source_category_is_supported_or_rejected_cleanly(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    engine, path = _engine(tmp_path, monkeypatch)
    trigger = SimpleNamespace(
        trigger_type="mood_reflection",
        channel_id=789,
        context="idle thought",
        target_user=None,
        content_id="",
    )

    engine.record_sent(_BotState(), trigger, "a legacy thought about the rain.")
    saved = json.loads(path.read_text(encoding="utf-8"))["history"]
    assert saved[-1]["source"] == "mood_reflection"
    assert saved[-1]["channel_id"] == 789


def test_sent_broadcast_is_recorded_even_if_bot_state_save_fails(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    engine, path = _engine(tmp_path, monkeypatch)

    class BrokenState:
        relationships = {}

        def save(self):
            raise OSError("simulated state disk failure")

    trigger = SimpleNamespace(
        trigger_type="mood_reflection",
        channel_id=789,
        content_id="",
        target_user=None,
    )
    engine.record_sent(BrokenState(), trigger, "this was delivered.")

    saved = json.loads(path.read_text(encoding="utf-8"))["history"]
    assert saved[-1]["summary"] == "this was delivered."
    assert saved[-1]["source"] == "mood_reflection"



def test_opener_deduplication_ignores_punctuation_only_changes(tmp_path, monkeypatch):
    engine, path = _engine(tmp_path, monkeypatch)
    now = time.time()
    path.write_text(json.dumps({"history": [{
        "timestamp": now - 30,
        "source": "conversation_followup",
        "channel_id": 123,
        "summary": "The station went quiet after the last train.",
    }]}), encoding="utf-8")

    # A period and an ellipsis produce the same lexical opening signature.
    assert engine.has_recent_duplicate_opener(
        "The station went quiet after the last train…",
        channel_id=123,
        now=now,
    )


def test_punctuation_variant_dedup_remains_channel_scoped(tmp_path, monkeypatch):
    from utils.core.kaia_proactive import _opener_signature

    engine, path = _engine(tmp_path, monkeypatch)
    now = time.time()
    previous = "The sky is turning an odd shade of green, and the birds have gone quiet…"
    candidate = "The sky is turning an odd shade of green, and the birds have gone quiet."

    assert _opener_signature(previous) == _opener_signature(candidate)
    path.write_text(json.dumps({"history": [{
        "timestamp": now - 15,
        "source": "conversation_followup",
        "channel_id": 123,
        "summary": previous,
    }]}), encoding="utf-8")

    assert engine.has_recent_duplicate_opener(candidate, channel_id=123, now=now)
    assert not engine.has_recent_duplicate_opener(candidate, channel_id=456, now=now)


def test_monologue_and_observation_posts_do_not_count_toward_opener_diversity(tmp_path, monkeypatch):
    """Only openers fill the diversity window; other sources' posts share the
    log for duplicate checks alone."""
    from utils.core.kaia_proactive import _is_broadcast_only

    engine, _ = _engine(tmp_path, monkeypatch)
    now = time.time()
    engine.record_broadcast_sent("a monologue thought", 1, "monologue", now=now)
    engine.record_broadcast_sent("an observation", 1, "observation", now=now)
    history = engine._load_diversity_log()
    assert all(_is_broadcast_only(h) for h in history)

    # A legacy entry written before the marker is recognised by its source.
    assert _is_broadcast_only({"source": "monologue"})
    assert not _is_broadcast_only({"source": "belief_musing"})

    openers = [h for h in history if not _is_broadcast_only(h)]
    assert engine._is_source_allowed("belief_musing", openers)
