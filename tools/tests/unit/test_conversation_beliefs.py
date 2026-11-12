"""A recurring, argued point can move a belief; one message can't."""
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


def test_an_ordinary_word_alias_alone_is_not_the_belief():
    """'knowledge' is an alias of 'expertise'; a line about loading a truck is not an argument about it."""
    from utils.core.conversation_beliefs import _mentions
    belief = {"topic": "expertise", "aliases": ["knowledge", "skill", "domain mastery"]}
    assert not _mentions(belief, "i was gonna send a sunset but it's a crap one, plus common knowledge says so")
    assert _mentions(belief, "expertise is overrated because anyone can learn")
    assert _mentions(belief, "domain mastery takes years, since practice compounds")
    assert _mentions(belief, "knowledge without skill is useless, because you can't apply it")


@pytest.mark.parametrize("verdict", [
    {},
    [],
    {"verdict": "agree"},
    {"verdict": "revise"},
    {"verdict": "revise", "position": "short"},
])
def test_invalid_model_verdicts_are_rejected(verdict):
    with pytest.raises(ValueError):
        cb.validate_verdict(verdict)


def test_apply_verdict_does_not_treat_missing_schema_as_keep(store):
    with pytest.raises(ValueError):
        cb.apply_verdict("remote work", {})


def _make_due_review(store):
    now = time.time()
    with open(cb.ARGUMENTS, "w", encoding="utf-8") as f:
        for ago in (3, 1):
            f.write(json.dumps({
                "ts": now - ago * 86400,
                "user_id": "1",
                "user_name": "Ekco",
                "topic": "remote work",
                "text": ARG,
            }) + "\n")


def _fake_review_context(content):
    from types import SimpleNamespace

    class FakeClient:
        async def chat(self, **_kwargs):
            return {"message": {"content": content}}

    return SimpleNamespace(
        config=SimpleNamespace(chat_model="test-model"),
        ollama_client=FakeClient(),
    )


def test_schema_invalid_json_does_not_consume_the_fourteen_day_review_window(store, monkeypatch):
    import asyncio
    from utils.infrastructure.gpu import gpu_manager

    _make_due_review(store)

    async def run_guard(**kwargs):
        return await kwargs["coro"]

    monkeypatch.setattr(gpu_manager.gpu_memory_manager, "run_with_gpu_guard", run_guard)
    asyncio.run(cb.nightly_review(_fake_review_context("{}")))

    with open(cb.REVIEWED, encoding="utf-8") as f:
        reviewed = json.load(f)
    assert "remote work" not in reviewed
    assert list(cb.due_topics()) == ["remote work"], "malformed output must be eligible for retry"


def test_valid_keep_verdict_does_consume_the_review_window(store, monkeypatch):
    import asyncio
    from utils.infrastructure.gpu import gpu_manager

    _make_due_review(store)

    async def run_guard(**kwargs):
        return await kwargs["coro"]

    monkeypatch.setattr(gpu_manager.gpu_memory_manager, "run_with_gpu_guard", run_guard)
    asyncio.run(cb.nightly_review(_fake_review_context(
        '{"verdict":"keep","why":"the arguments do not overturn the current position"}'
    )))

    with open(cb.REVIEWED, encoding="utf-8") as f:
        reviewed = json.load(f)
    assert "remote work" in reviewed
    assert cb.due_topics() == {}
