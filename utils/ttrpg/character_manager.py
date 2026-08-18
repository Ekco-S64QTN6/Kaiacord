"""
Load, save, and create character sheets.
All I/O is synchronous — wrap in asyncio.to_thread at the manager level.
"""
import os
import json
import time
import threading
import asyncio
import functools
from typing import Optional, Dict, Any, List

CHARACTERS_DIR = os.path.join("memory", "ttrpg", "characters")
_lock = threading.Lock()  # Protects internal file I/O
_user_locks: Dict[str, asyncio.Lock] = {} # Protects read-modify-write per user
_global_lock = asyncio.Lock()  # Protects access to the _user_locks dict

INVENTORY_LIMIT = 100

def _path(user_id: str) -> str:
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    return os.path.join(CHARACTERS_DIR, f"{user_id}.json")

async def get_user_lock(user_id: str) -> asyncio.Lock:
    """Return an asyncio.Lock dedicated to this user's character sheet."""
    async with _global_lock:
        if user_id not in _user_locks:
            _user_locks[user_id] = asyncio.Lock()
        return _user_locks[user_id]

def _migrate_inventory(sheet: Dict[str, Any]) -> None:
    """Normalize legacy equipment keys to their current registry keys."""
    legacy_map = {
        "hand_axe": "rusty_hand_axe", "stiletto": "rusty_stiletto",
        "mace": "rusty_mace", "spear": "iron_spear",
        "battle_axe": "iron_battle_axe", "morning_star": "iron_morning_star",
        "longsword": "steel_longsword", "steel_blade": "steel_dagger",
        "defender": "flame_scepter"
    }
    if "inventory" in sheet and isinstance(sheet["inventory"], list):
        for i, item in enumerate(sheet["inventory"]):
            if item in legacy_map:
                sheet["inventory"][i] = legacy_map[item]
        sheet["inventory"] = list(sheet["inventory"])
    else:
        sheet["inventory"] = list()
        
    if "equipment" in sheet and isinstance(sheet["equipment"], dict):
        for slot, item_data in sheet["equipment"].items():
            if isinstance(item_data, dict) and item_data.get("key") in legacy_map:
                new_key = legacy_map[item_data["key"]]
                from utils.ttrpg.equipment_registry import get_equipment
                new_eq = get_equipment(new_key)
                if new_eq:
                    sheet["equipment"][slot] = new_eq

def _migrate_hp_bonuses(sheet: Dict[str, Any]) -> None:
    """Retroactively apply HP bonuses for currently equipped tier 4-5 gear."""
    if sheet.get("_hp_migrated_v2"): return
    
    hp_to_add = 0
    if "equipment" in sheet and isinstance(sheet["equipment"], dict):
        from utils.ttrpg.equipment_registry import get_equipment
        for slot, item_data in sheet["equipment"].items():
            if not item_data: continue
            item_key = item_data.get("key") if isinstance(item_data, dict) else item_data
            # Re-fetch from registry to get latest hp_bonus
            reg_item = get_equipment(item_key)
            if reg_item:
                hp_to_add += reg_item.get("hp_bonus", 0)
                # Update the stored equipment dict to include the new bonus field
                if isinstance(item_data, dict):
                    sheet["equipment"][slot] = reg_item
    
    if hp_to_add > 0:
        if "hp" in sheet and isinstance(sheet["hp"], dict):
            sheet["hp"]["max"] += hp_to_add
            sheet["hp"]["current"] += hp_to_add
        
    sheet["_hp_migrated_v2"] = True

def _migrate_quests(sheet: Dict[str, Any]) -> None:
    """Migrate from single active_quest string to active_quests list."""
    if "active_quests" not in sheet:
        sheet["active_quests"] = []
    
    if "active_quest" in sheet:
        old_quest = sheet.pop("active_quest")
        if old_quest and old_quest not in sheet["active_quests"]:
            sheet["active_quests"].append(old_quest)

def _load_sync(user_id: str) -> Optional[Dict[str, Any]]:
    p = _path(user_id)
    if not os.path.exists(p):
        return None
    with _lock:
        with open(p, 'r', encoding='utf-8') as f:
            sheet = json.load(f)
            _migrate_inventory(sheet)
            _migrate_hp_bonuses(sheet)
            _migrate_quests(sheet)
            return sheet

