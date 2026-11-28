"""Corpus writes must be all-or-nothing.

CLAUDE.md §4 has required `.tmp` then `os.replace()` since a half-written
registry took the bot down. A September 2026 sweep found the rule was being
followed where people remembered and nowhere else: 35 bare `write_text` calls
across 21 modules that rewrite `knowledge_base/` in place — the nightly metadata
enrichment, the hourly ingress filer, the dream engine, every profile generator.

An interrupted rewrite there raises nothing anywhere. It leaves a truncated
document in the corpus, indexed on the next sweep, retrievable, and
indistinguishable from a file that was simply short.
"""
import os
from pathlib import Path

import pytest

from utils.core.atomic_write import append_atomic, write_atomic


def test_it_writes(tmp_path):
    p = write_atomic(tmp_path / "x.md", "hello")
    assert p.read_text(encoding="utf-8") == "hello"


def test_it_creates_parent_directories(tmp_path):
    p = write_atomic(tmp_path / "a" / "b" / "x.md", "hi")
    assert p.exists()


def test_it_replaces_existing_content(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("old", encoding="utf-8")
    write_atomic(p, "new")
    assert p.read_text(encoding="utf-8") == "new"


def test_a_failed_write_leaves_the_original_intact(tmp_path):
    """The whole point. A rewrite that dies half way must not destroy what was
    there — `write_text` truncates first and writes second."""
    p = tmp_path / "x.md"
    p.write_text("the original document", encoding="utf-8")
    with pytest.raises(Exception):
        write_atomic(p, object())          # type: ignore[arg-type]
    assert p.read_text(encoding="utf-8") == "the original document"


def test_a_failed_write_leaves_no_temporary_behind(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("original", encoding="utf-8")
    with pytest.raises(Exception):
        write_atomic(p, object())          # type: ignore[arg-type]
    assert [f.name for f in tmp_path.iterdir()] == ["x.md"]


def test_the_temporary_lives_beside_its_destination(tmp_path, monkeypatch):
    """`os.replace` is only atomic within a filesystem, so the temporary cannot
    go to /tmp."""
    import os
    from utils.core import atomic_write as aw
    moves = []
    real = os.replace
    monkeypatch.setattr(aw.os, "replace", lambda src, dst: (moves.append((src, dst)), real(src, dst))[1])
    dest = tmp_path / "corpus" / "page.md"
    dest.parent.mkdir()
    write_atomic(dest, "hello")
    assert dest.read_text() == "hello"
    assert moves and all(os.path.dirname(os.fspath(src)) == os.fspath(dest.parent) for src, _ in moves)


def test_append_preserves_what_was_there(tmp_path):
    p = tmp_path / "log.md"
    write_atomic(p, "first\n")
    append_atomic(p, "second\n")
    assert p.read_text(encoding="utf-8") == "first\nsecond\n"


def test_append_to_a_missing_file_creates_it(tmp_path):
    p = append_atomic(tmp_path / "new.md", "only line\n")
    assert p.read_text(encoding="utf-8") == "only line\n"


def test_concurrent_appends_do_not_overwrite_each_other(tmp_path, monkeypatch):
    """Force both unlocked writers to read the old content before either replaces it."""
    import threading
    import utils.core.atomic_write as atomic_write_module

    target = tmp_path / "shared.log"
    write_atomic(target, "base\n")
    simultaneous_writes = threading.Barrier(2)
    real_write_atomic = atomic_write_module.write_atomic
    errors = []

    def synchronized_write(path, text, encoding="utf-8"):
        if Path(path) == target:
            try:
                simultaneous_writes.wait(timeout=0.15)
            except threading.BrokenBarrierError:
                # With append_atomic's lock, only one writer can reach this
                # point at a time. Let it complete, then the next writer reads
                # the newly appended content.
                pass
        return real_write_atomic(path, text, encoding=encoding)

    monkeypatch.setattr(atomic_write_module, "write_atomic", synchronized_write)

    def append(line):
        try:
            append_atomic(target, line + "\n")
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    writers = [threading.Thread(target=append, args=(line,)) for line in ("first", "second")]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join(timeout=3)

    assert not errors
    assert all(not writer.is_alive() for writer in writers)
    assert set(target.read_text(encoding="utf-8").splitlines()) == {"base", "first", "second"}


AUTOMATIC_WRITERS = [
    "utils/core/kaia_dream.py",
    "utils/social/kaia_identities.py",
    "utils/commands/download_handler.py",
    "utils/commands/youtube_handler.py",
    "tools/maintenance/process_ingress.py",
    "tools/maintenance/enrich_metadata.py",
    "tools/maintenance/generate_user_profiles.py",
    "tools/maintenance/rollup_user_logs.py",
    "tools/maintenance/compact_user_logs.py",
]


@pytest.mark.parametrize("path", AUTOMATIC_WRITERS)
def test_writers_that_run_unattended_are_atomic(path):
    """These run from background tasks or user commands with nobody watching, so
    an interrupted write is found weeks later as a short document."""
    src = Path(path).read_text(encoding="utf-8")
    assert "write_atomic" in src, f"{path} no longer writes atomically"


def test_threads_writing_one_file_do_not_share_a_temporary(tmp_path):
    """Writer threads in one process need their own temporary: with the pid
    alone, one thread's os.replace moved the file the other was still writing."""
    import threading
    target = tmp_path / "stats.json"
    errors = []

    def writer(n):
        try:
            for _ in range(50):
                write_atomic(target, f"writer {n}\n" * 200)
        except Exception as e:  # pragma: no cover - the failure being tested
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    lines = set(target.read_text(encoding="utf-8").splitlines())
    assert len(lines) == 1  # one writer's whole text, never a mix
    assert not list(tmp_path.glob(".*.tmp"))



def test_atomic_replace_fsyncs_its_parent_directory_after_replacement(tmp_path, monkeypatch):
    """The file fsync alone does not make the renamed directory entry durable."""
    import utils.core.atomic_write as atomic_write_module

    target = tmp_path / "state.json"
    target.write_text("old", encoding="utf-8")
    real_fsync_directory = atomic_write_module.fsync_directory
    synced = []

    def observe_directory_sync(directory):
        assert target.read_text(encoding="utf-8") == "new"
        synced.append(Path(directory))
        real_fsync_directory(directory)

    monkeypatch.setattr(
        atomic_write_module, "fsync_directory", observe_directory_sync
    )
    write_atomic(target, "new")

    assert synced == [tmp_path]
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_replace_reports_parent_directory_sync_failure(tmp_path, monkeypatch):
    """Do not claim durable replacement when the directory sync failed."""
    import utils.core.atomic_write as atomic_write_module

    target = tmp_path / "state.json"

    def fail_directory_sync(_directory):
        raise OSError("simulated directory fsync failure")

    monkeypatch.setattr(
        atomic_write_module, "fsync_directory", fail_directory_sync
    )
    with pytest.raises(OSError, match="directory fsync"):
        write_atomic(target, "new")

    # os.replace already happened; the raised error means durability was not
    # confirmed, not that the destination was rolled back.
    assert target.read_text(encoding="utf-8") == "new"



def test_atomic_write_syncs_each_parent_when_creating_nested_directories(tmp_path, monkeypatch):
    """A new file's parent chain must exist durably after a successful write."""
    import utils.core.atomic_write as atomic_write_module

    synced = []
    real_fsync_directory = atomic_write_module.fsync_directory

    def observe(directory):
        synced.append(Path(directory))
        real_fsync_directory(directory)

    monkeypatch.setattr(atomic_write_module, "fsync_directory", observe)
    target = tmp_path / "first" / "second" / "state.json"
    write_atomic(target, "durable")

    assert target.read_text(encoding="utf-8") == "durable"
    assert synced == [tmp_path, tmp_path / "first", tmp_path / "first" / "second"]


def test_set_aside_moves_the_file_and_append_lock_is_a_context_manager(tmp_path):
    from pathlib import Path
    from utils.core import atomic_write
    store = tmp_path / "store.json"
    store.write_text("{broken", encoding="utf-8")
    kept = atomic_write.set_aside(store)
    assert isinstance(kept, Path) and kept.read_text(encoding="utf-8") == "{broken" and not store.exists()
    assert atomic_write.set_aside(store) is None
    with atomic_write.append_lock(store) as dest:
        assert dest == store


def test_fsync_tree_syncs_regular_files_and_directories_bottom_up(tmp_path, monkeypatch):
    import os
    import stat
    from pathlib import Path

    from utils.core import atomic_write

    root = tmp_path / "snapshot"
    nested = root / "nested"
    nested.mkdir(parents=True)
    files = (
        root / "root.json",
        nested / "child.json",
    )
    for path in files:
        path.write_text("durable", encoding="utf-8")
    expected_inodes = {path.stat().st_ino for path in files}

    real_fsync = os.fsync
    synced_files = []

    def observe_fsync(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            synced_files.append(os.fstat(descriptor).st_ino)
        real_fsync(descriptor)

    real_fsync_directory = atomic_write.fsync_directory
    synced_directories = []

    def observe_directory(directory):
        synced_directories.append(Path(directory))
        real_fsync_directory(directory)

    monkeypatch.setattr(os, "fsync", observe_fsync)
    monkeypatch.setattr(atomic_write, "fsync_directory", observe_directory)

    atomic_write.fsync_tree(root)

    assert set(synced_files) == expected_inodes
    assert synced_directories == [nested, root, tmp_path]


def test_read_json_store_sets_an_unreadable_store_aside_instead_of_answering_over_it(tmp_path):
    """Answering {} for a store that would not parse, then saving, replaced the
    whole store; nine of them were fixed by hand on 21 Nov."""
    from utils.core.atomic_write import read_json_store
    store = tmp_path / "desires.json"
    assert read_json_store(store, {"a": 1}) == {"a": 1}              # missing: the default
    store.write_text('{"curiosity": 0.4}', encoding="utf-8")
    assert read_json_store(store, {}, kind=dict) == {"curiosity": 0.4}
    store.write_text('{"curiosity": 0.4', encoding="utf-8")          # torn
    assert read_json_store(store, {}, kind=dict) == {}
    assert not store.exists()
    kept = list(tmp_path.glob("desires.json.unreadable-*"))
    assert len(kept) == 1 and kept[0].read_text() == '{"curiosity": 0.4'
    store.write_text('[1, 2]', encoding="utf-8")                     # the wrong shape
    default = {"x": []}
    got = read_json_store(store, default, kind=dict)
    assert got == default and got is not default and not store.exists()
