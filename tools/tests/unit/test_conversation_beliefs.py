"""DECISIONS K9: a recurring, argued point can move a belief; one message can't."""
import json
import time

import pytest

from utils.core import beliefs_store
from utils.core import conversation_beliefs as cb

BELIEFS = [{"topic": "remote work", "position": "Offices are overrated.", "confidence": 0.8,
            "source": "dream", "aliases": ["working from home"]}]
ARG = "remote work kills mentoring because juniors never overhear how seniors debug things"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(cb, "ARGUMENTS", str(tmp_path / "args.jsonl"))
    monkeypatch.setattr(cb, "REVIEWED", str(tmp_path / "reviewed.json"))
    monkeypatch.setattr(beliefs_store, "BELIEFS_PATH", tmp_path / "beliefs.json")
    (tmp_path / "beliefs.json").write_text(json.dumps(BELIEFS))
    return tmp_path


def test_only_an_argued_remark_on_a_belief_topic_is_noted(store):
    assert cb.note_argument(1, "Ekco", ARG, BELIEFS) == ["remote work"]
    assert cb.note_argument(1, "Ekco", "remote work is bad, simple as that, i just hate it lol", BELIEFS) == []
    assert cb.note_argument(1, "Ekco", "because the weather is nice we went to the beach today", BELIEFS) == []


def test_one_day_of_arguing_is_not_enough(store):
    cb.note_argument(1, "Ekco", ARG, BELIEFS)
    cb.note_argument(2, "Starkind", ARG + " honestly", BELIEFS)
    assert cb.due_topics() == {}


def test_arguments_on_two_days_are_reviewed_once(store):
    now = time.time()
    with open(cb.ARGUMENTS, "w") as f:
        for ago in (3, 1):
            f.write(json.dumps({"ts": now - ago * 86400, "user_id": "1", "user_name": "Ekco",
                                "topic": "remote work", "text": ARG}) + "\n")
    assert list(cb.due_topics(now)) == ["remote work"]


def test_a_verdict_moves_confidence_within_bounds(store):
    event = cb.apply_verdict("remote work", {"verdict": "weaker", "why": "mentoring point"})
    b = beliefs_store.load()[0]
    assert b["confidence"] == 0.65 and b["source"] == "conversation"
    assert event["type"] == "belief_weakened"
    event = cb.apply_verdict("remote work", {"verdict": "revise", "position": "Offices matter for juniors."})
    b = beliefs_store.load()[0]
    assert b["position"] == "Offices matter for juniors." and b["confidence"] == 0.6
    assert event["old_position"] == "Offices are overrated."
    assert cb.apply_verdict("remote work", {"verdict": "keep"}) is None
