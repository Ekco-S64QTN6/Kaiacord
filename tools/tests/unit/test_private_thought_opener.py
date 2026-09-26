"""A dream or a passing thought about someone opens a conversation with them
— once a day at most, and only while they are around."""
import json
import time
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from utils.core.kaia_proactive import ProactiveEngine

NOW = 2_000_000.0
CH = 42


@pytest.fixture
def engine(tmp_path, monkeypatch):
    log = tmp_path / "mono.jsonl"
    log.write_text("\n".join(json.dumps(e) for e in [
        {"epoch": NOW - 5000, "thought": "i wonder if starkind ever finished that painting."},
        {"epoch": NOW - 90 * 3600, "thought": "old thought about starkind."},
        {"epoch": NOW - 2000, "thought": "the rain sounds like static tonight."},
    ]) + "\n")
    monkeypatch.setattr("utils.core.kaia_proactive.telemetry_path", lambda p: str(log))
    monkeypatch.chdir(tmp_path)                       # no dream files here
    e = ProactiveEngine()
    monkeypatch.setattr(e, "_load_diversity_log", lambda: [])
    monkeypatch.setattr(e, "was_content_broadcast", lambda cid: False)
    return e


def _state(*speakers_ago):
    turns = [{"role": "user", "content": f"{n}: hi", "timestamp": NOW - ago} for n, ago in speakers_ago]
    return NS(channel_memory={CH: turns}, channel_last_activity={CH: NOW - 10})


def test_a_thought_about_someone_present_opens_with_them(engine):
    with patch("utils.core.kaia_proactive.time.time", return_value=NOW):
        got = engine._get_private_thought(_state(("Starkind", 600)))
    context, category, cid, person = got
    assert person == "Starkind" and category == "private_thought"
    assert "finished that painting" in context and cid.startswith("private:starkind:")


def test_nobody_is_approached_who_is_not_around(engine):
    with patch("utils.core.kaia_proactive.time.time", return_value=NOW):
        assert engine._get_private_thought(_state(("Starkind", 5 * 3600))) is None
        assert engine._get_private_thought(_state(("Ekco", 600))) is None


def test_once_a_day_per_person(engine, monkeypatch):
    monkeypatch.setattr(engine, "_load_diversity_log",
                        lambda: [{"content_id": "private:starkind:abc", "timestamp": NOW - 3600}])
    with patch("utils.core.kaia_proactive.time.time", return_value=NOW):
        assert engine._get_private_thought(_state(("Starkind", 600))) is None