async def load(user_id: str) -> Optional[Dict[str, Any]]:
    """Async load with per-user locking. Applies daily reset if needed."""
    lock = await get_user_lock(user_id)
    async with lock:
        sheet = await asyncio.to_thread(functools.partial(_load_sync, user_id))
        if sheet:
            from datetime import date
            today = date.today().strftime("%Y-%m-%d")
            if sheet.get("hunts_reset_date") != today:
                from utils.ttrpg.progression import check_and_reset_hunts
                from utils.ttrpg.housing import load_housing
                housing = await asyncio.to_thread(functools.partial(load_housing, str(sheet.get("user_id", ""))))
                sheet = check_and_reset_hunts(sheet, housing=housing)
                await asyncio.to_thread(functools.partial(_save_sync, sheet))
        return sheet

async def load_all() -> List[Dict[str, Any]]:
    """Load every character sheet on disk. Returns a list of dicts."""
    return await asyncio.to_thread(_load_all_sync)

def _load_all_sync() -> List[Dict[str, Any]]:
    os.makedirs(CHARACTERS_DIR, exist_ok=True)
    sheets = []
    with _lock:
        for fname in os.listdir(CHARACTERS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(CHARACTERS_DIR, fname), 'r', encoding='utf-8') as f:
                    sheet = json.load(f)
                    _migrate_inventory(sheet)
                    _migrate_hp_bonuses(sheet)
                    _migrate_quests(sheet)
                    sheets.append(sheet)
            except (json.JSONDecodeError, OSError):
                continue
    return sheets

def _save_sync(sheet: Dict[str, Any]) -> None:
    p = _path(str(sheet["user_id"]))
    sheet["last_updated"] = time.time()
    tmp = p + ".tmp"
    with _lock:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(sheet, f, indent=2)
        os.replace(tmp, p)

async def save(sheet: Dict[str, Any]) -> None:
    """Async save with per-user locking."""
    user_id = str(sheet["user_id"])
    lock = await get_user_lock(user_id)
    async with lock:
        await asyncio.to_thread(functools.partial(_save_sync, sheet))

async def create(user_id: str, user_name: str, character_name: str,
           race: str, class_name: str, stats: Dict[str, int]) -> Dict[str, Any]:
    """Create a new character sheet with rolled/assigned stats."""
    user_id = str(user_id)
    lock = await get_user_lock(user_id)
    async with lock:
        return await asyncio.to_thread(functools.partial(
            _create_sync, user_id, user_name, character_name, race, class_name, stats
        ))


def _create_sync(user_id: str, user_name: str, character_name: str,
           race: str, class_name: str, stats: Dict[str, int]) -> Dict[str, Any]:
    """Synchronous internal creation logic."""
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
        "hunts_today": 0,
        "hunts_reset_date": datetime.date.today().strftime("%Y-%m-%d"),
        "skills": [],
        "inventory": ["adventurers_pack"],
        "conditions": [],
        "deaths": 0,
        "active_quests": [],
        "completed_quests": [],
        "quest_progress": {},
        "recipes": [], # Learned alchemy recipes
        "rank": "Novice",
        "reputation": 0,
        "bank_balance": 0,
        "npc_last_topic": {},
        "created_at": time.time(),
        "last_updated": time.time(),
    }
    
    # Class-specific starting gear — head/boots/accessory start as None (must be found or bought)
    _base_eq = {"weapon": None, "armor": None, "offhand": None,
                "head": None, "boots": None, "accessory": None}
    if class_name == "Warrior":
        sheet["equipment"] = {**_base_eq, "weapon": "hand_axe",    "armor": "leather_armor"}
    elif class_name == "Ranger":
        sheet["equipment"] = {**_base_eq, "weapon": "shortbow",     "armor": "leather_armor"}
    elif class_name == "Mage":
        sheet["equipment"] = {**_base_eq, "weapon": "wooden_staff", "armor": "mages_robe"}
    elif class_name == "Rogue":
        sheet["equipment"] = {**_base_eq, "weapon": "rusty_dagger", "armor": "leather_armor"}
    elif class_name == "Cleric":
        sheet["equipment"] = {**_base_eq, "weapon": "wooden_staff", "armor": "leather_armor"}
    else:
        sheet["equipment"] = _base_eq.copy()
        
    _save_sync(sheet)
    return sheet

