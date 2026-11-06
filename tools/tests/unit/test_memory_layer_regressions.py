"""Regressions for the memory-layer fixes (observation digest, eviction policies).

Covers the four defects found auditing memory/:
  1. The observation digest fired on a clock, not on new material, so two
     consecutive entries could summarise essentially the same window.
  2. `raw_message_count` reported the running daily total rather than what the
     entry actually covered (hence 81 then 83).
  3. Belief eviction sorted on confidence alone, dropping ten fresh beliefs at
     a time in favour of stale high-confidence ones.
  4. Relationship-event pruning multiplied `timestamp / time.time()`, a term
     that is ~0.999 for every event, so recency never participated.
"""
import json
import time

import pytest

from utils.core.background_tasks import CoreTaskManager
from utils.core.relationship_manager import RelationshipEvent


LOG = """---
summary: ""
---

[2026-09-06 10:00:00] Ekco: first passive line

[2026-09-06 10:01:00] Starkind: second passive line
[2026-09-06 10:01:30] Ekco: same block, still passive

[2026-09-06 10:02:00] Ekco: addressed to her
[2026-09-06 10:02:10] Kaia: an active reply, so this block is not overheard
"""


def test_parse_passive_turns_skips_blocks_kaia_took_part_in():
    turns = CoreTaskManager._parse_passive_turns(LOG)
    assert [t[0] for t in turns] == [
        "2026-09-06 10:00:00",
        "2026-09-06 10:01:00",
        "2026-09-06 10:01:30",
    ]
    assert turns[0][1] == "Ekco: first passive line"
    assert all("Kaia" not in text for _, text in turns)


def test_parse_passive_turns_ignores_unstamped_lines():
    assert CoreTaskManager._parse_passive_turns("no timestamp here\n\njust prose") == []


def test_watermark_reads_newest_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "observation_digest.json").write_text(json.dumps([
        {"timestamp": 1.0, "watermark": "2026-09-06 08:00:00"},
        {"timestamp": 2.0, "watermark": "2026-09-06 11:56:38"},
    ]), encoding="utf-8")
    assert CoreTaskManager._load_digest_watermark() == "2026-09-06 11:56:38"


def test_watermark_absent_is_empty_not_an_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CoreTaskManager._load_digest_watermark() == ""


def test_watermark_survives_corrupt_digest_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "observation_digest.json").write_text("{not json", encoding="utf-8")
    assert CoreTaskManager._load_digest_watermark() == ""


def test_watermark_gates_out_already_digested_turns():
    """The 81 -> 83 case: a second run with 2 new turns must not re-digest."""
    turns = CoreTaskManager._parse_passive_turns(LOG)
    watermark = "2026-09-06 10:01:00"
    fresh = [t for t in turns if t[0] > watermark]
    assert len(fresh) == 1
    assert fresh[0][0] == "2026-09-06 10:01:30"
    assert len(fresh) < CoreTaskManager.OBS_DIGEST_MIN_NEW_TURNS


# ── Belief eviction ──────────────────────────────────────────────────

def _belief(topic, conf, age_days, accesses=0):
    return {
        "topic": topic,
        "position": "p",
        "confidence": conf,
        "last_updated": time.time() - age_days * 86400,
        "access_count": accesses,
    }


def _evict_once(beliefs, keep=""):
    from utils.core import beliefs_store
    out = list(beliefs)
    padding = [_belief(f"strong {i}", 0.95, age_days=8, accesses=50) for i in range(100)]
    out += padding
    beliefs_store.evict_weakest(out, keep_topic=keep)
    return [b for b in out if b not in padding]


def test_eviction_keeps_fresh_belief_over_stale_one():
    fresh = _belief("just formed", 0.70, age_days=0.5)
    stale = _belief("months old, never recalled", 0.72, age_days=60)
    survivors = _evict_once([fresh, stale])
    assert fresh in survivors and stale not in survivors


def test_eviction_keeps_frequently_recalled_belief():
    used = _belief("recalled often", 0.75, age_days=8, accesses=8)
    idle = _belief("never recalled", 0.80, age_days=8, accesses=0)
    survivors = _evict_once([used, idle])
    assert used in survivors and idle not in survivors


def test_eviction_removes_exactly_one():
    from utils.core import beliefs_store
    beliefs = [_belief(f"t{i}", 0.5 + i / 100, age_days=i) for i in range(101)]
    evicted = beliefs_store.evict_weakest(beliefs)
    assert evicted is not None and len(beliefs) == 100


def test_a_new_belief_does_not_evict_itself_from_a_full_store():
    """A dream's belief starts at 0.6 and every older one scored 0.7 or better, so
    with the store at 100 the new one was removed as soon as it was added, and
    "New Belief Formed" was logged for a belief that was no longer there."""
    from utils.core import beliefs_store
    beliefs = [_belief(f"old {i}", 0.9, age_days=30 + i, accesses=5) for i in range(100)]
    new = _belief("just formed", 0.6, age_days=0)
    beliefs.append(new)
    evicted = beliefs_store.evict_weakest(beliefs, keep_topic="just formed")
    assert evicted is not None and evicted["topic"].startswith("old")
    assert new in beliefs and len(beliefs) == 100


def test_a_nights_new_beliefs_survive_the_next_night():
    from utils.core import beliefs_store
    beliefs = [_belief(f"old {i}", 0.9, age_days=30, accesses=5) for i in range(90)]
    last_night = [_belief(f"last night {i}", 0.6, age_days=1) for i in range(10)]
    beliefs += last_night
    for i in range(10):
        topic = f"tonight {i}"
        beliefs.append(_belief(topic, 0.6, age_days=0))
        beliefs_store.evict_weakest(beliefs, keep_topic=topic)
    assert all(b in beliefs for b in last_night)
    assert sum(b["topic"].startswith("tonight") for b in beliefs) == 10


