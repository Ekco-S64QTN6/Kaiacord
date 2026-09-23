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


def test_the_temporary_lives_beside_its_destination(tmp_path):
    """`os.replace` is only atomic within a filesystem, so the temporary cannot
    go to /tmp."""
    import inspect

    src = inspect.getsource(write_atomic)
    assert "dest.with_name" in src, "the temporary is not beside its destination"
    assert "os.replace" in src


def test_append_preserves_what_was_there(tmp_path):
    p = tmp_path / "log.md"
    write_atomic(p, "first\n")
    append_atomic(p, "second\n")
    assert p.read_text(encoding="utf-8") == "first\nsecond\n"


def test_append_to_a_missing_file_creates_it(tmp_path):
    p = append_atomic(tmp_path / "new.md", "only line\n")
    assert p.read_text(encoding="utf-8") == "only line\n"


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
