import os
import json
import time
import threading
import asyncio
import functools
import inspect
from typing import Dict

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
        if channel_id not in _action_locks:
            _action_locks[channel_id] = asyncio.Lock()
        return _action_locks[channel_id]


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
    return wrapper


async def get_session_lock(channel_id: str) -> asyncio.Lock:
    """Guards a single session file read or write."""
    async with _chan_global_lock:
        if channel_id not in _chan_locks:
            _chan_locks[channel_id] = asyncio.Lock()
        return _chan_locks[channel_id]


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

def _save_session_sync(session: dict) -> None:
    p = _path(str(session["channel_id"]))
    tmp = p + ".tmp"
    with _lock:
        with open(tmp, 'w') as f:
            json.dump(session, f, indent=2)
        os.replace(tmp, p)

async def save_session(session: dict) -> None:
    chan_id = str(session["channel_id"])
    lock = await get_session_lock(chan_id)
    async with lock:
        await asyncio.to_thread(functools.partial(_save_session_sync, session))

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
