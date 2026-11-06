"""Concurrency and bounded-rotation regressions for the shared growth ledger."""
from concurrent.futures import ThreadPoolExecutor
import json

from utils.core.growth_log import append_growth_event


def _read_events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_concurrent_growth_log_appends_preserve_every_event(tmp_path):
    path = tmp_path / "memory" / "growth_log.jsonl"
    events = [{"event_id": i, "type": "concurrent_test"} for i in range(120)]

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(
            lambda event: append_growth_event(
                event, path, max_bytes=10_000_000, max_entries=1_000
            ),
            events,
        ))

    saved = _read_events(path)
    assert len(saved) == len(events)
    assert {row["event_id"] for row in saved} == set(range(len(events)))
    assert all(row["ts"] > 0 for row in saved)


def test_concurrent_growth_log_rotation_keeps_complete_unique_tail(tmp_path):
    path = tmp_path / "memory" / "growth_log.jsonl"
    events = [{"event_id": i, "type": "rotating_test"} for i in range(120)]

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(
            lambda event: append_growth_event(
                event, path, max_bytes=1, max_entries=17
            ),
            events,
        ))

    saved = _read_events(path)
    ids = [row["event_id"] for row in saved]
    assert len(saved) == 17
    assert len(ids) == len(set(ids))
    assert set(ids).issubset(set(range(len(events))))
    assert all(row["type"] == "rotating_test" for row in saved)


def test_growth_log_rotation_preserves_newest_complete_entries(tmp_path):
    path = tmp_path / "memory" / "growth_log.jsonl"
    for i in range(8):
        append_growth_event(
            {"event_id": i}, path, max_bytes=1, max_entries=3
        )

    assert [row["event_id"] for row in _read_events(path)] == [5, 6, 7]
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_dream_engine_resolves_growth_log_through_telemetry_path(monkeypatch):
    from utils.core.kaia_dream import DreamEngine

    monkeypatch.setenv("KAIACORD_TELEMETRY_SUFFIX", ".probe")
    engine = DreamEngine.__new__(DreamEngine)
    assert str(engine._growth_log_path()) == "memory/growth_log.probe.jsonl"

def test_entry_count_only_rotation_matches_milestone_writer_policy(tmp_path):
    path = tmp_path / "memory" / "growth_log.jsonl"
    for i in range(5):
        append_growth_event({"event_id": i}, path, max_bytes=None, max_entries=2)

    assert [row["event_id"] for row in _read_events(path)] == [3, 4]
