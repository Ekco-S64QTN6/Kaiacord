"""
Class Advancement System
========================
At level 5, characters may choose an advanced specialization.
Advanced classes grant passive bonuses, unique titles, and flavor.

Base → Advanced A | Advanced B
Warrior     → Paladin      | Shadowknight
Ranger      → Hunter       | Warden
Mage        → Wizard       | Necromancer
Rogue       → Shadowblade  | Trickster
Cleric      → High Priest  | Shaman
"""
import secrets

# ── Class Proc Table ──────────────────────────────────────────────────────────
# Every class (base and advanced) has a proc that fires on hit.
# base=0.10  → 10% chance on a normal hit
# crit=0.50  → 50% chance on a critical hit
#
# Types:
#   "bonus_die"  → roll extra die and add to damage; die="weapon" copies weapon_die
#   "undead"     → same as bonus_die but only triggers against undead enemies
#   "heal"       → restore <heal> HP to the player on proc

CLASS_PROCS = {
    # ── Base classes ──────────────────────────────────────────────────────────
    "Warrior":      {"name": "Onslaught",       "type": "bonus_die", "die": "weapon", "base": 0.10, "crit": 0.50},
    "Ranger":       {"name": "True Shot",       "type": "bonus_die", "die": "weapon", "base": 0.10, "crit": 0.50},
    "Mage":         {"name": "Arcane Surge",    "type": "bonus_die", "die": 8,        "base": 0.10, "crit": 0.50},
    "Rogue":        {"name": "Backstab",        "type": "bonus_die", "die": "weapon", "base": 0.10, "crit": 0.50},
    "Cleric":       {"name": "Undead Bane",     "type": "undead",    "die": 6,        "base": 0.10, "crit": 0.50},
    # ── Advanced classes ──────────────────────────────────────────────────────
    "Paladin":      {"name": "Holy Smite",      "type": "undead",    "die": 8,        "base": 0.10, "crit": 0.50},
    "Shadowknight": {"name": "Harm Touch",      "type": "bonus_die", "die": 8,        "base": 0.10, "crit": 0.50},
    "Hunter":       {"name": "Predator",        "type": "bonus_die", "die": "weapon", "base": 0.10, "crit": 0.50},
    "Warden":       {"name": "Forest Fury",     "type": "bonus_die", "die": 8,        "base": 0.10, "crit": 0.50},
    "Wizard":       {"name": "Arcane Nova",     "type": "bonus_die", "die": 10,       "base": 0.10, "crit": 0.50},
    "Necromancer":  {"name": "Death Touch",     "type": "undead",    "die": 8,        "base": 0.10, "crit": 0.50},
    "Shadowblade":  {"name": "Shadow Strike",   "type": "bonus_die", "die": "weapon", "base": 0.10, "crit": 0.50},
    "Trickster":    {"name": "Lucky Break",     "type": "bonus_die", "die": 6,        "base": 0.10, "crit": 0.50},
    "High Priest":  {"name": "Divine Touch",    "type": "heal",      "heal": 25,      "base": 0.10, "crit": 0.50},
    "Shaman":       {"name": "Spirit Wrath",    "type": "bonus_die", "die": 8,        "base": 0.10, "crit": 0.50},
}

_UNDEAD_NAMES = {
    "skeleton", "zombie", "ghoul", "ghost", "lich", "revenant", "wight",
    "spectre", "skull knight", "dark knight", "shadow lich", "dullahan",
    "decaying skeleton", "tonberry king", "elara (turned)",
}

PROC_EMOJIS = {
    "Warrior":      "⚔️",
    "Ranger":       "🎯",
    "Mage":         "🔮",
    "Rogue":        "🗡️",
    "Cleric":       "✝️",
    "Paladin":      "🌟",
    "Shadowknight": "🩸",
    "Hunter":       "🏹",
    "Warden":       "🌿",
    "Wizard":       "💫",
    "Necromancer":  "💀",
    "Shadowblade":  "🌑",
    "Trickster":    "🍀",
    "High Priest":  "☀️",
    "Shaman":       "🌀",
}

