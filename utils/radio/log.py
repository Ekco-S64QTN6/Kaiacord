"""The radio history: what Kaia recorded, what she heard, how right she was.

Lives in memory/radio/ — deliberately outside knowledge_base/, so the RAG
index never sees it. HF noise, half-heard call signs and base32 strings are
exactly what would pollute retrieval (Ekco, 24 Sept 2026).

    memory/radio/log.json     newest first, capped at MAX_ENTRIES
    memory/radio/clips/       Opus clips, capped at MAX_CLIPS (oldest dropped)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from utils.core.atomic_write import write_atomic
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

MAX_ENTRIES = 500
MAX_CLIPS = 300
_lock = threading.Lock()


def log_path() -> Path:
    return Path(telemetry_path("memory/radio/log.json"))


def clips_dir() -> Path:
    p = log_path().parent / ("clips.test" if ".test." in log_path().name else "clips")
    p.mkdir(parents=True, exist_ok=True)
    return p


def entries() -> list[dict]:
    try:
        data = json.loads(log_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def add(entry: dict) -> None:
    with _lock:
        items = [entry] + [e for e in entries() if e.get("id") != entry.get("id")]
        write_atomic(log_path(), json.dumps(items[:MAX_ENTRIES], indent=1))
    prune_clips()


def update(entry_id: str, **fields) -> Optional[dict]:
    with _lock:
        items = entries()
        for e in items:
            if e.get("id") == entry_id:
                e.update(fields)
                write_atomic(log_path(), json.dumps(items, indent=1))
                return e
    return None


def prune_clips() -> None:
    clips = sorted(clips_dir().glob("*.ogg"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in clips[MAX_CLIPS:]:
        old.unlink(missing_ok=True)
