"""An index save that dies partway leaves the last good copy in place."""
import os
import types

import pytest

from utils.core.kaia_rag_persistence import RAGPersistenceMixin


class _Store:
    def __init__(self, fail=False):
        self.fail = fail

    def persist(self, persist_dir):
        os.makedirs(persist_dir, exist_ok=True)
        with open(os.path.join(persist_dir, "docstore.json"), "w") as f:
            f.write('{"new": tru')                        # cut off mid-write
            if self.fail:
                raise OSError("killed mid-save")
        with open(os.path.join(persist_dir, "docstore.json"), "w") as f:
            f.write('{"new": true}')


def _rag(tmp_path, fail):
    rag = RAGPersistenceMixin.__new__(RAGPersistenceMixin)
    rag.persist_dir = str(tmp_path)
    rag.indices = {"knowledge": types.SimpleNamespace(storage_context=_Store(fail))}
    return rag


def test_a_failed_save_keeps_the_old_index(tmp_path):
    live = tmp_path / "knowledge"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}')
    with pytest.raises(OSError):
        _rag(tmp_path, fail=True)._persist_index_atomic("knowledge")
    assert (live / "docstore.json").read_text() == '{"old": true}'


def test_a_good_save_replaces_it_and_leaves_no_temporaries(tmp_path):
    live = tmp_path / "knowledge"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}')
    (tmp_path / "knowledge_tmp").mkdir()                   # left by an earlier cut-off save
    _rag(tmp_path, fail=False)._persist_index_atomic("knowledge")
    assert (live / "docstore.json").read_text() == '{"new": true}'
    # The lock file is a durable coordination primitive, not a stale
    # staging artifact. All other temporary paths must be gone.
    assert {p.name for p in tmp_path.iterdir()} == {"knowledge", ".rag-persistence.lock"}



def test_snapshot_tree_is_synced_before_swap_and_parent_after_each_rename(
    tmp_path, monkeypatch
):
    import shutil
    from pathlib import Path

    from utils.core import atomic_write
    from utils.core import kaia_rag_persistence

    live = tmp_path / "knowledge"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}', encoding="utf-8")
    harness = _rag(tmp_path, fail=False)

    events = []
    real_fsync_tree = atomic_write.fsync_tree
    real_fsync_directory = atomic_write.fsync_directory
    real_rename = os.rename
    real_rmtree = shutil.rmtree

    def observe_tree(path):
        events.append(("tree", Path(path)))
        real_fsync_tree(path)

    def observe_directory(path):
        events.append(("dir", Path(path)))
        real_fsync_directory(path)

    def observe_rename(source, destination):
        events.append(("rename", Path(source).name, Path(destination).name))
        real_rename(source, destination)

    def observe_rmtree(path, *args, **kwargs):
        events.append(("rmtree", Path(path).name))
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(atomic_write, "fsync_tree", observe_tree)
    monkeypatch.setattr(atomic_write, "fsync_directory", observe_directory)
    monkeypatch.setattr(kaia_rag_persistence.os, "rename", observe_rename)
    monkeypatch.setattr(kaia_rag_persistence.shutil, "rmtree", observe_rmtree)

    harness._persist_index_atomic("knowledge")

    tree_sync = next(i for i, event in enumerate(events) if event[0] == "tree")
    live_to_old = next(
        i for i, event in enumerate(events)
        if event == ("rename", "knowledge", "knowledge_old")
    )
    old_to_live_sync = next(
        i for i, event in enumerate(events)
        if i > live_to_old and event == ("dir", tmp_path)
    )
    temp_to_live = next(
        i for i, event in enumerate(events)
        if event == ("rename", "knowledge_tmp", "knowledge")
    )
    new_live_sync = next(
        i for i, event in enumerate(events)
        if i > temp_to_live and event == ("dir", tmp_path)
    )
    old_cleanup = next(
        i for i, event in enumerate(events)
        if event == ("rmtree", "knowledge_old")
    )
    cleanup_sync = next(
        i for i, event in enumerate(events)
        if i > old_cleanup and event == ("dir", tmp_path)
    )

    assert tree_sync < live_to_old < old_to_live_sync
    assert old_to_live_sync < temp_to_live < new_live_sync
    assert new_live_sync < old_cleanup < cleanup_sync
    assert (live / "docstore.json").read_text(encoding="utf-8") == '{"new": true}'



