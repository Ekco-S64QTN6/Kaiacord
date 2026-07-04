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
                state = _cache.copy()
            else:
                with open(WORLD_STATE_PATH, "r", encoding="utf-8") as f:
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
            modified = False
            
            # atk_mod
            if state.get("atk_mod_expiry", 0) > 0 and now > state["atk_mod_expiry"]:
                state["atk_mod"] = 0
                state["atk_mod_expiry"] = 0
                modified = True
            # def_mod
            if state.get("def_mod_expiry", 0) > 0 and now > state["def_mod_expiry"]:
                state["def_mod"] = 0
                state["def_mod_expiry"] = 0
                modified = True
            # xp_mult
            if state.get("xp_mult_expiry", 0) > 0 and now > state["xp_mult_expiry"]:
                state["xp_mult"] = 1.0
                state["xp_mult_expiry"] = 0
                modified = True
            # gil_mult
            if state.get("gil_mult_expiry", 0) > 0 and now > state["gil_mult_expiry"]:
                state["gil_mult"] = 1.0
                state["gil_mult_expiry"] = 0
                modified = True
            # shop_price_mult
            if state.get("shop_price_mult_expiry", 0) > 0 and now > state["shop_price_mult_expiry"]:
                state["shop_price_mult"] = 1.0
                state["shop_price_mult_expiry"] = 0
                modified = True
            # forest_event_bonus
            if state.get("forest_event_bonus_expiry", 0) > 0 and now > state["forest_event_bonus_expiry"]:
                state["forest_event_bonus"] = 0.0
                state["forest_event_bonus_expiry"] = 0
                modified = True
            # blessing_window_until
            if state.get("blessing_window_until", 0) > 0 and now > state["blessing_window_until"]:
                state["blessing_window_until"] = 0
                modified = True
            # pilgrim_blessing_until
            if state.get("pilgrim_blessing_until", 0) > 0 and now > state["pilgrim_blessing_until"]:
                state["pilgrim_blessing_until"] = 0
                modified = True
            # encounter_mod
            if state.get("encounter_mod_expiry", 0) > 0 and now > state["encounter_mod_expiry"]:
                state["encounter_mod"] = {}
                state["encounter_mod_expiry"] = 0
                modified = True
                
            if modified:
                os.makedirs(os.path.dirname(WORLD_STATE_PATH), exist_ok=True)
                tmp = WORLD_STATE_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp, WORLD_STATE_PATH)
                _cache = state.copy()
                _cache_date = os.path.getmtime(WORLD_STATE_PATH)
                
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

async def async_load_world_state() -> Dict[str, Any]:
    import asyncio
    return await asyncio.to_thread(load_world_state)

async def async_save_world_state(state: Dict[str, Any]):
    import asyncio
    await asyncio.to_thread(save_world_state, state)

