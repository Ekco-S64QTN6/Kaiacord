"""
Load, save, and create character sheets.
All I/O is synchronous — wrap in asyncio.to_thread at the handler level.
"""
import os
import json
import time
import threading
from typing import Optional

CHARACTERS_DIR = os.path.join("memory", "ttrpg", "characters")
_lock = threading.Lock()

def _path(user_id: str) -> str:
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    return os.path.join(CHARACTERS_DIR, f"{user_id}.json")

def load(user_id: str) -> Optional[dict]:
    p = _path(user_id)
    if not os.path.exists(p):
        return None
    with _lock:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)

def load_all() -> list:
    """Load every character sheet on disk. Returns a list of dicts."""
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    sheets = []
    for fname in os.listdir(CHARACTERS_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHARACTERS_DIR, fname), 'r', encoding='utf-8') as f:
                sheets.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return sheets

def save(sheet: dict) -> None:
    p = _path(str(sheet["user_id"]))
    sheet["last_updated"] = time.time()
    tmp = p + ".tmp"
    with _lock:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(sheet, f, indent=2)
        os.replace(tmp, p)

def create(user_id: str, user_name: str, character_name: str,
           race: str, class_name: str, stats: dict) -> dict:
    """Create a new character sheet with rolled/assigned stats."""
    from utils.ttrpg.dice_engine import CLASSES
    
    if class_name not in CLASSES:
        raise ValueError(f"Unknown class: {class_name}")
    
    con_mod = (stats["con"] - 10) // 2
    hp_die = CLASSES[class_name]["hp_die"]
    max_hp = max(2, hp_die + con_mod + 1)  # Level 1 HP = hp_die + CON mod + level
    
    import datetime
    sheet = {
        "user_id": user_id,
        "user_name": user_name,
        "character_name": character_name,
        "race": race,
        "class": class_name,
        "level": 1,
        "xp": 0,
        "hp": {"current": max_hp, "max": max_hp},
        "stats": stats,
        "gil": 50,
        "location": "oakhaven",
        "equipment": {
            "weapon": None,
            "armor": None,
            "offhand": None
        },
        "hunts_today": 0,
        "hunts_reset_date": datetime.date.today().strftime("%Y-%m-%d"),
        "skills": [],
        "inventory": ["adventurers_pack"],
        "conditions": [],
        "deaths": 0,
        "active_quest": None,
        "completed_quests": [],
        "quest_progress": {},
        "recipes": [], # Learned alchemy recipes
        "created_at": time.time(),
        "last_updated": time.time(),
    }
    save(sheet)
    return sheet

def format_sheet(sheet: dict) -> str:
    """Format character sheet for Discord display."""
    s = sheet["stats"]
    mod = lambda v: f"+{(v-10)//2}" if (v-10)//2 >= 0 else str((v-10)//2)
    
    from utils.ttrpg.progression import xp_to_next_level
    xp_next = xp_to_next_level(sheet["level"])
    xp_bar = f"{sheet['xp']}/{xp_next}" if xp_next else f"{sheet['xp']} (max level)"
    
    from utils.ttrpg.progression import hunts_remaining, MAX_HUNTS_PER_DAY
    
    gil = sheet.get("gil", 0)
    loc = sheet.get("location", "oakhaven")
    loc_name = loc.replace("_", " ").title()
    hunts_rem = hunts_remaining(sheet)
    
    eq = sheet.get("equipment", {})
    w_name = eq.get("weapon", {}).get("name", "None") if eq.get("weapon") else "Unarmed"
    a_name = eq.get("armor", {}).get("name", "None") if eq.get("armor") else "Unarmored"
    
    conditions = ", ".join(sheet.get("conditions", [])) if sheet.get("conditions") else "none"
    inventory = "\n  ".join(sheet.get("inventory", [])) if sheet.get("inventory") else "empty"
    skills = ", ".join(sheet.get("skills", [])) if sheet.get("skills") else "none"
    
    active_q = sheet.get("active_quest")
    q_str = f"📜 **Quest:** {active_q.replace('_', ' ').title()}" if active_q else "📜 **Quest:** None"
    
    return (
        f"⚔️ **{sheet['character_name']}** — {sheet.get('race', '')} {sheet['class']} Lv.{sheet['level']} | {loc_name}\n"
        f"**HP:** {sheet['hp']['current']}/{sheet['hp']['max']}  "
        f"**XP:** {xp_bar}  **Gil:** {gil}g\n"
        f"**Hunts Remaining:** {hunts_rem}/{MAX_HUNTS_PER_DAY}\n"
        f"**Weapon:** {w_name}  **Armor:** {a_name}\n"
        f"**Conditions:** {conditions} | {q_str}\n"
        f"```\n"
        f"STR {s['str']:2d} ({mod(s['str'])})  "
        f"DEX {s['dex']:2d} ({mod(s['dex'])})  "
        f"CON {s['con']:2d} ({mod(s['con'])})\n"
        f"INT {s['int']:2d} ({mod(s['int'])})  "
        f"WIS {s['wis']:2d} ({mod(s['wis'])})  "
        f"CHA {s['cha']:2d} ({mod(s['cha'])})\n"
        f"```\n"
        f"**Skills:** {skills}\n"
        f"**Inventory:**\n  {inventory}"
    )
