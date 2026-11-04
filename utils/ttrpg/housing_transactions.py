"""Crash-safe transactions spanning a character sheet and its housing JSON.

Housing gameplay actions run under the player's serialized RPG action lock.
This journal adds crash recovery across the two independently atomic files:
the intended snapshots are written first, then the character sheet and
housing snapshots are committed, and only then is the journal cleared.
"""
from __future__ import annotations

import asyncio
import copy
import glob
import hashlib
import json
import os
from typing import Any

_transaction_lock = asyncio.Lock()


def _journal_dir() -> str:
    from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
    return telemetry_path(os.path.join("memory", "ttrpg", "housing_transactions"))


def _journal_path(user_id: str) -> str:
    uid = str(user_id)
    digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return os.path.join(_journal_dir(), f"{digest}.json")


def _write_journal(user_id: str, record: dict) -> None:
    from utils.core.atomic_write import write_atomic
    path = _journal_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, json.dumps(record, indent=2))


def _read_journal(user_id: str) -> dict | None:
    path = _journal_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot read pending housing transaction for {user_id}: {exc}"
        ) from exc
    if not isinstance(record, dict) or not record.get("transaction_id"):
        return None
    return record


def _clear_journal(user_id: str) -> None:
    from utils.core.atomic_write import write_atomic
    path = _journal_path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, "{}")


async def _replay_record_locked(user_id: str, record: dict) -> None:
    if record.get("version") != 1:
        raise RuntimeError(
            f"Unknown housing transaction version for {user_id}; refusing to discard it."
        )
    if str(record.get("user_id")) != str(user_id):
        raise RuntimeError("Housing transaction journal owner mismatch.")
    sheet = record.get("character_sheet")
    housing = record.get("housing")
    if (
        not isinstance(sheet, dict)
        or str(sheet.get("user_id")) != str(user_id)
        or not isinstance(housing, dict)
        or str(housing.get("user_id")) != str(user_id)
    ):
        raise RuntimeError("Housing transaction journal has invalid recovery snapshots.")

    # Snapshot replay is idempotent. Keep the journal until both writes succeed.
    from utils.ttrpg.character_manager import save as save_character
    from utils.ttrpg.housing import save_housing_async
    await save_character(copy.deepcopy(sheet))
    await save_housing_async(copy.deepcopy(housing))
    _clear_journal(user_id)


async def recover_pending_housing_transaction(user_id: str) -> bool:
    """Replay one player's pending character + housing snapshots, if present."""
    uid = str(user_id)
    async with _transaction_lock:
        record = _read_journal(uid)
        if not record:
            return False
        await _replay_record_locked(uid, record)
        return True


async def recover_all_pending_housing_transactions() -> int:
    """Recover all pending player/housing journals before bulk character reads."""
    async with _transaction_lock:
        directory = _journal_dir()
        if not os.path.isdir(directory):
            return 0
        recovered = 0
        for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    record = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Cannot read pending housing journal {path}: {exc}") from exc
            if not isinstance(record, dict) or not record.get("transaction_id"):
                continue
            uid = str(record.get("user_id") or "")
            if not uid or os.path.abspath(path) != os.path.abspath(_journal_path(uid)):
                raise RuntimeError("Housing transaction journal path/owner mismatch.")
            await _replay_record_locked(uid, record)
            recovered += 1
        return recovered


async def commit_character_housing(
    sheet: dict,
    housing: dict,
    *,
    action: str,
    character_lock_held: bool = False,
) -> None:
    """Durably commit an already-mutated character sheet and housing snapshot.

    Callers should perform validation and mutate both snapshots before
    invoking this function. A pending journal is written before either save.
    `character_lock_held=True` is only for character_manager.load's daily
    reset path, which already owns the manager's non-reentrant sheet lock.
    """
    if not isinstance(sheet, dict) or not isinstance(housing, dict):
        raise ValueError("housing transactions require character and housing dictionaries")
    uid = str(sheet.get("user_id") or "")
    if not uid or str(housing.get("user_id") or "") != uid:
        raise ValueError("housing transaction snapshots must have the same user_id")
    if not action:
        raise ValueError("housing transaction requires an action name")

    async with _transaction_lock:
        # A previous interrupted action must be resolved before newer snapshots
        # for this player can replace its journal.
        pending = _read_journal(uid)
        if pending:
            await _replay_record_locked(uid, pending)

        import time
        record = {
            "version": 1,
            "transaction_id": f"{uid}:{time.time_ns()}",
            "user_id": uid,
            "action": str(action),
            "character_sheet": copy.deepcopy(sheet),
            "housing": copy.deepcopy(housing),
        }
        _write_journal(uid, record)

        from utils.ttrpg.housing import save_housing_async
        if character_lock_held:
            # The caller is character_manager.load itself, before returning its
            # sheet. Bypass the non-reentrant async manager lock, but retain its
            # thread-safe atomic file writer.
            from utils.ttrpg.character_manager import _save_sync
            await asyncio.to_thread(_save_sync, copy.deepcopy(sheet))
        else:
            from utils.ttrpg.character_manager import save as save_character
            await save_character(copy.deepcopy(sheet))
        await save_housing_async(copy.deepcopy(housing))
        _clear_journal(uid)
