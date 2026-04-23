"""
Player Housing System — Aethelgard
Inspired by Ultima Online housing progression.
"""

HOUSING_DISTRICT_KEY = "housing_district"
PLAYER_PLOT_PREFIX = "plot_"

# ── Housing Tiers ─────────────────────────────────────────────────────────────
# Each tier unlocks more furniture slots, farming plots, and pet slots.

HOUSING_TIERS = {
    "hut": {
        "name": "Wattle Hut",
        "cost": 500,
        "upgrade_from": None,
        "desc": "A single-room wattle-and-daub hut on the outskirts of Oakhaven. It keeps the rain out. Mostly.",
        "emoji": "🛖",
        "furniture_slots": 5,
        "farming_plots": 1,
        "pet_slots": 1,
        "level_required": 1,
        "flavor": "The deed is warm from the clerk's hands. It's yours now. Small, but yours.",
    },
    "cottage": {
        "name": "Stone Cottage",
        "cost": 2500,
        "upgrade_from": "hut",
        "desc": "A proper stone cottage with a hearth, two rooms, and a garden wall.",
        "emoji": "🏡",
        "furniture_slots": 12,
        "farming_plots": 3,
        "pet_slots": 2,
        "level_required": 4,
        "flavor": "The mason finishes the last stone. The hearth draws well. This is a home now.",
    },
    "longhouse": {
        "name": "Oak Longhouse",
        "cost": 8000,
        "upgrade_from": "cottage",
        "desc": "A grand longhouse of seasoned oak. Wide enough to entertain. Strong enough to outlast you.",
        "emoji": "🏠",
        "furniture_slots": 25,
        "farming_plots": 6,
        "pet_slots": 3,
        "level_required": 6,
        "flavor": "The longhouse stands. The Whisperwood can see it from the treeline.",
    },
    "keep": {
        "name": "Oakhaven Keep",
        "cost": 25000,
        "upgrade_from": "longhouse",
        "desc": "Stone walls. Iron gates. A tower with a view of the Whisperwood canopy. This is legacy.",
        "emoji": "🏰",
        "furniture_slots": 50,
        "farming_plots": 12,
        "pet_slots": 5,
        "level_required": 8,
        "flavor": "The final stone is set at dusk. Elder Elara came to see it. She said nothing. That was the point.",
    },
}

TIER_ORDER = ["hut", "cottage", "longhouse", "keep"]

# ── Default Housing Sheet ──────────────────────────────────────────────────────

def default_housing_sheet(user_id: str, character_name: str, tier: str = "hut") -> dict:
    import time
    return {
        "user_id": user_id,
        "character_name": character_name,
        "tier": tier,
        "furniture": [],          # list of placed furniture keys
        "farming": {
            "plots": [],          # list of plot dicts: {slot, crop, planted_date, watered_today, stage}
        },
        "pets": [],               # list of pet dicts: {key, name, fed_today, days_owned}
        "visitors_today": [],     # user_ids who visited today (future: player shops)
        "house_name": f"{character_name}'s {HOUSING_TIERS[tier]['name']}",
        "created_at": time.time(),
        "last_updated": time.time(),
    }

# ── Persistence ────────────────────────────────────────────────────────────────

import os, json
import threading

HOUSING_DIR = os.path.join("memory", "ttrpg", "housing")
_lock = threading.Lock()

def _housing_path(user_id: str) -> str:
    os.makedirs(HOUSING_DIR, exist_ok=True)
    return os.path.join(HOUSING_DIR, f"{user_id}.json")

def load_housing(user_id: str) -> dict | None:
    p = _housing_path(str(user_id))
    with _lock:
        if not os.path.exists(p):
            return None
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    if data.get("last_farm_reset") != today:
        from utils.ttrpg.farming import reset_daily_farm
        from utils.ttrpg.pets import reset_daily_pets
        data = reset_daily_farm(data)
        data = reset_daily_pets(data)
        save_housing(data)
        
    return data

def save_housing(housing: dict) -> None:
    import time
    p = _housing_path(str(housing["user_id"]))
    housing["last_updated"] = time.time()
    tmp = p + ".tmp"
    with _lock:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(housing, f, indent=2)
        os.replace(tmp, p)

async def load_housing_async(user_id: str) -> dict | None:
    import asyncio
    return await asyncio.to_thread(load_housing, user_id)

async def save_housing_async(housing: dict) -> None:
    import asyncio
    await asyncio.to_thread(save_housing, housing)

def load_all_housing() -> list[dict]:
    os.makedirs(HOUSING_DIR, exist_ok=True)
    result = []
    with _lock:
        for fname in os.listdir(HOUSING_DIR):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(HOUSING_DIR, fname), 'r', encoding='utf-8') as f:
                        result.append(json.load(f))
                except Exception:
                    pass
    return result

def get_tier_data(tier_key: str) -> dict:
    return HOUSING_TIERS.get(tier_key, HOUSING_TIERS["hut"])

def get_next_tier(current_tier: str) -> str | None:
    idx = TIER_ORDER.index(current_tier)
    if idx + 1 < len(TIER_ORDER):
        return TIER_ORDER[idx + 1]
    return None

def can_afford_upgrade(sheet: dict, housing: dict) -> tuple[bool, str]:
    next_t = get_next_tier(housing["tier"])
    if not next_t:
        return False, "Your estate is already at maximum tier."
    tier_data = HOUSING_TIERS[next_t]
    if sheet["level"] < tier_data["level_required"]:
        return False, f"Requires Level {tier_data['level_required']}."
    if sheet["gil"] < tier_data["cost"]:
        return False, f"Costs {tier_data['cost']}g. You have {sheet['gil']}g."
    return True, ""
