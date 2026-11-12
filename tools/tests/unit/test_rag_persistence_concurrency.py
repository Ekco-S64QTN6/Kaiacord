"""RAG snapshot directory swaps and manifest commits form one transaction."""
import threading
from pathlib import Path
from types import SimpleNamespace

from utils.core.kaia_rag_indexer import RAGIndexerMixin
from utils.core.kaia_rag_persistence import RAGPersistenceMixin


class _SnapshotStore:
    def __init__(self, name, writes):
        self.name = name
        self.writes = writes

    def persist(self, persist_dir):
        path = Path(persist_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "snapshot.txt").write_text(
            f"{self.name}:{threading.current_thread().name}", encoding="utf-8"
        )
        self.writes.append((threading.current_thread().name, self.name))


class _PersistenceHarness(RAGIndexerMixin, RAGPersistenceMixin):
    def __init__(self, root):
        self.persist_dir = str(root / "rag_storage")
        self.state_file = str(Path(self.persist_dir) / "file_manifest.json")
        Path(self.persist_dir).mkdir(parents=True)
        self.writes = []
        self.indices = {
            name: SimpleNamespace(storage_context=_SnapshotStore(name, self.writes))
            for name in ("a", "b")
        }
        self.bm25_cache = {}
        self.indexed_files = {}
        self._data_lock = threading.Lock()
        self.persist_needed = False


def test_refresh_batch_and_forced_persist_cannot_interleave(tmp_path):
    harness = _PersistenceHarness(tmp_path)
    batch_paused = threading.Event()
    release_batch = threading.Event()
    force_lock_attempted = threading.Event()
    force_snapshot_entered = threading.Event()
    errors = []
    results = {}

    original_persist_one = harness._persist_index_atomic
    original_get_lock = harness._get_persistence_transaction_lock
    first_batch_snapshot = {"done": False}

    def observe_lock_attempt():
        if threading.current_thread().name == "force":
            force_lock_attempted.set()
        return original_get_lock()

    harness._get_persistence_transaction_lock = observe_lock_attempt

    def pause_refresh_after_first_snapshot(itype):
        if threading.current_thread().name == "force":
            force_snapshot_entered.set()
        original_persist_one(itype)
        if threading.current_thread().name == "refresh" and not first_batch_snapshot["done"]:
            first_batch_snapshot["done"] = True
            batch_paused.set()
            if not release_batch.wait(timeout=4):
                raise AssertionError("test did not release refresh persistence batch")

    # Pause *between* per-index atomic swaps. The outer batch lock must remain
    # held while this function is paused, otherwise forced persistence can
    # write its snapshots between refresh's first and second index.
    harness._persist_index_atomic = pause_refresh_after_first_snapshot

    def run_refresh():
        try:
            results["refresh"] = harness._persist_updated_indices({"a", "b"})
        except Exception as exc:  # surfaced in the main test thread below
            errors.append(exc)

    def run_force():
        try:
            results["force"] = harness.persist(force=True)
        except Exception as exc:
            errors.append(exc)

    refresh = threading.Thread(target=run_refresh, name="refresh")
    refresh.start()
    assert batch_paused.wait(timeout=2), "refresh did not reach its first snapshot"

    force = threading.Thread(target=run_force, name="force")
    force.start()
    assert force_lock_attempted.wait(timeout=1)
    # The second writer has reached the shared lock acquisition. It must wait
    # for the whole refresh batch, not just the currently executing rename.
    assert not force_snapshot_entered.wait(timeout=0.2)

    release_batch.set()
    refresh.join(timeout=3)
    force.join(timeout=3)

    assert not refresh.is_alive() and not force.is_alive()
    assert errors == []
    assert results["refresh"] == {"a", "b"}
    assert results["force"] is True

    write_owners = [name for name, _itype in harness.writes]
    first_force = write_owners.index("force")
    assert all(name == "refresh" for name in write_owners[:first_force])
    assert all(name == "force" for name in write_owners[first_force:])
    assert (Path(harness.persist_dir) / "a" / "snapshot.txt").is_file()
    assert (Path(harness.persist_dir) / "b" / "snapshot.txt").is_file()
    assert Path(harness.state_file).is_file()


def test_two_writers_cannot_delete_each_others_shared_staging_directory(tmp_path):
    harness = _PersistenceHarness(tmp_path)
    first_entered = threading.Event()
    second_entered = threading.Event()
    release_first = threading.Event()
    call_lock = threading.Lock()
    call_count = 0
    second_lock_attempted = threading.Event()
    original_get_lock = harness._get_persistence_transaction_lock
    errors = []

    def observe_lock_attempt():
        if threading.current_thread().name == "second-writer":
            second_lock_attempted.set()
        return original_get_lock()

    harness._get_persistence_transaction_lock = observe_lock_attempt

    def blocking_persist(persist_dir):
        nonlocal call_count
        with call_lock:
            call_count += 1
            current = call_count
        path = Path(persist_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "writer.txt").write_text(str(current), encoding="utf-8")
        if current == 1:
            first_entered.set()
            if not release_first.wait(timeout=4):
                raise AssertionError("test did not release first writer")
        elif current == 2:
            second_entered.set()

    harness.indices["a"].storage_context.persist = blocking_persist

    def write():
        try:
            harness._persist_index_atomic("a")
        except Exception as exc:
            errors.append(exc)

    first = threading.Thread(target=write, name="first-writer")
    first.start()
    assert first_entered.wait(timeout=2)

    second = threading.Thread(target=write, name="second-writer")
    second.start()
    # The second thread signals immediately before requesting the shared lock.
    # It must block there until the first writer finishes staging and swapping.
    assert second_lock_attempted.wait(timeout=1)
    assert not second_entered.wait(timeout=0.2)

    release_first.set()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert call_count == 2
    assert (Path(harness.persist_dir) / "a" / "writer.txt").read_text() == "2"
