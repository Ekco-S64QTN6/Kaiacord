"""One way to write a file that something else might be reading.

CLAUDE.md §4 requires atomic writes — `.tmp` then `os.replace()` — and the rule
existed because a half-written registry took the bot down. It was being followed
in the places people remembered and nowhere else: a September 2026 sweep found
35 bare `write_text` calls across 21 modules that rewrite `knowledge_base/`
in place, including the nightly metadata enrichment, the hourly ingress filer,
the dream engine and every profile generator.

An interrupted rewrite there does not raise anywhere. It leaves a truncated
document in the corpus, indexed on the next sweep, retrievable, and identical in
every respect to a file that was simply short.

`os.replace` is atomic within a filesystem, which is why the temporary file is
written beside its destination rather than in `/tmp`.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

PathLike = Union[str, "os.PathLike[str]"]


def write_atomic(path: PathLike, text: str, encoding: str = "utf-8") -> Path:
    """Write `text` to `path` so a reader sees either the old file or the new one.

    Creates parent directories. Returns the path written.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A fixed `.tmp` suffix collides when two writers touch one file at once;
    # the pid keeps concurrent passes from clobbering each other's temporary.
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
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
