import os
import json
import threading
import asyncio
import copy
import time
from typing import Dict, Any, Callable, Tuple

WORLD_STATE_PATH = os.path.join("memory", "ttrpg", "world_state.json")


def _path() -> str:
    """The live file, or its .test twin under pytest. The suite wrote the real
    one: every run left the world on "test_storm" with a -5 attack modifier for
    every player until the next dawn tick."""
    from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
    return telemetry_path(WORLD_STATE_PATH)


DEFAULT_STATE = {
    "weather": "clear",
    "weather_desc": "The sky is a brilliant, cloudless blue.",
    "event": "none",
    "event_desc": "Oakhaven is peaceful today.",
    "atk_mod": 0,
    "def_mod": 0,
    "xp_mult": 1.0,
    "gil_mult": 1.0,
    "caravan_active": False,
    "blockade_active": False,
    "fishing_water_tainted": False,
    "watchtower_bonus": False,
    "special_item_sale": {},
    "last_tick": 0
}
_cache = None
_cache_date = 0.0
_lock = threading.Lock()

def load_world_state() -> Dict[str, Any]:
    global _cache, _cache_date
    path = _path()
    with _lock:
        if not os.path.exists(path):
            return DEFAULT_STATE.copy()
        try:
            mtime = os.path.getmtime(path)
            if _cache and mtime <= _cache_date:
                state = _cache.copy()
            else:
                with open(path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    # Ensure all keys exist
                    for k, v in DEFAULT_STATE.items():
                        if k not in state:
                            state[k] = v
                    _cache = state
                    _cache_date = mtime
                    state = state.copy()
            
            # Evaluate expiries
            import time
            now = time.time()
            
            # atk_mod
            if state.get("atk_mod_expiry", 0) > 0 and now > state["atk_mod_expiry"]:
                state["atk_mod"] = 0
                state["atk_mod_expiry"] = 0
            # def_mod
            if state.get("def_mod_expiry", 0) > 0 and now > state["def_mod_expiry"]:
                state["def_mod"] = 0
                state["def_mod_expiry"] = 0
            # xp_mult
            if state.get("xp_mult_expiry", 0) > 0 and now > state["xp_mult_expiry"]:
                state["xp_mult"] = 1.0
                state["xp_mult_expiry"] = 0
            # gil_mult
            if state.get("gil_mult_expiry", 0) > 0 and now > state["gil_mult_expiry"]:
                state["gil_mult"] = 1.0
                state["gil_mult_expiry"] = 0
            # shop_price_mult
            if state.get("shop_price_mult_expiry", 0) > 0 and now > state["shop_price_mult_expiry"]:
                state["shop_price_mult"] = 1.0
                state["blockade_active"] = False
                state["shop_price_mult_expiry"] = 0
            # forest_event_bonus
            if state.get("forest_event_bonus_expiry", 0) > 0 and now > state["forest_event_bonus_expiry"]:
                state["forest_event_bonus"] = 0.0
                state["forest_event_bonus_expiry"] = 0
            # blessing_window_until
            if state.get("blessing_window_until", 0) > 0 and now > state["blessing_window_until"]:
                state["blessing_window_until"] = 0
            # pilgrim_blessing_until
            if state.get("pilgrim_blessing_until", 0) > 0 and now > state["pilgrim_blessing_until"]:
                state["pilgrim_blessing_until"] = 0
            # encounter_mod
            if state.get("encounter_mod_expiry", 0) > 0 and now > state["encounter_mod_expiry"]:
                state["encounter_mod"] = {}
                state["encounter_mod_expiry"] = 0
            # fishing_water_tainted
            if state.get("fishing_water_tainted_expiry", 0) > 0 and now > state["fishing_water_tainted_expiry"]:
                state["fishing_water_tainted"] = False
                state["fishing_water_tainted_expiry"] = 0
            # watchtower_bonus
            if state.get("watchtower_bonus_expiry", 0) > 0 and now > state["watchtower_bonus_expiry"]:
                state["watchtower_bonus"] = False
                state["watchtower_bonus_expiry"] = 0
            # special_item_sale
            if state.get("special_item_sale_expiry", 0) > 0 and now > state["special_item_sale_expiry"]:
                state["special_item_sale"] = {}
                state["special_item_sale_expiry"] = 0
                
            # Expiry normalization is a read-time view, not a write. Persisting
            # it from this getter bypasses _transaction_lock and can race a
            # journaled read-modify-write, restoring stale values or losing keys.
            # The next explicit transaction persists its own fresh snapshot.
            return state.copy()
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
            # Logged, not printed: stderr is the terminal the dashboard draws on,
            # and a world state silently reset to defaults is worth seeing.
            from utils.infrastructure.logging.kaia_logger import log_warning
            log_warning(f"[world_state] Failed to load {path}, using defaults: {e}")
            return DEFAULT_STATE.copy()

def _write_world_state(state: Dict[str, Any], text: str):
    global _cache, _cache_date
    from utils.core.atomic_write import write_atomic
    path = _path()
    with _lock:
        write_atomic(path, text)
        _cache = state
        _cache_date = os.path.getmtime(path)


def save_world_state(state: Dict[str, Any]):
    """Synchronous snapshot writer for isolated tests/bootstrap only.

    Async production read-modify-write paths must use update_world_state() or
    mutate_world_state(); this function cannot serialize a read-modify-write.
    """
    _write_world_state(state.copy(), json.dumps(state, indent=2))

def get_current_state() -> Dict[str, Any]:
    return load_world_state()

async def _async_write_world_state_unlocked(state: Dict[str, Any]) -> None:
    """Write one already-serialized state while the caller owns _transaction_lock."""
    await asyncio.to_thread(_write_world_state, state.copy(), json.dumps(state, indent=2))


async def async_save_world_state(state: Dict[str, Any]):
    """Write a complete snapshot already prepared while owning _transaction_lock.

    Prefer update_world_state() for ordinary mutations: locking only the final
    write does not make a snapshot loaded before the lock fresh.
    """
    async with _transaction_lock:
        await _async_write_world_state_unlocked(state)



# Shared transaction lock: individual file locks above only protect one read or
# write. This lock spans load -> validate -> mutate -> journal -> both commits.
_transaction_lock = asyncio.Lock()


def _transaction_path() -> str:
    from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
    return telemetry_path(os.path.join("memory", "ttrpg", "world_state_pending.json"))


def _read_pending_transaction() -> dict | None:
    path = _transaction_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        # Never continue with a possibly half-committed shared action.
        raise RuntimeError(f"Cannot read pending world-state transaction: {exc}") from exc
    if record == {}:
        return None
    if not isinstance(record, dict) or not record.get("transaction_id"):
        raise RuntimeError(
            "Pending world-state transaction is malformed; refusing to continue."
        )
    return record


def _write_pending_transaction(record: dict) -> None:
    from utils.core.atomic_write import write_atomic
    path = _transaction_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, json.dumps(record, indent=2))