def resolve_class_proc(sheet: dict, weapon_die: int, player_crit: bool, monster: dict) -> dict:
    """
    Roll and resolve a class-based proc for one combat hit.

    Returns a dict:
        proc_triggered  bool
        proc_name       str
        proc_damage     int   (extra damage to add)
        proc_heal       int   (HP to restore to player)
        proc_log        list[str]
    """
    result = {
        "proc_triggered": False,
        "proc_name": "",
        "proc_damage": 0,
        "proc_heal": 0,
        "proc_log": [],
    }

    adv  = sheet.get("advanced_class", "")
    base = sheet.get("class", "Warrior")
    # Advanced class takes priority; "stay" classes keep the base proc
    active_class = adv if (adv and adv != base) else base

    proc = CLASS_PROCS.get(active_class)
    if not proc:
        return result

    proc_type = proc["type"]

    # Undead procs: only fire against undead — check before rolling RNG
    if proc_type == "undead":
        m_name = monster.get("name", "").lower()
        if not any(u in m_name for u in _UNDEAD_NAMES):
            return result

    # Roll proc chance
    chance = proc["crit"] if player_crit else proc["base"]
    if secrets.randbelow(100) >= int(chance * 100):
        return result

    result["proc_triggered"] = True
    result["proc_name"] = proc["name"]
    
    icon = PROC_EMOJIS.get(active_class, "⚡")

    if proc_type in ("bonus_die", "undead"):
        die = proc["die"]
        if die == "weapon":
            die = weapon_die
        extra = secrets.randbelow(die) + 1
        result["proc_damage"] = extra
        result["proc_log"].append(
            f"{icon} **{proc['name']}!** +{extra} bonus damage (1d{die})"
        )

    elif proc_type == "heal":
        result["proc_heal"] = proc["heal"]
        result["proc_log"].append(
            f"{icon} **{proc['name']}!** Restored {proc['heal']} HP"
        )

    return result

