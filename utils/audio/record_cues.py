"""Persistent, audio-identity-scoped hot and memory cues for the records booth.

Cue banks live under memory/records, never in the user's DJ catalog. Audio
identity survives file renames and ID3 edits; writes are serialized across
threads/processes and replaced atomically. This module is called by dashboard
request/snapshot threads, never by the 20 ms audio renderer.
"""
from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Optional

from utils.core.atomic_write import append_lock, set_aside, write_atomic
from utils.infrastructure.monitoring.telemetry_paths import telemetry_path

VERSION = 1
HOT_CUE_COUNT = 8
_LOCK = threading.RLock()
_CACHE: dict[str, tuple[tuple[int, int, int, int] | None, dict]] = {}


def store_path() -> Path:
    """Production cue store, redirected to a test-suffixed file under pytest."""
    return Path(telemetry_path("memory/records/cues.json"))


def _empty() -> dict:
    return {"memory": None, "hot": [None] * HOT_CUE_COUNT}


def _position(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def record_key(record) -> Optional[str]:
    """Use the stable audio payload identity, not the editable catalog path."""
    try:
        from utils.audio.audio_identity import audio_signature
        return audio_signature(str(record.path))
    except (OSError, TypeError, ValueError):
        return None


def _read_store(path: Path, *, preserve_invalid: bool = False) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": VERSION, "records": {}}
    except (OSError, UnicodeError, json.JSONDecodeError):
        # Preserve a damaged store rather than interpreting it as an empty bank
        # and silently overwriting every cue when the next pad is pressed.
        if preserve_invalid:
            set_aside(path)
        return {"version": VERSION, "records": {}}
    if not isinstance(payload, dict) or payload.get("version") != VERSION or not isinstance(payload.get("records"), dict):
        set_aside(path)
        return {"version": VERSION, "records": {}}
    return payload


def _clean_bank(raw) -> dict:
    out = _empty()
    if not isinstance(raw, dict):
        return out
    out["memory"] = _position(raw.get("memory"))
    hot = raw.get("hot")
    if isinstance(hot, list):
        for index, value in enumerate(hot[:HOT_CUE_COUNT]):
            out["hot"][index] = _position(value)
    return out


def load(record) -> dict:
    """Return a copy of the record's memory/hot cue bank."""
    key = record_key(record)
    if key is None:
        return _empty()
    path = store_path()
    try:
        st = path.stat()
        stat_key = (int(st.st_dev), int(st.st_ino), int(st.st_size), int(st.st_mtime_ns))
    except OSError:
        stat_key = None
    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] == stat_key:
            return {"memory": cached[1]["memory"], "hot": list(cached[1]["hot"])}
        payload = _read_store(path)
        bank = _clean_bank(payload["records"].get(key))
        try:
            st = path.stat()
            stat_key = (int(st.st_dev), int(st.st_ino), int(st.st_size), int(st.st_mtime_ns))
        except OSError:
            stat_key = None
        _CACHE[key] = (stat_key, bank)
        return {"memory": bank["memory"], "hot": list(bank["hot"])}


def _mutate(record, mutation) -> bool:
    key = record_key(record)
    if key is None:
        return False
    path = store_path()
    with _LOCK:
        with append_lock(path):
            payload = _read_store(path, preserve_invalid=True)
            bank = _clean_bank(payload["records"].get(key))
            if not mutation(bank):
                return False
            payload["records"][key] = bank
            write_atomic(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
            st = path.stat()
            _CACHE[key] = ((int(st.st_dev), int(st.st_ino), int(st.st_size), int(st.st_mtime_ns)), bank)
    return True


def set_hot(record, index: int, position: float) -> bool:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < HOT_CUE_COUNT:
        return False
    cue = _position(position)
    if cue is None:
        return False
    return _mutate(record, lambda bank: (bank["hot"].__setitem__(index, cue) is None))


def clear_hot(record, index: int) -> bool:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < HOT_CUE_COUNT:
        return False
    return _mutate(record, lambda bank: (bank["hot"].__setitem__(index, None) is None))


def set_memory(record, position: float) -> bool:
    cue = _position(position)
    if cue is None:
        return False
    return _mutate(record, lambda bank: (bank.__setitem__("memory", cue) is None))


def clear_memory(record) -> bool:
    return _mutate(record, lambda bank: (bank.__setitem__("memory", None) is None))


def clear_cache() -> None:
    """Clear the read cache (used by tests after changing the backing file)."""
    with _LOCK:
        _CACHE.clear()
