"""
XP thresholds and level-up logic. All deterministic.
"""

ACTION_XP = {
    "CRITICAL_SUCCESS": 15,
    "SUCCESS":          10,
    "FAILURE":           5,
    "CRITICAL_FAILURE":  5,
}

COMBAT_TIERS = {
    "trivial": 25,
    "easy":    50,
    "medium":  100,
    "hard":    200,
    "deadly":  500,
}

XP_THRESHOLDS = {
    1:  0,      2:  300,    3:  900,    4:  2700,
    5:  6500,   6:  14000,  7:  23000,  8:  34000,
    9:  48000,  10: 64000,
}

# Increased HP per level — characters need to survive dungeon bosses
HP_PER_LEVEL = {
    "Warrior": 8,   # was 6
    "Ranger":  7,   # was 5
    "Mage":    5,   # was 4
    "Rogue":   5,   # was 4
    "Cleric":  6,   # was 5
}

MAX_HUNTS_PER_DAY = 5


def xp_to_next_level(current_level: int) -> int:
    """Return XP needed for the next level, or 0 if max."""
    return XP_THRESHOLDS.get(current_level + 1, 0)


def check_level_up(sheet: dict) -> tuple[bool, int]:
    """
    Returns (leveled_up, new_level).
    Mutates sheet in place if leveled up.
    Also triggers class advancement prompt at level 5.
    """
    level = sheet["level"]
    xp = sheet["xp"]
    next_threshold = XP_THRESHOLDS.get(level + 1)

    if next_threshold is None or xp < next_threshold:
        return False, level

    new_level = level + 1
    sheet["level"] = new_level

    # Deterministic HP increase: half die + CON modifier (floor 1)
    con_mod = (sheet["stats"]["con"] - 10) // 2
    class_name = sheet["class"]
    hp_gain = max(1, HP_PER_LEVEL.get(class_name, 5) + con_mod)
    sheet["hp"]["max"] += hp_gain
    sheet["hp"]["current"] = min(sheet["hp"]["current"] + hp_gain, sheet["hp"]["max"])

    # Stat growth: stat choice at levels 4 and 8
    if new_level in (4, 8):
        sheet["_stat_choice_pending"] = True

    # Mark for class advancement at level 5 (if not already advanced)
    if new_level == 5 and not sheet.get("advanced_class"):
        sheet["_advancement_pending"] = True

    return True, new_level


def check_and_reset_hunts(sheet: dict) -> dict:
    """Reset daily hunts if it's a new day."""
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    if sheet.get("hunts_reset_date") != today:
        sheet["hunts_today"] = 0
        sheet["hunts_reset_date"] = today

        # Transfer the inn_rest buff from pending to active for the new day
        if sheet.get("inn_rest_pending", False):
            sheet["inn_rest_active_today"] = True
            sheet["inn_rest_pending"] = False
        else:
            sheet["inn_rest_active_today"] = False

        # Clear ale temp HP condition on day reset
        if "ale_warmth" in sheet.get("conditions", []):
            sheet["conditions"].remove("ale_warmth")
            sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - 3)
            sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

        # Clear ALL temporary event conditions on day reset
        # Only preserve permanent/quest-flag conditions
        PERMANENT_CONDITIONS = {"blessed", "mognet_pending"}
        conditions = sheet.get("conditions", [])
        sheet["conditions"] = [c for c in conditions if c in PERMANENT_CONDITIONS]

    return sheet


def get_max_hunts(sheet: dict) -> int:
    """Returns the maximum hunts available today, accounting for buffs."""
    sheet = check_and_reset_hunts(sheet)
    ale_bonus = 1 if "ale_warmth" in sheet.get("conditions", []) else 0
    rest_bonus = 1 if sheet.get("inn_rest_active_today") else 0
    return MAX_HUNTS_PER_DAY + ale_bonus + rest_bonus


def hunts_remaining(sheet: dict) -> int:
    """Returns how many hunts the player has left today."""
    sheet = check_and_reset_hunts(sheet)
    return max(0, get_max_hunts(sheet) - sheet.get("hunts_today", 0))


def get_character_title(sheet: dict) -> str:
    """Return the character's current earned title."""
    from utils.ttrpg.class_advancement import get_title
    return get_title(sheet)
