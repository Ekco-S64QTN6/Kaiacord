"""memory/beliefs.json, read and written in one place.

Two writers change it: the dream engine forms and revises beliefs, and every
chat turn that touches one bumps its access count. Each used to read the whole
file, change its copy and write the whole copy back, from different threads —
so a turn that read the file before a dream wrote it put its stale copy back
afterwards and the new belief was gone. Every change now goes through
`update()`, which re-reads under a lock, applies the change and writes
atomically.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, List, TypeVar

BELIEFS_PATH = Path("memory") / "beliefs.json"

_lock = threading.RLock()
T = TypeVar("T")


def load() -> List[dict]:
    """The current beliefs; [] when the file is missing or unreadable."""
    with _lock:
        try:
            with open(BELIEFS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []


def update(change: Callable[[List[dict]], T]) -> T:
    """Apply `change` to a fresh read of the beliefs and save the result.

    `change` mutates the list in place and may return a value, which is
    passed back. Nothing is written if it raises.
    """
    from utils.core.atomic_write import write_atomic
    with _lock:
        beliefs = load()
        result = change(beliefs)
        write_atomic(BELIEFS_PATH, json.dumps(beliefs, indent=2))
        return result


def bump_access(topics) -> None:
    """Count one use of each named belief."""
    wanted = {str(t).lower() for t in topics if t}
    if not wanted:
        return

    def _bump(beliefs):
        for b in beliefs:
            if str(b.get("topic", "")).lower() in wanted:
                b["access_count"] = b.get("access_count", 0) + 1

    update(_bump)
