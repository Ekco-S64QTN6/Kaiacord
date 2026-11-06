import os
import json
import time
import threading
import asyncio
import copy
import functools
import inspect
from typing import Dict

from utils.infrastructure.monitoring.async_lock_metrics import (
    MeasuredAsyncLock,
    record_registry_lock_created,
)

SESSIONS_DIR = os.path.join("memory", "ttrpg", "sessions")
_lock = threading.Lock()
_chan_locks: Dict[str, asyncio.Lock] = {}
_chan_global_lock = asyncio.Lock()

# Distinct from the locks above, and it has to be. Those are held *inside*
# load_session() and again inside save_session(), and released in between — so
# each file write is atomic, which was never the problem. A combat round loads
# the session, resolves, waits on the model for narration, then saves; two
# rounds overlapping in that window both read the same state and the second
# save discards the first round's damage. Players saw HP go *up*: a Wyrm at
# 80/116 reappearing at 101/116, exactly the 21 damage that had just been
# dealt. This lock is held across the whole read-modify-write instead.
_action_locks: Dict[str, asyncio.Lock] = {}


async def get_action_lock(channel_id: str) -> asyncio.Lock:
    """Serialises whole gameplay actions in a channel, not single file writes."""
    async with _chan_global_lock:
        lock = _action_locks.get(channel_id)
        if lock is None:
            lock = MeasuredAsyncLock("rpg_action")
            _action_locks[channel_id] = lock
            record_registry_lock_created("rpg_action", len(_action_locks))
        return lock


def _action_keys(fn, args, kwargs):
    """(channel_id, user_id) for a gameplay action, from either handler shape.

    Two exist: `(ctx, msg, send, rest, uid, uname, is_owner)` for the command
    handlers and `(ctx_obj, interaction, uid, uname, is_owner)` for the dungeon
    views. Both name their user parameter `uid` and both carry a channel on the
    second positional argument, so bind the signature and read `uid` by name —
    an earlier version guessed by scanning positional args for a digit string,
    which silently found nothing and dropped the user lock entirely.
    """
    channel_id = str(getattr(getattr(args[1] if len(args) > 1 else None,
                                     "channel", None), "id", "")) or "unknown"
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        uid = bound.arguments.get("uid")
    except TypeError:
        uid = kwargs.get("uid")
    return channel_id, str(uid) if uid else None


def serialize_combat_action(fn):
    """Run one gameplay action at a time, for the whole read-modify-write.

    Two locks, always taken in the same order so they cannot deadlock against
    each other:

      channel — the session holds the monsters, shared by everyone at the table
      user    — the character sheet is per-user, and a channel lock does not
                protect it. The Use Item flow runs from an *ephemeral*
                interaction, so a potion drunk there and an attack in the party
                channel take two different channel locks and interleave their
                load/save on the same sheet file, which is the same corruption
                the channel lock was added to stop.

    Both must be different objects from the locks inside load()/save(), which
    are taken internally: asyncio.Lock is not reentrant, so reusing them would
    deadlock on the first save inside a guarded action.
    """
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        channel_id, uid = _action_keys(fn, args, kwargs)
        chan_lock = await get_action_lock(f"chan:{channel_id}")
        async with chan_lock:
            if uid:
                user_lock = await get_action_lock(f"user:{uid}")
                async with user_lock:
                    return await fn(*args, **kwargs)
            return await fn(*args, **kwargs)
    wrapper._serialized = True        # takes its own locks; callers must not hold the user lock
    return wrapper


