import os
import json
import time
import threading

SESSIONS_DIR = os.path.join("memory", "ttrpg", "sessions")
_lock = threading.Lock()

def _path(channel_id: str) -> str:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"{channel_id}.json")

def load_session(channel_id: str) -> dict | None:
    p = _path(channel_id)
    if not os.path.exists(p):
        return None
    with _lock:
        with open(p, 'r') as f:
            return json.load(f)

def save_session(session: dict) -> None:
    p = _path(str(session["channel_id"]))
    tmp = p + ".tmp"
    with _lock:
        with open(tmp, 'w') as f:
            json.dump(session, f, indent=2)
        os.replace(tmp, p)

def create_session(channel_id: str, scene: str) -> dict:
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
    save_session(session)
    return session

def end_session(channel_id: str) -> None:
    session = load_session(channel_id)
    if session:
        session["active"] = False
        save_session(session)
