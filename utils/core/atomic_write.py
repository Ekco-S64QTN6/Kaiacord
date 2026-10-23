"""One way to write a file that something else might be reading.

Write to `.tmp`, then `os.replace()`. Required for everything under
`knowledge_base/` and `memory/` (CLAUDE.md §4): an interrupted bare write raises
nowhere and leaves a truncated document that is indexed on the next sweep,
retrievable, and indistinguishable from a file that was simply short.

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


def write_atomic(path: PathLike, text: str, encoding: str = "utf-8") -> Path:
    """Write `text` to `path` so a reader sees either the old file or the new one.

    Creates parent directories. Returns the path written.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
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