def format_sheet(sheet: Dict[str, Any]) -> str:
    """Format character sheet for Discord display."""
    s = sheet["stats"]
    mod = lambda v: f"+{(v-10)//2}" if (v-10)//2 >= 0 else str((v-10)//2)
    
    from utils.ttrpg.progression import xp_to_next_level
    xp_next = xp_to_next_level(sheet["level"])
    xp_bar = f"{sheet['xp']}/{xp_next}" if xp_next else f"{sheet['xp']} (max level)"
    
    from utils.ttrpg.progression import hunts_remaining, get_max_hunts
    
    gil = sheet.get("gil", 0)
    bank = sheet.get("bank_balance", 0)
    loc = sheet.get("location", "oakhaven")
    loc_name = loc.replace("_", " ").title()
    hunts_rem = hunts_remaining(sheet)
    
    from utils.ttrpg.equipment_registry import WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES

    def _resolve_eq_name(slot_val, registry, fallback):
        if not slot_val:
            return fallback
        if isinstance(slot_val, dict):
            return slot_val.get("name", fallback)
        return registry.get(slot_val, {}).get("name", fallback)

    eq = sheet.get("equipment", {})
    w_name  = _resolve_eq_name(eq.get("weapon"),    WEAPONS,     "Unarmed")
    a_name  = _resolve_eq_name(eq.get("armor"),     ARMOR,       "Unarmored")
    h_name  = _resolve_eq_name(eq.get("head"),      HEADGEAR,    "—")
    b_name  = _resolve_eq_name(eq.get("boots"),     BOOTS,       "—")
    ac_name = _resolve_eq_name(eq.get("accessory"), ACCESSORIES, "—")
    
    conditions = ", ".join(sheet.get("conditions", [])) if sheet.get("conditions") else "none"
    inventory = "\n  ".join(sheet.get("inventory", [])) if sheet.get("inventory") else "empty"
    skills = ", ".join(sheet.get("skills", [])) if sheet.get("skills") else "none"
    
    active_qs = sheet.get("active_quests", [])
    q_str = f"📜 **Quests:** {len(active_qs)} active" if active_qs else "📜 **Quests:** None"
    
    bank_line = f"  **Bank:** {bank}g" if bank > 0 else ""
    
    rep = sheet.get("reputation", 0)
    def get_rep_rank(r):
        if r >= 100: return "Hero"
        if r >= 50: return "Trusted"
        if r >= 20: return "Known"
        if r < -50: return "Outlaw"
        if r < -20: return "Unwelcome"
        return "Neutral"
    
    rep_str = f"**Reputation:** {get_rep_rank(rep)} ({rep})"
    
    return (
        f"⚔️ **{sheet['character_name']}** — {sheet.get('race', '')} {sheet['class']} Lv.{sheet['level']} | {loc_name}\n"
        f"**HP:** {sheet['hp']['current']}/{sheet['hp']['max']}  "
        f"**XP:** {xp_bar}  **Gil:** {gil}g{bank_line}\n"
        f"**Status:** {rep_str} | {q_str}\n"
        f"**Hunts:** {hunts_rem}/{get_max_hunts(sheet)} | **Medals:** {sheet.get('deaths', 0)} deaths\n"
        f"**Weapon:** {w_name}  **Armor:** {a_name}\n"
        f"**Head:** {h_name}  **Boots:** {b_name}  **Accessory:** {ac_name}\n"
        f"**Conditions:** {conditions}\n"
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


async def get_active_town_defenders(town_locations=None, within_hours=48):
    """Return character sheets for players plausibly present/active for a town event."""
    import time
    if town_locations is None:
        town_locations = {
            "oakhaven", "stone_hearth", "hemlocks_store",
            "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
            "housing_district", "tricklebrook_pond"
        }
    sheets = await load_all()
    now = time.time()
    cutoff = now - within_hours * 3600
    
    # Active within 48h window and alive in town
    defenders = [
        s for s in sheets
        if s.get("location") in town_locations
        and s.get("hp", {}).get("current", 0) > 0
        and s.get("last_updated", 0) >= cutoff
    ]
    
    # If fewer than 2 or to support small testing group, draft all living characters in town
    if len(defenders) < len(sheets):
        all_town = [
            s for s in sheets
            if s.get("location", "oakhaven") in town_locations
            and s.get("hp", {}).get("current", 0) > 0
        ]
        if all_town:
            defenders = all_town
        
    return defenders

