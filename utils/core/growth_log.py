"""Serialized appends and bounded rotation for the shared growth ledger.

The growth log has several writers (dreams, creation events, and interaction
milestones). A sidecar flock covers both each append and any subsequent
rotation, so one writer cannot replace a snapshot that omits another writer's
just-appended event. The lock file is retained to keep every process locking
the same inode.
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Union

from utils.core.atomic_write import fsync_directory, mkdir_durable, write_atomic

PathLike = Union[str, os.PathLike[str]]


def append_growth_event(
    event: Mapping[str, Any],
    path: PathLike,
    *,
    max_bytes: int | None = 600_000,
    max_entries: int = 2_000,
) -> Path:
    """Append one JSONL event and rotate under the same interprocess lock.

    Writes are append-only in the common case. Once the byte threshold is
    exceeded, the newest `max_entries` complete lines are atomically retained.
    Set `max_bytes=None` to check the entry cap on every append.
    """
    if max_entries < 1:
        raise ValueError("max_entries must be at least 1")
    if max_bytes is not None and max_bytes < 1:
        raise ValueError("max_bytes must be at least 1")

    destination = Path(path)
    mkdir_durable(destination.parent)
    lock_path = destination.with_name(f".{destination.name}.lock")
    payload = dict(event)
    payload.setdefault("ts", time.time())
    serialized = json.dumps(payload) + "\n"

    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            created = not destination.exists()
            with open(destination, "a", encoding="utf-8") as growth_file:
                growth_file.write(serialized)
                growth_file.flush()
                os.fsync(growth_file.fileno())

            # A newly created JSONL file also needs its directory entry synced.
            if created:
                fsync_directory(destination.parent)

            # Rotation is best-effort: the append and any new file entry are
            # already durable even if compaction cannot run.
            try:
                if max_bytes is None or destination.stat().st_size > max_bytes:
                    with open(destination, "r", encoding="utf-8") as growth_file:
                        lines = growth_file.readlines()
                    if len(lines) > max_entries:
                        write_atomic(destination, "".join(lines[-max_entries:]))
            except Exception:
                pass
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return destination