ADVANCED_CLASSES = {
    "Warrior": {
        "Warrior": {
            "description": "Master of arms. Onslaught proc on every hit.",
            "bonuses": {
                "atk_bonus": 1,
                "def_bonus": 1,
                "hp_bonus": 5,
            },
            "flavor": "You don't need a new name. The old one was enough.",
            "is_stay": True,
        },
        "Paladin": {
            "description": "Holy warrior. Holy Smite proc vs undead. Heals on kill.",
            "bonuses": {
                "atk_vs_undead": 2,
                "heal_on_kill": 3,
                "def_bonus": 1,
                "hp_bonus": 5,
            },
            "flavor": "Aerthis acknowledges your oath. The flame at the Shrine burns white-blue.",
        },
        "Shadowknight": {
            "description": "Dark blade. Harm Touch proc. Drains life on every hit.",
            "bonuses": {
                "lifesteal_pct": 0.15,
                "atk_bonus": 2,
                "hp_bonus": 5,
            },
            "flavor": "Morvenna is watching. The flame at the Shrine burns amber-black.",
        },
    },
    "Ranger": {
        "Ranger": {
            "description": "Seasoned tracker. True Shot proc on every hit. +1 daily hunt.",
            "bonuses": {
                "atk_bonus": 1,
                "extra_hunt": 1,
                "hp_bonus": 4,
            },
            "flavor": "The forest doesn't change. You do. That's the difference.",
            "is_stay": True,
        },
        "Hunter": {
            "description": "Predator proc on every hit. Extended crit range.",
            "bonuses": {
                "crit_threshold": 18,
                "atk_bonus": 2,
                "hp_bonus": 4,
            },
            "flavor": "The forest edge accepts you as part of its pattern. Something shifts.",
        },
        "Warden": {
            "description": "Forest Fury proc on hit. Hard to kill — strong defense.",
            "bonuses": {
                "def_bonus": 3,
                "hp_bonus": 10,
                "forest_def_bonus": 2,
                "heal_on_combat_end": 5,
                "xp_bonus_pct": 0.10,
            },
            "flavor": "Thornax approves. The Whisperwood breathes with you.",
        },
    },
    "Mage": {
        "Mage": {
            "description": "Pure arcane focus. Arcane Surge proc on hit.",
            "bonuses": {
                "spell_atk_bonus": 2,
                "hp_bonus": 4,
            },
            "flavor": "The resonance hums louder now. You've always known. You just listen better.",
            "is_stay": True,
        },
        "Wizard": {
            "description": "INT drives all attack rolls. Arcane Nova proc (1d10).",
            "bonuses": {
                "int_to_atk": True,
                "spell_atk_bonus": 3,
                "hp_bonus": 4,
            },
            "flavor": "Sylvara tears open the door for you. The resonance sings aloud.",
        },
        "Necromancer": {
            "description": "Death Touch proc vs undead. Deep attunement to the dead.",
            "bonuses": {
                "atk_vs_undead": 3,
                "hp_bonus": 4,
            },
            "flavor": "Morvenna welcomes your final lesson. The Shrine goes dead quiet.",
        },
    },
    "Rogue": {
        "Rogue": {
            "description": "Survivor. Backstab proc on every hit.",
            "bonuses": {
                "atk_bonus": 1,
                "gil_bonus_pct": 0.10,
                "hp_bonus": 3,
            },
            "flavor": "You've survived this long without a title. That IS the title.",
            "is_stay": True,
        },
        "Shadowblade": {
            "description": "Shadow Strike proc on every hit. Crits on 17+.",
            "bonuses": {
                "crit_threshold": 17,
                "crit_damage_bonus": 4,
                "atk_bonus": 1,
                "hp_bonus": 3,
            },
            "flavor": "The knife feels lighter. The dark feels familiar in a way it didn't before.",
        },
        "Trickster": {
            "description": "Lucky Break proc on hit. Gil mastery. Gambling advantage.",
            "bonuses": {
                "gil_bonus_pct": 0.25,
                "gamble_edge": True,
                "hp_bonus": 3,
            },
            "flavor": "A moogle winks at you from a dark corner of the Stone Hearth. You don't question it.",
        },
    },
    "Cleric": {
        "Cleric": {
            "description": "Devoted healer. Undead Bane proc. Enhanced consumable healing.",
            "bonuses": {
                "heal_mult": 1.25,
                "def_bonus": 1,
                "hp_bonus": 4,
            },
            "flavor": "The flame doesn't change. But it burns a little steadier when you're near.",
            "is_stay": True,
        },
        "High Priest": {
            "description": "WIS drives attack rolls. Divine Touch proc — heals 25 HP on proc.",
            "bonuses": {
                "heal_mult": 1.5,
                "wis_to_atk": True,
                "hp_bonus": 4,
            },
            "flavor": "The flame at the Shrine burns three times as bright for a moment. Then settles.",
        },
        "Shaman": {
            "description": "Spirit Wrath proc on hit. Forest XP bonus. Passive heal on forest events.",
            "bonuses": {
                "forest_xp_bonus": 0.20,
                "def_bonus": 1,
                "nature_heal_on_event": 4,
                "hp_bonus": 4,
            },
            "flavor": "The Whisperwood acknowledges you as something more than a visitor. That distinction matters.",
        },
    },
}

