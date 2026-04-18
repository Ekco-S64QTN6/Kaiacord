import os
import json
import threading
from typing import Dict, Any

WORLD_STATE_PATH = os.path.join("memory", "ttrpg", "world_state.json")

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
    "last_tick": 0
}
_cache = None
_cache_date = 0.0
_lock = threading.Lock()

def load_world_state() -> Dict[str, Any]:
    global _cache, _cache_date
    with _lock:
        if not os.path.exists(WORLD_STATE_PATH):
            return DEFAULT_STATE.copy()
        try:
            mtime = os.path.getmtime(WORLD_STATE_PATH)
            if _cache and mtime <= _cache_date:
                return _cache.copy()
                
            with open(WORLD_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
                # Ensure all keys exist
                for k, v in DEFAULT_STATE.items():
                    if k not in state:
                        state[k] = v
                _cache = state
                _cache_date = mtime
                return state.copy()
        except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
            import sys
            print(f"[world_state] Failed to load {WORLD_STATE_PATH}: {e}", file=sys.stderr)
            return DEFAULT_STATE.copy()

def save_world_state(state: Dict[str, Any]):
    global _cache, _cache_date
    with _lock:
        os.makedirs(os.path.dirname(WORLD_STATE_PATH), exist_ok=True)
        tmp = WORLD_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, WORLD_STATE_PATH)
        _cache = state.copy()
        _cache_date = os.path.getmtime(WORLD_STATE_PATH)

def get_current_state() -> Dict[str, Any]:
    return load_world_state()

