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
        # Match the storage_context contract used by mutation paths such as
        # flag_nodes(); these snapshot-only tests otherwise lack a docstore.
        self.docstore = SimpleNamespace(docs={}, get_node=lambda _node_id: None)

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
    errors = []

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
    # The first writer is stopped inside storage_context.persist while still
    # holding the transaction lock. The second must not enter that function.
    assert not second_entered.wait(timeout=0.2)

    release_first.set()
    first.join(timeout=3)
    second.join(timeout=3)

    assert not first.is_alive() and not second.is_alive()
    assert errors == []
    assert call_count == 2
    assert (Path(harness.persist_dir) / "a" / "writer.txt").read_text() == "2"


def test_forced_persist_bounds_wait_for_the_transaction_lock(tmp_path):
    harness = _PersistenceHarness(tmp_path)
    harness.persist_needed = True

    class RefusingLock:
        def __init__(self):
            self.timeouts = []

        def acquire(self, timeout=None):
            self.timeouts.append(timeout)
            return False

        def release(self):
            raise AssertionError("a lock that was not acquired must not be released")

    refusing = RefusingLock()
    harness._get_persistence_transaction_lock = lambda: refusing

    assert harness.persist(force=True) is False
    assert refusing.timeouts == [5.0]
    assert harness.persist_needed is True
    assert harness.writes == []
    assert harness._data_lock.acquire(timeout=0.1), "data lock leaked after transaction timeout"
    harness._data_lock.release()


def test_failed_directory_swap_restores_the_last_good_index(tmp_path, monkeypatch):
    import os
    import pytest

    harness = _PersistenceHarness(tmp_path)
    index_dir = Path(harness.persist_dir) / "a"
    index_dir.mkdir()
    (index_dir / "snapshot.txt").write_text("last-good", encoding="utf-8")

    original_rename = os.rename
    temp_dir = Path(f"{index_dir}_tmp")
    failed = {"once": False}

    def fail_new_snapshot_once(source, destination):
        if Path(source) == temp_dir and Path(destination) == index_dir and not failed["once"]:
            failed["once"] = True
            raise OSError("injected temp-to-live rename failure")
        return original_rename(source, destination)

    monkeypatch.setattr("utils.core.kaia_rag_persistence.os.rename", fail_new_snapshot_once)

    with pytest.raises(OSError, match="injected temp-to-live"):
        harness._persist_index_atomic("a")

    assert (index_dir / "snapshot.txt").read_text(encoding="utf-8") == "last-good"
    assert not Path(f"{index_dir}_old").exists()
    # The failed staged copy may remain, but it must never replace the restored
    # live index. The next save removes this staging directory before writing.
    assert temp_dir.is_dir()


def test_partial_snapshot_batch_does_not_advance_the_manifest(tmp_path):
    harness = _PersistenceHarness(tmp_path)
    manifest_writes = []
    harness._save_indexed_files = lambda: manifest_writes.append("write") or True

    def fail_second_index(persist_dir):
        raise OSError("injected second-index failure")

    harness.indices["b"].storage_context.persist = fail_second_index

    result = harness._persist_updated_indices({"a", "b"})

    assert result == {"a"}
    assert manifest_writes == []
    assert harness._get_pending_index_persist_types() == {"a", "b"}
    assert (Path(harness.persist_dir) / "a" / "snapshot.txt").is_file()


def test_manifest_failure_keeps_the_whole_snapshot_batch_pending(tmp_path):
    harness = _PersistenceHarness(tmp_path)
    manifest_attempts = []
    harness._save_indexed_files = lambda: manifest_attempts.append("write") or False

    result = harness._persist_updated_indices({"a", "b"})

    assert result == set()
    assert manifest_attempts == ["write"]
    assert harness._get_pending_index_persist_types() == {"a", "b"}
    assert (Path(harness.persist_dir) / "a" / "snapshot.txt").is_file()
    assert (Path(harness.persist_dir) / "b" / "snapshot.txt").is_file()