# Title progression: base class and advanced class titles by level
TITLES = {
    # Base class titles (no advanced class chosen yet)
    "Warrior":     {1: "Grunt", 3: "Soldier", 5: "Veteran", 7: "Warlord", 9: "Champion"},
    "Ranger":      {1: "Scout", 3: "Tracker", 5: "Pathfinder", 7: "Outrider", 9: "Stalker"},
    "Mage":        {1: "Apprentice", 3: "Channeler", 5: "Invoker", 7: "Arcanist", 9: "Magister"},
    "Rogue":       {1: "Cutpurse", 3: "Shadow", 5: "Blade", 7: "Phantom", 9: "Wraith"},
    "Cleric":      {1: "Novice", 3: "Acolyte", 5: "Cleric", 7: "Devout", 9: "Saint"},
    # Advanced class titles
    "Paladin":        {5: "Initiate", 7: "Knight", 9: "Champion of Silence", 10: "Blessed Blade"},
    "Shadowknight":   {5: "Shade", 7: "Dread Knight", 9: "Deathbringer", 10: "Terror of the Ruins"},
    "Hunter":         {5: "Stalker", 7: "Predator", 9: "Apex Hunter", 10: "Legend of the Forest"},
    "Warden":         {5: "Keeper", 7: "Sentinel", 9: "Guardian of the Deep", 10: "Heart of Whisperwood"},
    "Wizard":         {5: "Scholar", 7: "Arcanist", 9: "Archmage", 10: "Resonance-Touched"},
    "Necromancer":    {5: "Student of Death", 7: "Bone Whisperer", 9: "Lich-Touched", 10: "Morvenna's Hand"},
    "Shadowblade":    {5: "Knife in the Dark", 7: "Ghost", 9: "Phantom", 10: "The Last Face You See"},
    "Trickster":      {5: "Scoundrel", 7: "Schemer", 9: "Legend", 10: "Myth and Rumor"},
    "High Priest":    {5: "Acolyte", 7: "Priest", 9: "Voice of the Silent", 10: "They Who Are Heard"},
    "Shaman":         {5: "Listener", 7: "Speaker", 9: "Worldsong", 10: "The Forest's Voice"},
}

# Special titles from achievements
SPECIAL_TITLES = [
    (lambda s: s.get("deaths", 0) >= 10, "the Unkillable"),
    (lambda s: s.get("deaths", 0) == 0 and s.get("level", 1) >= 5, "the Unmarked"),
    (lambda s: len(s.get("completed_quests", [])) >= 3, "the Proven"),
    (lambda s: s.get("reputation", 0) >= 100, "Hero of Oakhaven"),
    (lambda s: s.get("reputation", 0) < -50, "the Unwelcome"),
]


def _total_gil(sheet: dict) -> int:
    """Return combined on-hand + bank gil for a character sheet."""
    return sheet.get("gil", 0) + sheet.get("bank_balance", 0)


import time
_WEALTHIEST_CACHE = {"timestamp": 0, "uid": None}

def _is_wealthiest(sheet: dict) -> bool:
    """Check if this sheet's owner has the most total gil across all players (cached)."""
    import os, json
    my_uid = str(sheet.get("user_id", ""))
    now = time.time()
    
    # Cache hit check (60s TTL)
    if now - _WEALTHIEST_CACHE["timestamp"] < 60:
        return _WEALTHIEST_CACHE["uid"] == my_uid

    char_dir = os.path.join("memory", "ttrpg", "characters")
    if not os.path.isdir(char_dir):
        return False

    max_gil = 0
    richest_uid = None

    for fname in os.listdir(char_dir):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(char_dir, fname), "r") as f:
                other = json.load(f)
            total = _total_gil(other)
            if total > max_gil:
                max_gil = total
                richest_uid = str(other.get("user_id", fname[:-5]))
        except Exception:
            continue

    _WEALTHIEST_CACHE["timestamp"] = now
    _WEALTHIEST_CACHE["uid"] = richest_uid if max_gil >= 1000 else None
    
    return _WEALTHIEST_CACHE["uid"] == my_uid


def get_title(sheet: dict) -> str:
    """Return the character's current title string."""
    # Check special achievement titles first
    for check, title in SPECIAL_TITLES:
        try:
            if check(sheet):
                return title
        except Exception:
            pass

    # "the Wealthy" — awarded to the single richest player (on-hand + bank)
    if _is_wealthiest(sheet):
        return "the Wealthy"

    level = sheet.get("level", 1)
    advanced = sheet.get("advanced_class", "")
    base_class = sheet.get("class", "Warrior")

    # "Stay" classes (advanced_class == base_class) use the base title track
    if advanced and advanced != base_class:
        title_map = TITLES.get(advanced, {})
    else:
        title_map = TITLES.get(base_class, {})

    if not title_map:
        return "Adventurer"

    current = "Adventurer"
    for threshold in sorted(title_map.keys()):
        if level >= threshold:
            current = title_map[threshold]
    return current


def get_advanced_options(base_class: str) -> dict:
    return ADVANCED_CLASSES.get(base_class, {})