def test_parent_fsync_failure_after_live_to_old_rolls_last_good_back(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from utils.core import atomic_write
    from utils.core import kaia_rag_persistence

    live = tmp_path / "knowledge"
    old = tmp_path / "knowledge_old"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}', encoding="utf-8")
    harness = _rag(tmp_path, fail=False)

    real_rename = os.rename
    real_fsync_directory = atomic_write.fsync_directory
    fail_next_parent_sync = [False]

    def observe_rename(source, destination):
        real_rename(source, destination)
        if Path(source) == live and Path(destination) == old:
            fail_next_parent_sync[0] = True

    def fail_once(directory):
        if fail_next_parent_sync[0] and Path(directory) == tmp_path:
            fail_next_parent_sync[0] = False
            raise OSError("injected parent-directory fsync failure")
        real_fsync_directory(directory)

    monkeypatch.setattr(kaia_rag_persistence.os, "rename", observe_rename)
    monkeypatch.setattr(atomic_write, "fsync_directory", fail_once)

    with pytest.raises(OSError, match="injected parent-directory fsync failure"):
        harness._persist_index_atomic("knowledge")

    assert (live / "docstore.json").read_text(encoding="utf-8") == '{"old": true}'
    assert not old.exists()



def test_parent_fsync_failure_after_new_live_rename_keeps_backup(
    tmp_path, monkeypatch
):
    from pathlib import Path

    from utils.core import atomic_write
    from utils.core import kaia_rag_persistence

    live = tmp_path / "knowledge"
    old = tmp_path / "knowledge_old"
    temp = tmp_path / "knowledge_tmp"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}', encoding="utf-8")
    harness = _rag(tmp_path, fail=False)

    real_rename = os.rename
    real_fsync_directory = atomic_write.fsync_directory
    fail_next_parent_sync = [False]

    def observe_rename(source, destination):
        real_rename(source, destination)
        if Path(source) == temp and Path(destination) == live:
            fail_next_parent_sync[0] = True

    def fail_once(directory):
        if fail_next_parent_sync[0] and Path(directory) == tmp_path:
            fail_next_parent_sync[0] = False
            raise OSError("injected post-promotion fsync failure")
        real_fsync_directory(directory)

    monkeypatch.setattr(kaia_rag_persistence.os, "rename", observe_rename)
    monkeypatch.setattr(atomic_write, "fsync_directory", fail_once)

    with pytest.raises(OSError, match="injected post-promotion fsync failure"):
        harness._persist_index_atomic("knowledge")

    assert (live / "docstore.json").read_text(encoding="utf-8") == '{"new": true}'
    assert (old / "docstore.json").read_text(encoding="utf-8") == '{"old": true}'



def test_manifest_uses_shared_durable_atomic_writer(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from utils.core import atomic_write
    from utils.core.kaia_rag_indexer import RAGIndexerMixin

    class ManifestHarness(RAGIndexerMixin):
        def __init__(self, root):
            self.persist_dir = str(root / "rag_storage")
            self.state_file = str(Path(self.persist_dir) / "file_manifest.json")
            self.indexed_files = {
                str(root / "document.md"): {"mtime": 123.0, "size": 7, "nodes": ["n1"]}
            }

    harness = ManifestHarness(tmp_path)
    calls = []
    real_write_atomic = atomic_write.write_atomic

    def observe_write(path, text, encoding="utf-8"):
        calls.append(Path(path))
        return real_write_atomic(path, text, encoding=encoding)

    monkeypatch.setattr(atomic_write, "write_atomic", observe_write)

    assert harness._save_indexed_files() is True

    assert calls == [Path(harness.state_file)]
    assert json.loads(Path(harness.state_file).read_text(encoding="utf-8")) == harness.indexed_files



def test_staging_tree_fsync_failure_never_promotes_the_new_snapshot(
    tmp_path, monkeypatch
):
    from utils.core import atomic_write

    live = tmp_path / "knowledge"
    live.mkdir()
    (live / "docstore.json").write_text('{"old": true}', encoding="utf-8")
    harness = _rag(tmp_path, fail=False)

    def fail_tree(_directory):
        raise OSError("injected staged-tree fsync failure")

    monkeypatch.setattr(atomic_write, "fsync_tree", fail_tree)

    with pytest.raises(OSError, match="injected staged-tree fsync failure"):
        harness._persist_index_atomic("knowledge")

    assert (live / "docstore.json").read_text(encoding="utf-8") == '{"old": true}'
    assert (tmp_path / "knowledge_tmp" / "docstore.json").read_text(encoding="utf-8") == '{"new": true}'
    assert not (tmp_path / "knowledge_old").exists()