def test_a_view_held_once_fades_once_its_protection_ends():
    from utils.core import beliefs_store
    beliefs = [_belief(f"old {i}", 0.9, age_days=30, accesses=5) for i in range(100)]
    faded = _belief("held once, a fortnight ago", 0.6, age_days=14)
    beliefs.append(faded)
    assert beliefs_store.evict_weakest(beliefs) is faded


# ── Relationship event pruning ───────────────────────────────────────

def test_save_event_prunes_by_real_recency(tmp_path, monkeypatch):
    import utils.core.relationship_manager as rm
    monkeypatch.setattr(rm, "RELATIONSHIPS_DIR", str(tmp_path))

    now = time.time()
    # Equal weight throughout: under the old key every event scored the same
    # and stable ordering kept the OLDEST 80. Recency must now decide.
    for i in range(101):
        rm.save_event("u1", RelationshipEvent(
            timestamp=now - (101 - i) * 5 * 86400,
            event_type="positive",
            summary=f"event {i}",
            emotional_weight=0.5,
        ))

    kept = rm.load_events("u1")
    assert len(kept) == 80
    summaries = {e.summary for e in kept}
    assert "event 100" in summaries, "newest event must survive pruning"
    assert "event 0" not in summaries, "oldest event must be pruned first"
    assert [e.timestamp for e in kept] == sorted(e.timestamp for e in kept), \
        "events are persisted in chronological order"


def test_save_event_still_favours_high_emotional_weight(tmp_path, monkeypatch):
    import utils.core.relationship_manager as rm
    monkeypatch.setattr(rm, "RELATIONSHIPS_DIR", str(tmp_path))

    now = time.time()
    rm.save_event("u2", RelationshipEvent(
        timestamp=now - 200 * 86400, event_type="milestone",
        summary="old but pivotal", emotional_weight=1.0,
    ))
    for i in range(100):
        rm.save_event("u2", RelationshipEvent(
            timestamp=now - i * 3600, event_type="neutral",
            summary=f"filler {i}", emotional_weight=0.05,
        ))

    assert "old but pivotal" in {e.summary for e in rm.load_events("u2")}


# ── Dream name resolution ────────────────────────────────────────────

@pytest.mark.parametrize("name,expected_hit", [
    ("Ekco", True),
    ("ekco", True),
    ("Tenno Henka", True),
    ("Henka", True),      # whole word of a two-word display name
    ("He", False),        # pronoun; the old substring match resolved this
    ("Case", False),      # a character out of an ingested novel
    ("UnknownStarkind", False),
    ("", False),
    (None, False),
])
def test_resolve_user_id_is_strict(monkeypatch, name, expected_hit):
    import utils.core.relationship_manager as rm

    class FakeState:
        relationships = {
            "177011971818782721": {"display_name": "Ekco"},
            "919782120308752425": {"display_name": "Tenno Henka"},
            "519557167779676160": {"display_name": "Starkind"},
        }

    import utils.infrastructure.system.bot_state as bs
    monkeypatch.setattr(bs, "bot_state", FakeState)
    assert (rm.resolve_user_id(name) is not None) is expected_hit


# ── Dream continuity filesystem isolation ─────────────────────────────

def test_dream_continuity_load_runs_off_event_loop_thread(tmp_path):
    import asyncio
    import threading
    from utils.core.kaia_dream import DreamEngine

    engine = DreamEngine.__new__(DreamEngine)
    engine.continuity_file = tmp_path / "private" / "kaia_continuity.md"
    engine.continuity_file.parent.mkdir(parents=True)
    engine.continuity_file.write_text("recent reflection", encoding="utf-8")

    event_loop_thread = threading.get_ident()
    worker_threads = []
    original = engine._load_continuity_sync

    def tracked_load():
        worker_threads.append(threading.get_ident())
        return original()

    engine._load_continuity_sync = tracked_load
    assert asyncio.run(engine._load_continuity()) == "recent reflection"
    assert worker_threads and worker_threads[0] != event_loop_thread


def test_dream_continuity_update_runs_off_event_loop_thread_and_is_atomic(tmp_path):
    import asyncio
    import threading
    from utils.core.kaia_dream import DreamEngine

    engine = DreamEngine.__new__(DreamEngine)
    engine.continuity_file = tmp_path / "private" / "kaia_continuity.md"

    event_loop_thread = threading.get_ident()
    worker_threads = []
    original = engine._update_continuity_sync

    def tracked_update(new_reflection, source_label):
        worker_threads.append(threading.get_ident())
        return original(new_reflection, source_label)

    engine._update_continuity_sync = tracked_update
    asyncio.run(engine._update_continuity("a new thought", "source.md"))

    assert worker_threads and worker_threads[0] != event_loop_thread
    saved = engine.continuity_file.read_text(encoding="utf-8")
    assert "a new thought" in saved
    assert "source.md" in saved
    assert not list(engine.continuity_file.parent.glob(".*.tmp"))


def test_dream_continuity_async_callers_await_the_io_helpers():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "utils/core/kaia_dream.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {
        id(child): parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"_load_continuity", "_update_continuity"}:
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "self":
            continue
        parent = parents.get(id(node))
        assert isinstance(parent, ast.Await) and parent.value is node, (
            f"{node.func.attr} must be awaited at line {node.lineno}"
        )