def serialize_user_action(fn):
    """The player's lock only, for a handler that changes their sheet but not a
    shared session — a purchase, a sale, a cast. The same `user:` lock combat
    takes, so the two can't interleave; no channel lock, which a combat round
    holds through its narration. Called from buttons as well as commands, so
    the lock is taken here rather than in the dispatcher."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        _, uid = _action_keys(fn, args, kwargs)
        if not uid:
            return await fn(*args, **kwargs)
        async with await get_action_lock(f"user:{uid}"):
            return await fn(*args, **kwargs)
    wrapper._serialized = True
    return wrapper


def player_locked(uid: str):
    """serialize_user_action for a view callback: the callback closes over the
    player instead of taking them as a parameter, so the uid is given here.

        @player_locked(uid)
        async def _cb(interaction): ...
    """
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            async with await get_action_lock(f"user:{uid}"):
                return await fn(*args, **kwargs)
        return wrapper
    return deco


async def get_session_lock(channel_id: str) -> asyncio.Lock:
    """Guards a single session file read or write."""
    async with _chan_global_lock:
        lock = _chan_locks.get(channel_id)
        if lock is None:
            lock = MeasuredAsyncLock("rpg_session")
            _chan_locks[channel_id] = lock
            record_registry_lock_created("rpg_session", len(_chan_locks))
        return lock


def _path(channel_id: str) -> str:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{channel_id}.json")

def _load_session_sync(channel_id: str) -> dict | None:
    p = _path(channel_id)
    if not os.path.exists(p):
        return None
    with _lock:
        with open(p, 'r') as f:
            return json.load(f)

async def load_session(channel_id: str) -> dict | None:
    lock = await get_session_lock(channel_id)
    async with lock:
        return await asyncio.to_thread(functools.partial(_load_session_sync, channel_id))

def _write_session_sync(channel_id: str, text: str) -> None:
    from utils.core.atomic_write import write_atomic
    with _lock:
        write_atomic(_path(channel_id), text)

async def save_session(session: dict) -> None:
    chan_id = str(session["channel_id"])
    text = json.dumps(session, indent=2)      # on the caller's thread: the session is live
    lock = await get_session_lock(chan_id)
    async with lock:
        await asyncio.to_thread(_write_session_sync, chan_id, text)


async def apply_overworld_combat_update(
    outcome: dict, *, remove_monster: bool = False
) -> None:
    """Replay one player's change to a shared channel session.

    Sessions contain encounters for multiple players. Recovery patches only
    the named owner's stable monster IDs and appends the combat-log event once;
    it never restores a stale whole-session snapshot.
    """
    channel_id = str(outcome.get("channel_id") or "")
    owner_id = str(outcome.get("owner_id") or "")
    outcome_id = str(outcome.get("outcome_id") or "")
    monster_id = str(outcome.get("monster_id") or "")
    monster_ids = outcome.get("monster_ids")
    if not channel_id or not owner_id or not outcome_id:
        raise RuntimeError("Pending overworld update is missing its identity.")
    if not remove_monster and not monster_id:
        raise RuntimeError("Pending overworld round is missing its monster ID.")
    if monster_ids is not None and (
        not isinstance(monster_ids, list)
        or any(not str(value) for value in monster_ids)
    ):
        raise RuntimeError("Pending overworld escape has invalid monster IDs.")

    session = await load_session(channel_id)
    if not session:
        raise RuntimeError(
            f"Cannot recover overworld update: session {channel_id} is missing."
        )

    monsters = session.setdefault("monsters", [])
    if remove_monster:
        target_ids = {str(value) for value in (monster_ids or []) if str(value)}
        if monster_id:
            target_ids.add(monster_id)
        if target_ids:
            session["monsters"] = [
                monster for monster in monsters
                if not (
                    isinstance(monster, dict)
                    and str(monster.get("aggro_uid")) == owner_id
                    and str(monster.get("id", "")) in target_ids
                )
            ]
        else:
            # Compatibility with terminal outcomes written before stable spawn IDs.
            removed = False
            kept = []
            for monster in monsters:
                matches = (
                    isinstance(monster, dict)
                    and str(monster.get("aggro_uid")) == owner_id
                    and monster.get("key") == outcome.get("monster_key")
                    and monster.get("origin_location") == outcome.get("origin_location")
                )
                if matches and not removed:
                    removed = True
                else:
                    kept.append(monster)
            session["monsters"] = kept
        session["combat_active"] = bool(session["monsters"])
    else:
        monster_after = outcome.get("monster_after")
        if not isinstance(monster_after, dict):
            raise RuntimeError("Pending overworld round has no monster snapshot.")
        replaced = False
        for index, current in enumerate(monsters):
            if (
                isinstance(current, dict)
                and str(current.get("aggro_uid")) == owner_id
                and str(current.get("id", "")) == monster_id
            ):
                session["monsters"][index] = copy.deepcopy(monster_after)
                replaced = True
                break
        if not replaced:
            raise RuntimeError(
                f"Cannot recover overworld round: monster {monster_id} is missing."
            )

    log_entry = outcome.get("combat_log_entry")
    if isinstance(log_entry, dict):
        log_id = str(log_entry.get("outcome_id") or outcome_id)
        log = session.setdefault("combat_log", [])
        if not any(
            isinstance(entry, dict) and str(entry.get("outcome_id") or "") == log_id
            for entry in log
        ):
            entry = copy.deepcopy(log_entry)
            entry["outcome_id"] = log_id
            log.append(entry)

    await save_session(session)

async def create_session(channel_id: str, scene: str) -> dict:
    session = {
        "channel_id": channel_id,
        "active": True,
        "scene_summary": scene,
        "participants": [],
        "monsters": [],
        "combat_active": False,
        "turn_order": [],
        "current_turn_index": 0,
        "round": 0,
        "action_log": [],
        "created_at": time.time(),
        "last_action_at": time.time(),
    }
    await save_session(session)
    return session

async def end_session(channel_id: str) -> None:
    session = await load_session(channel_id)
    if session:
        session["active"] = False
        await save_session(session)