def apply_advanced_class_to_combat(sheet: dict, player_damage: int,
                                   player_hit: bool, player_crit: bool,
                                   monster_damage: int, monster: dict,
                                   monster_defeated: bool,
                                   location: str = None) -> dict:
    """
    Apply advanced class passive bonuses to a resolved combat exchange.
    Returns a dict of modifications:
      player_damage_bonus, monster_damage_reduction, heal_amount, extra_log
    """
    result = {
        "player_damage_bonus": 0,
        "monster_damage_reduction": 0,
        "heal_amount": 0,
        "extra_log": [],
    }

    advanced = sheet.get("advanced_class", "")
    if not advanced:
        return result

    bonuses = {}
    for base_opts in ADVANCED_CLASSES.values():
        if advanced in base_opts:
            bonuses = base_opts[advanced].get("bonuses", {})
            break

    if not bonuses:
        return result

    m_name_lower = monster.get("name", "").lower()
    UNDEAD_NAMES = {
        "skeleton", "zombie", "ghoul", "ghost", "lich", "revenant", "wight",
        "spectre", "skull knight", "dark knight", "shadow lich", "tonberry king",
        "necrophobe", "shadow dancer", "decaying skeleton",
    }
    is_undead = any(u in m_name_lower for u in UNDEAD_NAMES)

    # Paladin — smite undead, heal on kill
    if advanced == "Paladin":
        if player_hit and is_undead and bonuses.get("atk_vs_undead"):
            result["player_damage_bonus"] += bonuses["atk_vs_undead"]
            result["extra_log"].append(f"✝️ *Paladin's smite: +{bonuses['atk_vs_undead']} vs undead.*")
        if monster_defeated and bonuses.get("heal_on_kill"):
            result["heal_amount"] += bonuses["heal_on_kill"]
            result["extra_log"].append(f"✝️ *Holy kill restores {bonuses['heal_on_kill']} HP.*")

    # Shadowknight — lifesteal
    elif advanced == "Shadowknight":
        if player_damage > 0 and bonuses.get("lifesteal_pct"):
            steal = max(1, min(6, int(player_damage * bonuses["lifesteal_pct"])))
            result["heal_amount"] += steal
            result["extra_log"].append(f"🩸 *Lifesteal: +{steal} HP.*")

    # Necromancer — devastate undead
    elif advanced == "Necromancer":
        if player_hit and is_undead and bonuses.get("atk_vs_undead"):
            result["player_damage_bonus"] += bonuses["atk_vs_undead"]
            result["extra_log"].append(f"💀 *Death mastery: +{bonuses['atk_vs_undead']} vs undead.*")

    # Warden — forest defense
    elif advanced == "Warden":
        loc = location or sheet.get("location", "")
        if bonuses.get("forest_def_bonus") and loc in ("whisperwood_edge", "whisperwood_deep"):
            result["monster_damage_reduction"] += bonuses["forest_def_bonus"]
            if monster_damage > 0:
                result["extra_log"].append(f"🌲 *Warden's bark: -{bonuses['forest_def_bonus']} damage taken.*")

    # Cleric (stay) — enhanced healing (handled via heal_mult in combat_engine)
    elif advanced == "Cleric":
        pass  # heal_mult applied separately in combat_engine.py

    # Shaman — nature heal on event
    elif advanced == "Shaman":
        pass  # Applied separately in event handler

    return result


def apply_advanced_class_to_sheet(sheet: dict, advanced_class: str) -> dict:
    """Apply one-time stat bonuses when first gaining an advanced class."""
    options = get_advanced_options(sheet.get("class", ""))
    if advanced_class not in options:
        return sheet

    bonuses = options[advanced_class].get("bonuses", {})
    sheet["advanced_class"] = advanced_class

    # One-time HP bonuses
    if "hp_bonus" in bonuses:
        sheet["hp"]["max"] += bonuses["hp_bonus"]
        sheet["hp"]["current"] = min(
            sheet["hp"]["current"] + bonuses["hp_bonus"],
            sheet["hp"]["max"]
        )

    return sheet