def test_flag_nodes_waits_for_the_persistence_transaction(tmp_path):
    from types import SimpleNamespace

    harness = _PersistenceHarness(tmp_path)
    node = SimpleNamespace(metadata={})
    docstore = SimpleNamespace(
        docs={"node-1": node},
        get_node=lambda node_id: node if node_id == "node-1" else None,
    )
    harness.indices["a"].storage_context.docstore = docstore
    harness.persist = lambda force=False: True

    transaction_lock = harness._get_persistence_transaction_lock()
    transaction_lock.acquire()
    errors = []

    def flag():
        try:
            assert harness.flag_nodes(["node-1"], "reviewed") == 1
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=flag, name="flag-nodes")
    worker.start()
    try:
        # flag_nodes must wait for an in-flight snapshot transaction before it
        # mutates the docstore, even though it has already requested _data_lock.
        assert not node.metadata
        assert worker.is_alive()
    finally:
        transaction_lock.release()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert errors == []
    assert node.metadata["audit_flags"] == ["reviewed"]


def test_persistence_lock_serializes_independent_processes(tmp_path):
    """A maintenance process must not enter the same RAG directory transaction."""
    import subprocess
    import sys
    import textwrap
    from types import SimpleNamespace

    from utils.core.rag_persistence_lock import persistence_transaction_lock

    persist_dir = tmp_path / "rag_storage"
    parent_lock = persistence_transaction_lock(SimpleNamespace(persist_dir=str(persist_dir)))
    assert parent_lock.acquire(timeout=1.0)

    child_code = textwrap.dedent(
        """
        import sys
        from types import SimpleNamespace
        from utils.core.rag_persistence_lock import persistence_transaction_lock

        lock = persistence_transaction_lock(SimpleNamespace(persist_dir=sys.argv[1]))
        first = lock.acquire(timeout=0.2)
        print("unexpected" if first else "blocked", flush=True)
        if first:
            lock.release()
            raise SystemExit(2)
        if not lock.acquire(timeout=3.0):
            raise SystemExit(3)
        print("acquired", flush=True)
        lock.release()
        """
    )
    root = Path(__file__).resolve().parents[3]
    child = subprocess.Popen(
        [sys.executable, "-c", child_code, str(persist_dir)],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "blocked"
    finally:
        parent_lock.release()

    stdout, stderr = child.communicate(timeout=5.0)
    assert child.returncode == 0, stderr
    assert "acquired" in stdout


def test_distinct_rag_instances_share_the_same_persistence_lock(tmp_path):
    from types import SimpleNamespace
    from utils.core.rag_persistence_lock import persistence_transaction_lock

    first = persistence_transaction_lock(SimpleNamespace(persist_dir=str(tmp_path / "rag")))
    second = persistence_transaction_lock(SimpleNamespace(persist_dir=str(tmp_path / "rag" / ".")))

    assert first is second


def test_index_initialization_reloads_manifest_under_the_shared_transaction(tmp_path, monkeypatch):
    """A manifest read and the index-directory reads must share one lock."""
    from utils.core import kaia_rag_indexer as indexer_module

    class Guard:
        held = False

        def __enter__(self):
            assert not self.held
            self.held = True
            return self

        def __exit__(self, *_exc):
            self.held = False
            return False

    guard = Guard()
    manifest_reads = []

    class Harness(RAGIndexerMixin):
        def __init__(self):
            self.persist_dir = str(tmp_path)
            self._data_lock = threading.RLock()
            self.indices = {}
            self.bm25_cache = {}
            self.indexed_files = {}
            self._get_persistence_transaction_lock = lambda: guard

        def _load_indexed_files(self):
            assert guard.held, "manifest was read outside the snapshot transaction"
            manifest_reads.append(True)
            self.indexed_files = {}

        def _populate_indexed_files(self):
            return None

    for itype in ("persona", "user_profiles", "knowledge", "logs", "dreams"):
        folder = tmp_path / itype
        folder.mkdir()
        (folder / "marker").write_text(itype, encoding="utf-8")

    monkeypatch.setattr(indexer_module.StorageContext, "from_defaults", lambda **_kw: object())
    monkeypatch.setattr(indexer_module, "load_index_from_storage", lambda _ctx: object())

    harness = Harness()
    harness._initialize_indices()

    assert manifest_reads == [True]
    assert not guard.held
    assert set(harness.indices) == {"persona", "user_profiles", "knowledge", "logs", "dreams"}
