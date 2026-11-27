"""An index write killed partway through must not cost the index."""
import os



def test_an_index_left_in_old_is_restored_at_load(tmp_path):
    """persist() renames <itype> to <itype>_old, then <itype>_tmp to <itype>.
    Killed between the two, <itype> is missing and the last good copy sits in
    _old; loading used to start an empty index there and re-embed everything."""
    from llama_index.core import VectorStoreIndex
    from utils.core.kaia_rag import KaiaRAG

    rag = KaiaRAG(persist_dir=str(tmp_path / "rag"))
    base = rag.persist_dir
    for itype in ("persona", "user_profiles", "knowledge", "logs", "dreams"):
        VectorStoreIndex.from_documents([]).storage_context.persist(
            persist_dir=os.path.join(base, itype))
    os.rename(os.path.join(base, "knowledge"), os.path.join(base, "knowledge_old"))
    marker = os.path.join(base, "knowledge_old", "MARKER")
    open(marker, "w").close()

    rag._initialize_indices()

    assert os.path.exists(os.path.join(base, "knowledge", "MARKER")), "the old copy was not restored"
    assert not os.path.exists(os.path.join(base, "knowledge_old"))


def _rag_with_fake_snapshot_loader(tmp_path, monkeypatch):
    """Build the real RAG initializer around simple, path-aware snapshot fixtures."""
    from pathlib import Path
    from types import SimpleNamespace

    from utils.core import kaia_rag_indexer
    from utils.core.kaia_rag import KaiaRAG

    rag = KaiaRAG(persist_dir=str(tmp_path / "rag"))
    base = Path(rag.persist_dir)
    for itype in ("persona", "user_profiles", "knowledge", "logs", "dreams"):
        folder = base / itype
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SNAPSHOT").write_text(itype, encoding="utf-8")

    # Avoid involving the external vector-store format: the test exercises the
    # actual directory recovery path and makes the loader's decision explicit.
    monkeypatch.setattr(
        kaia_rag_indexer,
        "StorageContext",
        SimpleNamespace(from_defaults=lambda *, persist_dir: persist_dir),
    )
    rag._populate_indexed_files = lambda: None
    return rag, base, kaia_rag_indexer



def test_corrupt_live_index_restores_and_loads_the_valid_last_good_backup(
    tmp_path, monkeypatch
):
    """A present but unreadable live snapshot must not hide a valid *_old copy."""
    from pathlib import Path
    from types import SimpleNamespace

    rag, base, indexer_module = _rag_with_fake_snapshot_loader(tmp_path, monkeypatch)
    live = base / "knowledge"
    old = base / "knowledge_old"
    os.rename(live, old)
    (old / "LAST_GOOD").write_text("previous valid snapshot", encoding="utf-8")
    live.mkdir()
    (live / "CORRUPT").write_text("unreadable new snapshot", encoding="utf-8")

    loads = []

    def load_snapshot(path):
        path = Path(path)
        loads.append(path)
        if (path / "CORRUPT").exists():
            raise ValueError("live snapshot is corrupt")
        return SimpleNamespace(persist_dir=str(path))

    monkeypatch.setattr(indexer_module, "load_index_from_storage", load_snapshot)

    rag._initialize_indices()

    assert loads.count(live) == 2  # failed live load, then reload after promotion
    assert old in loads  # independent validation before promotion
    assert rag.indices["knowledge"].persist_dir == str(live)
    assert (live / "LAST_GOOD").read_text(encoding="utf-8") == "previous valid snapshot"
    assert not (live / "CORRUPT").exists()
    assert not old.exists()
    assert not Path(f"{live}_corrupt").exists()



def test_unreadable_live_and_backup_snapshots_are_both_preserved(
    tmp_path, monkeypatch
):
    """If neither snapshot validates, startup fails without deleting either artifact."""
    import pytest

    rag, base, indexer_module = _rag_with_fake_snapshot_loader(tmp_path, monkeypatch)
    live = base / "knowledge"
    old = base / "knowledge_old"
    os.rename(live, old)
    (old / "CORRUPT").write_text("unreadable backup", encoding="utf-8")
    live.mkdir()
    (live / "CORRUPT").write_text("unreadable live", encoding="utf-8")

    def load_snapshot(path):
        from pathlib import Path

        if (Path(path) / "CORRUPT").exists():
            raise ValueError("snapshot is unreadable")
        return object()

    monkeypatch.setattr(indexer_module, "load_index_from_storage", load_snapshot)

    with pytest.raises(ValueError, match="snapshot is unreadable"):
        rag._initialize_indices()

    assert (live / "CORRUPT").read_text(encoding="utf-8") == "unreadable live"
    assert (old / "CORRUPT").read_text(encoding="utf-8") == "unreadable backup"
    assert (base / "knowledge_old").is_dir()



def test_unreadable_live_directory_listing_uses_the_valid_backup(
    tmp_path, monkeypatch
):
    """A permission/listing failure is a corrupt-live condition too."""
    from pathlib import Path
    from types import SimpleNamespace

    rag, base, indexer_module = _rag_with_fake_snapshot_loader(tmp_path, monkeypatch)
    live = base / "knowledge"
    old = base / "knowledge_old"
    os.rename(live, old)
    (old / "LAST_GOOD").write_text("valid backup", encoding="utf-8")
    live.mkdir()
    (live / "CORRUPT").write_text("unreadable live", encoding="utf-8")

    real_listdir = os.listdir

    def listdir(path):
        if Path(path) == live:
            raise PermissionError("cannot inspect live snapshot")
        return real_listdir(path)

    monkeypatch.setattr(indexer_module.os, "listdir", listdir)
    monkeypatch.setattr(
        indexer_module,
        "load_index_from_storage",
        lambda path: SimpleNamespace(persist_dir=str(path)),
    )

    rag._initialize_indices()

    assert rag.indices["knowledge"].persist_dir == str(live)
    assert (live / "LAST_GOOD").read_text(encoding="utf-8") == "valid backup"
    assert not (live / "CORRUPT").exists()



def test_failed_reload_after_backup_promotion_rolls_both_directories_back(
    tmp_path, monkeypatch
):
    """A backup that fails at its final path must not replace or erase the live copy."""
    from pathlib import Path

    rag, base, indexer_module = _rag_with_fake_snapshot_loader(tmp_path, monkeypatch)
    live = base / "knowledge"
    old = base / "knowledge_old"
    os.rename(live, old)
    (old / "LAST_GOOD").write_text("backup", encoding="utf-8")
    live.mkdir()
    (live / "CORRUPT").write_text("original live", encoding="utf-8")

    live_loads = 0

    def load_snapshot(path):
        nonlocal live_loads
        path = Path(path)
        if path == live:
            live_loads += 1
            if live_loads in (1, 2):
                raise ValueError("live snapshot cannot load")
        return object()

    monkeypatch.setattr(indexer_module, "load_index_from_storage", load_snapshot)

    import pytest
    with pytest.raises(ValueError, match="live snapshot cannot load"):
        rag._initialize_indices()

    assert (live / "CORRUPT").read_text(encoding="utf-8") == "original live"
    assert (old / "LAST_GOOD").read_text(encoding="utf-8") == "backup"
    assert not (base / "knowledge_corrupt").exists()
