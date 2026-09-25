"""She re-reads her own identity shifts when the talk touches them."""
import json

import pytest

from utils.core import growth_recall as g

SHIFTS = [
    "i'm finding myself less inclined to dissect the architecture of ai funding rounds.",
    "i've been re-reading notes on distributed consensus algorithms and raft elections.",
] + [f"i'm finding myself noticing systems, quietly, in way number {i}." for i in range(20)]


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "growth_log.jsonl"
    rows = [{"type": "identity_shift", "content": c, "ts": 1790065968.0 + i} for i, c in enumerate(SHIFTS)]
    rows.append({"type": "belief_revised", "topic": "flat earth theory",
                 "old_position": "a joke", "new_position": "performance art", "ts": 1787000000})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    monkeypatch.setattr(g, "GROWTH_LOG", str(path))
    monkeypatch.setattr(g, "_cache", {"mtime": None, "shifts": [], "revisions": [], "df": {}})
    monkeypatch.setattr(g, "_last_offered", {})
    return path


def test_a_shift_the_talk_touches_comes_back_with_its_date(log):
    note = g.identity_shift_for("do you still care about consensus algorithms like raft?", channel_id=1)
    assert "distributed consensus" in note and "September" in note


def test_words_every_shift_uses_match_nothing(log):
    assert g.identity_shift_for("i keep finding myself noticing systems", channel_id=2) == ""


def test_once_per_channel_per_cooldown(log):
    ask = "consensus algorithms and raft, still?"
    assert g.identity_shift_for(ask, channel_id=3)
    assert g.identity_shift_for(ask, channel_id=3) == ""
    assert g.identity_shift_for(ask, channel_id=4)


def test_a_revised_belief_in_play_is_found_anywhere_in_the_log(log):
    note = g.belief_revision_for(["flat earth theory: performance art"])
    assert "a joke" in note
    assert g.belief_revision_for(["earthworms: good for soil"]) == ""
