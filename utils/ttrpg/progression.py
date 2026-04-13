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
    5:  5000,   6:  11000,  7:  23000,  8:  34000,
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
MAX_HUNTS_CEILING = 8  # Hard cap regardless of stacking (ale + inn + pet + class)

# Conditions preserved across daily resets (all others are cleared at dawn)
PERMANENT_CONDITIONS = {"blessed", "mognet_pending"}


def xp_to_next_level(current_level: int) -> int:
    """Return XP needed for the next level, or 0 if max."""
    return XP_THRESHOLDS.get(current_level + 1, 0)


def check_level_up(sheet: dict) -> tuple[bool, int]:
    """
    Returns (leveled_up, new_level).
    Mutates sheet in place if leveled up.
    Also triggers class advancement prompt at level 5.
    """
    leveled = False
    final_level = sheet["level"]
    
    while True:
        level = sheet["level"]
        next_threshold = XP_THRESHOLDS.get(level + 1)

        if next_threshold is None or sheet["xp"] < next_threshold:
            break

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
            
        leveled = True
        final_level = new_level

    # Check level 10 cap
    if final_level >= 10:
        final_level = 10
        sheet["level"] = 10
        cap_xp = XP_THRESHOLDS.get(10, 64000) + 1
        if sheet["xp"] > cap_xp:
            sheet["xp"] = cap_xp

    return leveled, final_level


def check_and_reset_hunts(sheet: dict, housing: dict = None) -> dict:
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
        sheet["hunts_today"] = 0
        from utils.ttrpg.progression import PERMANENT_CONDITIONS
        old_conds = sheet.get("conditions", [])
        sheet["conditions"] = [c for c in old_conds if c in PERMANENT_CONDITIONS]

        from utils.ttrpg.housing import load_housing, save_housing
        from utils.ttrpg.pets import reset_daily_pets
        from utils.ttrpg.farming import reset_daily_farm

        if housing is None:
            housing = load_housing(str(sheet.get("user_id", "")))
        if housing and housing.get("last_farm_reset") != today:
            housing = reset_daily_farm(housing)
            housing = reset_daily_pets(housing)
            save_housing(housing)
            
    return sheet


def get_max_hunts(sheet: dict, housing: dict = None) -> int:
    """Calculates the max hunts for a player, applying modifiers."""
    # Base buffs
    ale_bonus = 1 if "ale_warmth" in sheet.get("conditions", []) else 0
    rest_bonus = 1 if "rested" in sheet.get("conditions", []) else 0
    class_hunt_bonus = 0
    adv_class = sheet.get("advanced_class", "")
    if adv_class:
        from utils.ttrpg.class_advancement import ADVANCED_CLASSES
        for base_opts in ADVANCED_CLASSES.values():
            if adv_class in base_opts:
                class_hunt_bonus = base_opts[adv_class].get("bonuses", {}).get("extra_hunt", 0)
                break

    # Pet bonus (chocobo chick)
    from utils.ttrpg.pets import get_pet_passive
    if housing is None:
        from utils.ttrpg.housing import load_housing
        housing = load_housing(str(sheet.get("user_id", "")))
    pet_bonus = get_pet_passive(housing).get("extra_hunt", 0) if housing else 0

    # Items and random event temporary bonuses
    hunt_bonus = sum(1 for c in sheet.get("conditions", []) if c == "hunt_bonus")

    return min(MAX_HUNTS_CEILING, MAX_HUNTS_PER_DAY + ale_bonus + rest_bonus + pet_bonus + class_hunt_bonus + hunt_bonus)


def hunts_remaining(sheet: dict) -> int:
    """Returns how many hunts the player has left today."""
    from utils.ttrpg.housing import load_housing
    housing = load_housing(str(sheet.get("user_id", "")))
    
    sheet = check_and_reset_hunts(sheet, housing=housing)
    return max(0, get_max_hunts(sheet, housing=housing) - sheet.get("hunts_today", 0))


def get_character_title(sheet: dict) -> str:
    """Return the character's current earned title."""
    from utils.ttrpg.class_advancement import get_title
    return get_title(sheet)