def _clear_pending_transaction() -> None:
    from utils.core.atomic_write import write_atomic
    path = _transaction_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, "{}")


async def _recover_pending_transaction_locked() -> bool:
    """Replay the one write-ahead transaction while _transaction_lock is held."""
    record = _read_pending_transaction()
    if not record:
        return False
    if record.get("version") != 1 or not isinstance(record.get("world_state"), dict):
        raise RuntimeError("Unknown pending world-state transaction version; refusing to discard it.")

    sheet = record.get("character_sheet")
    if not isinstance(sheet, dict) or not sheet.get("user_id"):
        raise RuntimeError("Pending world-state transaction has no recoverable character sheet.")

    # Both writes are snapshot replays and therefore idempotent. Keep the
    # journal until both destinations are durable.
    await _async_write_world_state_unlocked(record["world_state"])
    from utils.ttrpg.character_manager import save as save_character
    await save_character(sheet)
    _clear_pending_transaction()
    return True


async def recover_pending_world_state_transaction() -> bool:
    """Recover an interrupted world-state + character-sheet transaction."""
    async with _transaction_lock:
        return await _recover_pending_transaction_locked()


async def mutate_world_state(mutator: Callable[[dict, Dict[str, Any]], Tuple[bool, Any]], sheet: dict):
    """Serialize and durably commit one shared-world action and its character cost.

    The mutator receives (character_sheet, fresh_world_state) and returns
    (changed, result). It must be synchronous and must not perform I/O. A
    successful mutation is journaled before either JSON file is written. If
    the process stops between writes, the next character load replays both
    snapshots exactly once before allowing another action.

    Returning changed=False skips persistence, which lets callers report stale
    state or insufficient resources without writing either file.
    """
    if not isinstance(sheet, dict) or not sheet.get("user_id"):
        raise ValueError("world-state transactions require a character sheet with user_id")

    async with _transaction_lock:
        await _recover_pending_transaction_locked()
        state = load_world_state()
        changed, result = mutator(sheet, state)
        if not changed:
            return result

        transaction_id = f"{sheet['user_id']}:{time.time_ns()}"
        record = {
            "version": 1,
            "transaction_id": transaction_id,
            "user_id": str(sheet["user_id"]),
            "world_state": copy.deepcopy(state),
            "character_sheet": copy.deepcopy(sheet),
        }
        _write_pending_transaction(record)

        # Keep the durable journal until both snapshots have committed.
        await _async_write_world_state_unlocked(record["world_state"])
        from utils.ttrpg.character_manager import save as save_character
        await save_character(record["character_sheet"])
        _clear_pending_transaction()
        return result


async def update_world_state(mutator: Callable[[Dict[str, Any]], Any]) -> bool:
    """Apply one world-only mutation to a fresh snapshot under _transaction_lock.

    The lock covers recovery, load, validation/mutation, and the atomic write.
    Mutators must be synchronous, deterministic, and perform no I/O. Return
    False to reject/no-op without writing; any other return value commits the
    changed snapshot and this helper returns True.
    """
    async with _transaction_lock:
        await _recover_pending_transaction_locked()
        state = load_world_state()
        changed = mutator(state)
        if changed is False:
            return False
        await _async_write_world_state_unlocked(state)
        return True


async def mutate_world_state_only(mutator: Callable[[Dict[str, Any]], Any]) -> Any:
    """Apply an idempotent mutation whose retry is covered by an outer journal.

    The caller must persist its recovery record before invoking this helper.
    Ordinary world-only event writes should use update_world_state().
    """
    return await update_world_state(mutator)
