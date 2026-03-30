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

ADVANCED_CLASSES = {
    "Warrior": {
        "Warrior": {
            "description": "Master of arms. No tricks, just steel.",
            "bonuses": {
                "atk_bonus": 1,
                "def_bonus": 1,
                "hp_bonus": 5,
            },
            "flavor": "You don't need a new name. The old one was enough.",
            "is_stay": True,
        },
        "Paladin": {
            "description": "Holy warrior of the Silent Ones. Smites undead, heals on kill.",
            "bonuses": {
                "atk_vs_undead": 3,
                "heal_on_kill": 3,
                "def_bonus": 1,
            },
            "flavor": "You kneel at the Shrine and feel something ancient acknowledge you. The flame burns white for a moment.",
        },
        "Shadowknight": {
            "description": "Dark blade of Morvenna. Drains life, fears nothing.",
            "bonuses": {
                "lifesteal_pct": 0.20,
                "atk_bonus": 2,
                "bone_shield_on_kill": 3,
            },
            "flavor": "The flame at the Shrine gutters when you approach. You take that as a yes.",
        },
    },
    "Ranger": {
        "Ranger": {
            "description": "Seasoned tracker. Sharper senses, steadier aim.",
            "bonuses": {
                "atk_bonus": 1,
                "xp_bonus_pct": 0.05,
                "hp_bonus": 4,
            },
            "flavor": "The forest doesn't change. You do. That's the difference.",
            "is_stay": True,
        },
        "Hunter": {
            "description": "Precise predator. Critical range extended, first strike on entry.",
            "bonuses": {
                "crit_threshold": 18,
                "atk_bonus": 1,
                "xp_bonus_pct": 0.10,
            },
            "flavor": "The forest edge accepts you as part of its pattern. Something shifts.",
        },
        "Warden": {
            "description": "Guardian of the Whisperwood. Hard to kill, harder to wound.",
            "bonuses": {
                "def_bonus": 2,
                "hp_bonus": 8,
                "forest_def_bonus": 2,
            },
            "flavor": "Something old in the deep wood approves. The trees do not move but you sense them watching.",
        },
    },
    "Mage": {
        "Mage": {
            "description": "Pure arcane focus. Deeper reserves, stronger fundamentals.",
            "bonuses": {
                "spell_atk_bonus": 2,
                "hp_bonus": 4,
            },
            "flavor": "The resonance hums louder now. You've always known.<br>You just listen better.",
            "is_stay": True,
        },
        "Wizard": {
            "description": "Scholar of deep resonance. INT scales attack. Spells hit harder.",
            "bonuses": {
                "int_to_atk": True,
                "spell_atk_bonus": 3,
                "hp_bonus": 4,
            },
            "flavor": "The Aeridor resonance sings at a frequency you now understand. You wish you didn't.",
        },
        "Necromancer": {
            "description": "Student of Morvenna's final lesson. Undead fear you.",
            "bonuses": {
                "atk_vs_undead": 4,
                "death_resist": True,
                "bone_shield_passive": 4,
            },
            "flavor": "The Shrine of the Silent Ones goes very quiet when you make your choice.",
        },
    },
    "Rogue": {
        "Rogue": {
            "description": "Survivor. Quick hands, quicker feet.",
            "bonuses": {
                "atk_bonus": 1,
                "gil_bonus_pct": 0.10,
                "hp_bonus": 3,
            },
            "flavor": "You've survived this long without a title. That IS the title.",
            "is_stay": True,
        },
        "Shadowblade": {
            "description": "Ghost with a knife. Crits more, crits harder.",
            "bonuses": {
                "crit_threshold": 17,
                "crit_damage_bonus": 4,
                "atk_bonus": 1,
            },
            "flavor": "The knife feels lighter. The dark feels familiar in a way it didn't before.",
        },
        "Trickster": {
            "description": "Laughs at bad odds. Steals from the dead.",
            "bonuses": {
                "gil_bonus_pct": 0.25,
                "gamble_edge": True,
                "luck_charges": 2,
            },
            "flavor": "A moogle winks at you from a dark corner of the Stone Hearth. You don't question it.",
        },
    },
    "Cleric": {
        "Cleric": {
            "description": "Devoted healer. The old prayers still carry weight.",
            "bonuses": {
                "heal_mult": 1.25,
                "def_bonus": 1,
                "hp_bonus": 4,
            },
            "flavor": "The flame doesn't change. But it burns a little steadier when you're near.",
            "is_stay": True,
        },
        "High Priest": {
            "description": "Voice of the Silent Ones. Heals better, smites harder.",
            "bonuses": {
                "heal_mult": 1.5,
                "wis_to_atk": True,
                "shrine_offering_bonus": True,
            },
            "flavor": "The flame at the Shrine burns three times as bright for a moment. Then settles.",
        },
        "Shaman": {
            "description": "Reads the old signs. The Whisperwood fights alongside you.",
            "bonuses": {
                "forest_xp_bonus": 0.20,
                "def_bonus": 1,
                "weather_resist": True,
                "nature_heal_on_event": 4,
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
    (lambda s: s.get("gil", 0) >= 1000, "the Wealthy"),
    (lambda s: len(s.get("completed_quests", [])) >= 3, "the Proven"),
    (lambda s: s.get("reputation", 0) >= 100, "Hero of Oakhaven"),
    (lambda s: s.get("reputation", 0) < -50, "the Unwelcome"),
]


def get_title(sheet: dict) -> str:
    """Return the character's current title string."""
    # Check special achievement titles first
    for check, title in SPECIAL_TITLES:
        try:
            if check(sheet):
                return title
        except Exception:
            pass

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
                                   monster_defeated: bool) -> dict:
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
            steal = max(1, int(player_damage * bonuses["lifesteal_pct"]))
            result["heal_amount"] += steal
            result["extra_log"].append(f"🩸 *Lifesteal: +{steal} HP.*")

    # Necromancer — devastate undead
    elif advanced == "Necromancer":
        if player_hit and is_undead and bonuses.get("atk_vs_undead"):
            result["player_damage_bonus"] += bonuses["atk_vs_undead"]
            result["extra_log"].append(f"💀 *Death mastery: +{bonuses['atk_vs_undead']} vs undead.*")

    # Warden — forest defense
    elif advanced == "Warden":
        if bonuses.get("forest_def_bonus"):
            result["monster_damage_reduction"] += bonuses["forest_def_bonus"]
            if monster_damage > 0:
                result["extra_log"].append(f"🌲 *Warden's bark: -{bonuses['forest_def_bonus']} damage taken.*")

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
