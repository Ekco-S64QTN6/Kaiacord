"""Durable appends to per-user transcripts retain the shared append lock."""

import fcntl
import os
import stat
from pathlib import Path

import pytest

from utils.core import kaia_rag_persistence as persistence
from utils.core.kaia_rag_persistence import RAGPersistenceMixin


_HEADER = '---\nsummary: ""\nkeywords: []\ndocument_type: Transcript\n---\n\n'


def _args(path, text="turn from pytest\n\n"):
    return {
        "path": str(path),
        "is_new": True,
        "header": _HEADER,
        "user_name": "pytest",
        "text": text,
    }


def _observe_syncs(monkeypatch):
    """Record file/directory fsyncs and whether the sidecar flock is held."""
    events = []
    state = {"lock_held": False}
    real_flock = persistence.fcntl.flock
    real_fsync = persistence.os.fsync

    def tracked_flock(descriptor, operation):
        result = real_flock(descriptor, operation)
        if operation & fcntl.LOCK_UN:
            state["lock_held"] = False
        elif operation & fcntl.LOCK_EX:
            state["lock_held"] = True
        return result

    def tracked_fsync(descriptor):
        mode = os.fstat(descriptor).st_mode
        if stat.S_ISREG(mode):
            kind = "file"
        elif stat.S_ISDIR(mode):
            kind = "directory"
        else:
            kind = "other"
        events.append((kind, state["lock_held"]))
        return real_fsync(descriptor)

    monkeypatch.setattr(persistence.fcntl, "flock", tracked_flock)
    monkeypatch.setattr(persistence.os, "fsync", tracked_fsync)
    return events, state


def test_stale_new_file_metadata_writes_front_matter_once(tmp_path):
    path = tmp_path / "interactions_20261023.md"
    stale_args = _args(
        path,
        text="[2026-10-23 12:00:00] Alice: first message\n\n",
    )

    # Simulate two writers that both prepared arguments before the first
    # append created the file. Both carry the stale is_new=True snapshot.
    assert RAGPersistenceMixin._write_interaction_to_disk(None, stale_args)
    second = dict(
        stale_args,
        text="[2026-10-23 12:00:01] Alice: second message\n\n",
    )
    assert RAGPersistenceMixin._write_interaction_to_disk(None, second)

    content = path.read_text(encoding="utf-8")
    assert content.count("document_type: Transcript") == 1
    assert "Alice: first message" in content
    assert "Alice: second message" in content


def test_existing_transcript_append_fsyncs_file_while_lock_is_held(tmp_path, monkeypatch):
    path = tmp_path / "interactions_existing.md"
    path.write_text("existing transcript\n", encoding="utf-8")
    events, state = _observe_syncs(monkeypatch)

    assert RAGPersistenceMixin._write_interaction_to_disk(
        None, _args(path, text="new turn\n\n")
    )

    assert events == [("file", True), ("directory", True)]
    assert state["lock_held"] is False
    assert "new turn" in path.read_text(encoding="utf-8")


def test_first_transcript_append_fsyncs_file_then_parent_directory_under_lock(
    tmp_path, monkeypatch
):
    path = tmp_path / "interactions_new.md"
    events, state = _observe_syncs(monkeypatch)

    assert RAGPersistenceMixin._write_interaction_to_disk(None, _args(path))

    assert events == [("file", True), ("directory", True)]
    assert state["lock_held"] is False
    assert path.is_file()
    assert "document_type: Transcript" in path.read_text(encoding="utf-8")


def test_user_log_directory_creation_syncs_each_new_parent(tmp_path, monkeypatch):
    from utils.core import atomic_write

    root = tmp_path / "corpus"
    synced = []
    real_sync_directory = atomic_write.fsync_directory

    def observe_directory_sync(directory):
        synced.append(Path(directory))
        return real_sync_directory(directory)

    monkeypatch.setattr(persistence, "corpus_dir", lambda _knowledge_base: str(root))
    monkeypatch.setattr(atomic_write, "fsync_directory", observe_directory_sync)

    harness = RAGPersistenceMixin.__new__(RAGPersistenceMixin)
    harness.knowledge_base_dir = str(tmp_path / "knowledge_base")
    harness._existing_dir_for_id = lambda _user_id: None

    path = Path(RAGPersistenceMixin._resolve_log_path(harness, "42", "Pytest", 42))

    assert path.parent.is_dir()
    assert synced == [tmp_path, root, root / "user_logs"]


@pytest.mark.parametrize("failure_stage", ["file", "directory"])
def test_sync_failure_returns_false_and_releases_append_lock(
    tmp_path, monkeypatch, failure_stage
):
    from utils.core import atomic_write

    path = tmp_path / f"interactions_{failure_stage}_failure.md"
    events, state = _observe_syncs(monkeypatch)
    errors = []
    monkeypatch.setattr(persistence, "log_error", errors.append)

    if failure_stage == "file":
        def fail_file_sync(_descriptor):
            raise OSError("injected transcript fsync failure")

        monkeypatch.setattr(persistence.os, "fsync", fail_file_sync)
    else:
        def fail_directory_sync(_directory):
            raise OSError("injected directory fsync failure")

        monkeypatch.setattr(atomic_write, "fsync_directory", fail_directory_sync)

    assert not RAGPersistenceMixin._write_interaction_to_disk(None, _args(path))
    assert errors and "Error logging user interaction to disk" in errors[-1]
    assert state["lock_held"] is False

    # The failed writer must not strand the stable sidecar lock.
    lock_path = path.with_name(f".{path.name}.append.lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
