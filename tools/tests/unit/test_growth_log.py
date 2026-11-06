"""Concurrency and bounded-rotation regressions for the shared growth ledger."""
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing
from pathlib import Path
import sys

import pytest

from utils.core import growth_log
from utils.core.growth_log import append_growth_event


def _append_growth_log_batch(path, first_id, count, barrier):
    """Worker process used to exercise the ledger's actual interprocess flock."""
    barrier.wait(timeout=15)
    for event_id in range(first_id, first_id + count):
        append_growth_event(
            {"event_id": event_id, "type": "interprocess_test"},
            path,
            max_bytes=1,
            max_entries=180,
        )


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



def test_new_growth_log_entry_fsyncs_its_parent_directory(tmp_path, monkeypatch):
    path = tmp_path / "memory" / "growth_log.jsonl"
    synced = []
    monkeypatch.setattr(growth_log, "fsync_directory", lambda directory: synced.append(Path(directory)))

    append_growth_event({"event_id": 1}, path)
    append_growth_event({"event_id": 2}, path)

    assert synced == [path.parent]


def test_growth_log_file_fsync_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    path = tmp_path / "memory" / "growth_log.jsonl"
    # Keep directory-creation fsync out of this fault injection: the failure
    # under test is specifically the sync of the newly appended file.
    path.parent.mkdir()

    def fail_fsync(_fd):
        raise OSError("simulated growth-log fsync failure")

    monkeypatch.setattr(growth_log.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="growth-log fsync"):
        append_growth_event({"event_id": 1}, path)

    # The append may be visible in cache, but the helper must not claim it was
    # durably recorded after the filesystem reported a sync failure.
    assert _read_events(path)[0]["event_id"] == 1



@pytest.mark.skipif(sys.platform != "linux", reason="Linux flock semantics are required")
def test_interprocess_growth_log_append_and_rotation_preserve_the_retained_tail(tmp_path):
    """Independent processes must serialize append plus rotation through sidecar flock."""
    path = tmp_path / "memory" / "growth_log.jsonl"
    path.parent.mkdir()

    context = multiprocessing.get_context("fork")
    worker_count = 6
    events_per_worker = 50
    retained_entries = 180
    barrier = context.Barrier(worker_count)
    processes = [
        context.Process(
            target=_append_growth_log_batch,
            args=(
                str(path),
                worker * events_per_worker,
                events_per_worker,
                barrier,
            ),
        )
        for worker in range(worker_count)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)

    still_running = [process for process in processes if process.is_alive()]
    for process in still_running:
        process.terminate()
        process.join(timeout=2)

    assert not still_running, "a growth-log writer process hung"
    assert [process.exitcode for process in processes] == [0] * worker_count

    saved = _read_events(path)
    ids = [row["event_id"] for row in saved]
    assert len(saved) == retained_entries
    assert len(ids) == len(set(ids))
    assert set(ids).issubset(set(range(worker_count * events_per_worker)))
    assert all(row["type"] == "interprocess_test" for row in saved)
