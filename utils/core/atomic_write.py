"""One way to write a file that something else might be reading.

Write to a same-directory temporary, fsync it, then `os.replace()` and fsync
the parent directory. The file sync persists the new contents; the directory
sync persists the rename itself across a host crash. Required for everything
under `knowledge_base/` and `memory/` (CLAUDE.md §4).

`os.replace` is atomic only within a filesystem, so the temporary is written
beside its destination rather than in `/tmp`.
"""
from __future__ import annotations

import fcntl
import os
import threading
from pathlib import Path
from typing import Union

PathLike = Union[str, "os.PathLike[str]"]


def fsync_directory(directory: PathLike) -> None:
    """Persist directory-entry changes such as file creation and replacement."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(os.fspath(directory), flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def mkdir_durable(directory: PathLike) -> None:
    """Create a directory tree and sync each parent that gains a new entry."""
    target = Path(directory)
    missing = []
    current = target
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    for path in reversed(missing):
        try:
            path.mkdir()
        except FileExistsError:
            if not path.is_dir():
                raise
        else:
            fsync_directory(path.parent)


def write_atomic(path: PathLike, text: str, encoding: str = "utf-8") -> Path:
    """Write `text` to `path` so a reader sees either the old file or the new one.

    Creates parent directories. Returns the path written.
    """
    dest = Path(path)
    mkdir_durable(dest.parent)
    # A fixed `.tmp` suffix collides when two writers touch one file at once.
    # The pid separates processes and the thread id separates writer threads
    # inside one: with the pid alone, two threads shared a temporary, and the
    # loser's os.replace found it already moved.
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding=encoding) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
        fsync_directory(dest.parent)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return dest


def append_atomic(path: PathLike, text: str, encoding: str = "utf-8") -> Path:
    """Append to a small log without losing concurrent writers.

    The read-modify-write sequence is protected by a stable sidecar lock, so
    cooperating threads and processes cannot both read the same old contents
    and replace one another's append. The lock file is intentionally retained:
    unlinking it could let writers lock different inodes.
    This rewrites the file, so it is only for small logs in
    `knowledge_base/user_logs/`, not large files.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lock_path = dest.with_name(f".{dest.name}.append.lock")
    with open(lock_path, "a", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                existing = dest.read_text(encoding=encoding, errors="replace")
            except FileNotFoundError:
                existing = ""
            write_atomic(dest, existing + text, encoding=encoding)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return dest
