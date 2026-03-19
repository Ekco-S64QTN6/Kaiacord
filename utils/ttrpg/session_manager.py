import os
import json
import time
import threading
import asyncio
from typing import Dict

SESSIONS_DIR = os.path.join("memory", "ttrpg", "sessions")
_lock = threading.Lock()
_chan_locks: Dict[str, asyncio.Lock] = {}
_chan_global_lock = asyncio.Lock()

async def get_session_lock(channel_id: str) -> asyncio.Lock:
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
        return await asyncio.to_thread(_load_session_sync, channel_id)

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
        await asyncio.to_thread(_save_session_sync, session)

async def create_session(channel_id: str, scene: str) -> dict:
    session = {
        "channel_id": channel_id,
        "active": True,
        "scene_summary": scene,
        "participants": [],
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
