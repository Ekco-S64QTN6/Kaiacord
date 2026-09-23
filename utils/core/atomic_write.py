"""One way to write a file that something else might be reading.

Write to `.tmp`, then `os.replace()`. Required for everything under
`knowledge_base/` and `memory/` (CLAUDE.md §4): an interrupted bare write raises
nowhere and leaves a truncated document that is indexed on the next sweep,
retrievable, and indistinguishable from a file that was simply short.

`os.replace` is atomic only within a filesystem, so the temporary is written
beside its destination rather than in `/tmp`.
"""
from __future__ import annotations

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
    """Append, read-modify-write, atomically.

    For the small append-only logs in `knowledge_base/user_logs/`. Not for
    anything large — it rewrites the whole file.
    """
    dest = Path(path)
    existing = ""
    if dest.exists():
        existing = dest.read_text(encoding=encoding, errors="replace")
    return write_atomic(dest, existing + text, encoding=encoding)
