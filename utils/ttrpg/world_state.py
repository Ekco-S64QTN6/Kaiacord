import os
import json
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
    "last_tick": 0
}

def load_world_state() -> Dict[str, Any]:
    if not os.path.exists(WORLD_STATE_PATH):
        return DEFAULT_STATE.copy()
    try:
        with open(WORLD_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
            # Ensure all keys exist
            for k, v in DEFAULT_STATE.items():
                if k not in state:
                    state[k] = v
            return state
    except:
        return DEFAULT_STATE.copy()

def save_world_state(state: Dict[str, Any]):
    os.makedirs(os.path.dirname(WORLD_STATE_PATH), exist_ok=True)
    with open(WORLD_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def get_current_state() -> Dict[str, Any]:
    return load_world_state()

def calculate_next_state() -> Dict[str, Any]:
    import random
    new_state = DEFAULT_STATE.copy()
    
    # 1. Roll for Weather
    w_roll = random.random()
    if w_roll < 0.6: # 60% Clear
        new_state["weather"] = "clear"
        new_state["weather_desc"] = "The sky is a brilliant, cloudless blue."
    elif w_roll < 0.8: # 20% Overcast
        new_state["weather"] = "overcast"
        new_state["weather_desc"] = "A thick layer of grey clouds hangs low over the trees."
        new_state["atk_mod"] = -1
    elif w_roll < 0.95: # 15% Stormy
        new_state["weather"] = "stormy"
        new_state["weather_desc"] = "Thunder rumbles as rain lashes against the square."
        new_state["atk_mod"] = -2
        new_state["def_mod"] = -2
    else: # 5% Blood Moon (Aethelgard special)
        new_state["weather"] = "blood_moon"
        new_state["weather_desc"] = "The moon hangs bloated and crimson. The monsters are restless."
        new_state["atk_mod"] = 3
        new_state["xp_mult"] = 1.5
        
    # 2. Roll for World Event
    e_roll = random.random()
    if e_roll < 0.1: # 10% chance of event
        events = [
            ("resonance_surge", "A surge of ancient magic pulses through the ley lines (+2 ATK/DEF).", {"atk_mod": 2, "def_mod": 2}),
            ("hemlock_sale", "Old Man Hemlock is feeling generous today (Selling bonus).", {"gil_mult": 1.25}),
            ("whisper_thin", "The veil is thin. XP flows more freely (+25% XP).", {"xp_mult": 1.25}),
        ]
        ev_type, ev_desc, mods = random.choice(events)
        new_state["event"] = ev_type
        new_state["event_desc"] = ev_desc
        for k, v in mods.items():
            if k in new_state and isinstance(v, (int, float)):
                new_state[k] += v # additive
                
    return new_state
