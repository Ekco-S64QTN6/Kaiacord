"""An open thread is an idea she has wondered about on more than one day.
Wonderings about people are left out, and a thread is never an answer owed."""
import json

import pytest

from utils.core import open_threads as ot

DAY = 86400
NOW = 1_800_000_000.0


@pytest.fixture
def setup(tmp_path, monkeypatch):
    mono = tmp_path / "mono.jsonl"
    rows = [
        (NOW - 3 * DAY, "i wonder if anyone still remembers what the early internet felt like."),
        (NOW - 1 * DAY, "i wonder whether anyone remembers the early internet at all."),
        (NOW - 2 * DAY, "i wonder if starkind is subtly steering the internet conversation."),
        (NOW - 2 * DAY, "i wonder if starkind is subtly steering the internet conversation again."),
        (NOW - 1 * DAY, "i wonder why the tea went cold."),
    ]
    mono.write_text("\n".join(json.dumps({"epoch": t, "thought": x}) for t, x in rows) + "\n")
    kb = tmp_path / "knowledge_base"
    (kb / "user_logs" / "Starkind_519557167779676160").mkdir(parents=True)
    paths = {"memory/monologue_log.jsonl": str(mono), "memory/belief_arguments.jsonl": str(tmp_path / "none"),
             "memory/bot_state.json": str(tmp_path / "none")}
    monkeypatch.setattr(ot, "telemetry_path", lambda p: paths[p])
    monkeypatch.setattr(ot, "KB", kb)
    monkeypatch.setattr(ot, "_cache", (0.0, None))


def test_a_recurring_idea_is_a_thread_and_a_person_is_not(setup):
    ts = ot.threads(NOW)
    assert len(ts) == 1 and "early internet" in ts[0]["text"] and ts[0]["days"] == 2


def test_the_chat_line_is_not_an_obligation(setup):
    ot.threads(NOW)
    note = ot.note_for("does anyone even remember the early internet?")
    assert "STILL OPEN FOR YOU" in note and "not an answer you owe anyone" in note
    assert ot.note_for("what's for dinner") == ""


def test_a_tag_question_is_a_reaction_not_a_wondering():
    assert ot._TAG.search("the data breaches are a constant, aren't they?")
    assert not ot._TAG.search("what would it take to stop them?")
