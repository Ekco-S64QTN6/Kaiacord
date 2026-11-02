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
import time
from pathlib import Path
from typing import Callable, List, Optional, TypeVar

from utils.infrastructure.logging.kaia_logger import log_info
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

BELIEFS_PATH = Path(telemetry_path("memory/beliefs.json"))

_lock = threading.RLock()
T = TypeVar("T")

MAX_BELIEFS = 100
#: A belief this new is not up for eviction. A dream's new belief starts at a
#: confidence below what almost every older one scores, so with the store full
#: the weakest was always the one just written: it evicted itself on the spot.
PROTECT_NEW_S = 7 * 86400


def retention_score(belief: dict, now: float) -> float:
    """Confidence reinforced by use and decayed by age: +0.05 per recall (capped),
    -0.01 per day untouched (capped), so an unused belief takes about a month to
    fall a full band. Confidence alone would never let a fresh view outrank a
    fortnight-old one nothing has referenced since."""
    conf = float(belief.get("confidence", 0.5) or 0.5)
    accesses = int(belief.get("access_count", 0) or 0)
    age_days = max(0.0, (now - float(belief.get("last_updated", now) or now)) / 86400.0)
    return conf + min(0.25, 0.05 * accesses) - min(0.30, 0.01 * age_days)


def evict_weakest(beliefs: List[dict], keep_topic: str = "", now: Optional[float] = None) -> Optional[dict]:
    """Over the cap, drop the single weakest belief and return it: the weakest
    past its protection, else the weakest of the new. Never `keep_topic`, the one
    being written. A burst of new beliefs cannot wipe a block, and file order stays."""
    if len(beliefs) <= MAX_BELIEFS:
        return None
    now = time.time() if now is None else now
    keep = keep_topic.strip().lower()
    candidates = [i for i, b in enumerate(beliefs) if str(b.get("topic", "")).lower() != keep]
    if not candidates:
        return None
    settled = [i for i in candidates
               if now - float(beliefs[i].get("last_updated", 0) or 0) >= PROTECT_NEW_S]
    weakest = min(settled or candidates, key=lambda i: retention_score(beliefs[i], now))
    evicted = beliefs.pop(weakest)
    log_info(f"🧠 Belief evicted (store at cap): '{str(evicted.get('topic', '?'))[:40]}' "
             f"conf={evicted.get('confidence')} accesses={evicted.get('access_count', 0)}")
    return evicted


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
    passed back. Nothing is written if it raises — or if the file exists and
    can't be read: `load()` answers [] then, and saving the change on top of
    that would replace every belief with it.
    """
    from utils.core.atomic_write import write_atomic
    with _lock:
        beliefs = load()
        if not beliefs and BELIEFS_PATH.exists() and BELIEFS_PATH.stat().st_size > 2:
            raise ValueError(f"{BELIEFS_PATH} is unreadable; not overwriting it")
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
