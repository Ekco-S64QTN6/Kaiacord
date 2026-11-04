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


async def _save_resource_snapshot(user_id: str, resource_kind: str, resource_state: dict) -> None:
    """Persist the non-character side of a multi-file action snapshot."""
    snapshot = copy.deepcopy(resource_state)
    if resource_kind == "housing":
        from utils.ttrpg.housing import save_housing_async
        await save_housing_async(snapshot)
    elif resource_kind == "dungeon":
        from utils.ttrpg.dungeon import save_dungeon
        await save_dungeon(str(user_id), snapshot)
    elif resource_kind == "spine_dungeon":
        from utils.ttrpg.spine_dungeon import save_spine_dungeon
        await save_spine_dungeon(str(user_id), snapshot)
    else:
        raise RuntimeError(f"Unknown multi-file transaction resource: {resource_kind!r}")


async def _replay_record_locked(
    user_id: str, record: dict, *, character_lock_held: bool = False
) -> None:
    if record.get("version") != 1:
        raise RuntimeError(
            f"Unknown housing transaction version for {user_id}; refusing to discard it."
        )
    if str(record.get("user_id")) != str(user_id):
        raise RuntimeError("Housing transaction journal owner mismatch.")
    sheet = record.get("character_sheet")
    resource_kind = record.get("resource_kind", "housing")
    resource_state = record.get("resource_state", record.get("housing"))
    if not isinstance(sheet, dict) or str(sheet.get("user_id")) != str(user_id):
        raise RuntimeError("Multi-file transaction journal has an invalid character snapshot.")
    if resource_kind not in {"housing", "dungeon", "spine_dungeon"}:
        raise RuntimeError(f"Unknown multi-file transaction resource: {resource_kind!r}")
    if not isinstance(resource_state, dict):
        raise RuntimeError("Multi-file transaction journal has an invalid resource snapshot.")
    if resource_kind == "housing" and str(resource_state.get("user_id")) != str(user_id):
        raise RuntimeError("Housing transaction journal owner mismatch.")

    # Snapshot replay is idempotent. Keep the journal until both writes succeed.
    from utils.ttrpg.character_manager import save as save_character
    if character_lock_held:
        from utils.ttrpg.character_manager import _save_sync
        await asyncio.to_thread(_save_sync, copy.deepcopy(sheet))
    else:
        await save_character(copy.deepcopy(sheet))
    await _save_resource_snapshot(user_id, resource_kind, resource_state)
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


async def commit_character_resource(
    sheet: dict,
    resource_state: dict,
    *,
    resource_kind: str,
    action: str,
    character_lock_held: bool = False,
) -> None:
    """Durably commit a character sheet and one housing/dungeon resource snapshot.

    The write-ahead journal is durable before either JSON file is changed.
    Supported resource kinds are housing, dungeon and spine_dungeon.
    """
    if not isinstance(sheet, dict) or not isinstance(resource_state, dict):
        raise ValueError("multi-file transactions require dictionary snapshots")
    uid = str(sheet.get("user_id") or "")
    if not uid:
        raise ValueError("multi-file transaction requires a character user_id")
    if resource_kind not in {"housing", "dungeon", "spine_dungeon"}:
        raise ValueError(f"unsupported multi-file resource kind: {resource_kind!r}")
    if resource_kind == "housing" and str(resource_state.get("user_id") or "") != uid:
        raise ValueError("character and housing snapshots must have the same user_id")
    if not action:
        raise ValueError("multi-file transaction requires an action name")

    async with _transaction_lock:
        pending = _read_journal(uid)
        if pending:
            await _replay_record_locked(
                uid, pending, character_lock_held=character_lock_held
            )

        import time
        record = {
            "version": 1,
            "transaction_id": f"{uid}:{time.time_ns()}",
            "user_id": uid,
            "action": str(action),
            "resource_kind": resource_kind,
            "character_sheet": copy.deepcopy(sheet),
            "resource_state": copy.deepcopy(resource_state),
        }
        _write_journal(uid, record)

        if character_lock_held:
            # The caller is character_manager.load itself, before returning its
            # sheet. Bypass the non-reentrant async manager lock, but retain its
            # thread-safe atomic file writer.
            from utils.ttrpg.character_manager import _save_sync
            await asyncio.to_thread(_save_sync, copy.deepcopy(sheet))
        else:
            from utils.ttrpg.character_manager import save as save_character
            await save_character(copy.deepcopy(sheet))
        await _save_resource_snapshot(uid, resource_kind, resource_state)
        _clear_journal(uid)


async def commit_character_housing(
    sheet: dict,
    housing: dict,
    *,
    action: str,
    character_lock_held: bool = False,
) -> None:
    """Convenience wrapper for a character sheet + housing transaction."""
    await commit_character_resource(
        sheet,
        housing,
        resource_kind="housing",
        action=action,
        character_lock_held=character_lock_held,
    )


async def commit_character_dungeon(
    sheet: dict, dungeon_state: dict, *, action: str
) -> None:
    """Commit a character cost with its ordinary dungeon snapshot."""
    await commit_character_resource(
        sheet, dungeon_state, resource_kind="dungeon", action=action
    )


async def commit_character_spine_dungeon(
    sheet: dict, dungeon_state: dict, *, action: str
) -> None:
    """Commit a character cost with its Spine dungeon snapshot."""
    await commit_character_resource(
        sheet, dungeon_state, resource_kind="spine_dungeon", action=action
    )
