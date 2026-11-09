"""
XP thresholds and level-up logic. All deterministic.
"""



# Set from measured XP a day at each level (tools/simulation/progression_sim.py
# --policy hunt): a daily hunter takes about a day a level at first and twelve
# for the last, about three months to the cap. The old table took 2-3 weeks
# each for levels 5, 6 and 9, and its 8→9 step was larger than 9→10.
XP_THRESHOLDS = {
    1:  0,      2:  200,    3:  500,    4:  900,
    5:  1400,   6:  2500,   7:  4500,   8:  8500,
    9:  16000,  10: 25000,  11: 38000,  12: 57000,
    13: 92000,  14: 136000, 15: 193000,
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
MAX_FREE_FOREST_EVENT_ATTEMPTS_PER_DAY = 5

# Conditions preserved across daily resets (all others are cleared at dawn)
PERMANENT_CONDITIONS = {"blessed", "mognet_pending", "rested"}


def xp_to_next_level(current_level: int) -> int:
    """Return XP needed for the next level, or 0 if max."""
    return XP_THRESHOLDS.get(current_level + 1, 0)


def retroactive_hp_gain_for_con_change(previous_con: int, new_con: int, level: int) -> int:
    """Return HP gained from a CON increase based on modifier change."""
    previous_mod = (int(previous_con) - 10) // 2
    new_mod = (int(new_con) - 10) // 2
    return max(0, new_mod - previous_mod) * max(0, int(level))


def queue_stat_choice(sheet: dict, level: int) -> None:
    """Persist one stat-growth choice for each earned milestone.

    Keep the legacy boolean for existing callers/UI while retaining a queue so
    multi-level XP gains cannot collapse several choices into one flag.
    A None entry represents one legacy pending choice whose milestone is unknown.
    """
    raw = sheet.get("_stat_choice_levels_pending")
    if isinstance(raw, list):
        pending = list(raw)
    else:
        pending = [None] if sheet.get("_stat_choice_pending") else []
    if level not in pending:
        pending.append(level)
    sheet["_stat_choice_levels_pending"] = pending
    sheet["_stat_choice_pending"] = bool(pending)


def consume_stat_choice(sheet: dict) -> bool:
    """Consume exactly one stat-growth choice; return whether more remain."""
    raw = sheet.get("_stat_choice_levels_pending")
    if isinstance(raw, list) and raw:
        pending = list(raw)
        pending.pop(0)
    elif sheet.get("_stat_choice_pending"):
        # Backward compatibility with saves/UI created before the queue existed.
        pending = []
    else:
        pending = []

    if pending:
        sheet["_stat_choice_levels_pending"] = pending
        sheet["_stat_choice_pending"] = True
        return True
    sheet.pop("_stat_choice_levels_pending", None)
    sheet.pop("_stat_choice_pending", None)
    return False


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

        # Stat growth: queue one independent choice for each milestone.
        # A boolean alone loses choices when one XP reward crosses multiple
        # milestones (for example, a jump from level 3 to level 13).
        if new_level in (4, 8, 12):
            queue_stat_choice(sheet, new_level)

        # Mark for class advancement at level 5 (if not already advanced)
        if new_level == 5 and not sheet.get("advanced_class"):
            sheet["_advancement_pending"] = True
            
        leveled = True
        final_level = new_level

    # Check level 15 cap
    if final_level >= 15:
        final_level = 15
        sheet["level"] = 15
        cap_xp = XP_THRESHOLDS[max(XP_THRESHOLDS)] + 1
        if sheet["xp"] > cap_xp:
            sheet["xp"] = cap_xp

    return leveled, final_level


def check_and_reset_hunts(sheet: dict, housing: dict = None) -> dict:
    """Reset character-only daily hunts and temporary conditions.

    The optional housing argument remains for older callers, but housing is
    never loaded, mutated, or saved here. Daily farm/pet state is coordinated
    by character_manager.load() under the player's lock and recovery journal.
    """
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    # Older character sheets predate the separate free-event budget.
    sheet.setdefault("forest_event_attempts_today", 0)
    if sheet.get("hunts_reset_date") != today:
        sheet["hunts_today"] = 0
        sheet["hunts_reset_date"] = today
        sheet["forest_event_attempts_today"] = 0

        # BUG-H1 fix: strip ale_warmth HP bonus before clearing conditions
        old_conds = sheet.get("conditions", [])
        if "ale_warmth" in old_conds:
            sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - 3)
            sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

        # Clear temporary conditions (PERMANENT_CONDITIONS survive)
        sheet["conditions"] = [c for c in old_conds if c in PERMANENT_CONDITIONS]

        # BUG-C2 fix: transfer inn_rest buff to "rested" condition (after clear)
        if sheet.get("inn_rest_pending", False):
            sheet.setdefault("conditions", [])
            if "rested" not in sheet["conditions"]:
                sheet["conditions"].append("rested")
            sheet["inn_rest_pending"] = False


    return sheet


def reserve_forest_event_attempt(sheet: dict) -> bool:
    """Reserve one daily free forest-event roll, counting misses too.

    Call after check_and_reset_hunts(). Persist the sheet before rolling so a
    restart cannot restore an already-used attempt.
    """
    try:
        attempts = max(0, int(sheet.get("forest_event_attempts_today", 0)))
    except (TypeError, ValueError):
        attempts = 0

    if attempts >= MAX_FREE_FOREST_EVENT_ATTEMPTS_PER_DAY:
        return False

    sheet["forest_event_attempts_today"] = attempts + 1
    return True


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

    # Calendar special day bonus (Long Night Vigil: +1 hunt)
    from utils.ttrpg.calendar import get_special_day
    _special = get_special_day()
    calendar_hunt_bonus = 0
    if _special and _special.get("buff") == "long_night_vigil":
        calendar_hunt_bonus = _special.get("buff_value", 1)

    return min(MAX_HUNTS_CEILING, MAX_HUNTS_PER_DAY + ale_bonus + rest_bonus + pet_bonus + class_hunt_bonus + hunt_bonus + calendar_hunt_bonus)


def hunts_remaining(sheet: dict, housing: dict = None) -> int:
    """Returns how many hunts the player has left today."""
    if housing is None:
        from utils.ttrpg.housing import load_housing
        housing = load_housing(str(sheet.get("user_id", "")))
    
    sheet = check_and_reset_hunts(sheet, housing=housing)
    return max(0, get_max_hunts(sheet, housing=housing) - sheet.get("hunts_today", 0))


def get_character_title(sheet: dict) -> str:
    """Return the character's current earned title."""
    from utils.ttrpg.class_advancement import get_title
    return get_title(sheet)


# ── Kill-reward bonuses ─────────────────────────────────────────────────────
# A kill is worth anywhere from 4 gil (trivial) to thousands (boss), so a flat
# bonus means everything at level 1 and nothing at level 15: "+1 gil per kill"
# was a quarter of a trivial kill and under 2% of a typical hard one. Bonuses
# are a share of the kill, never less than the flat amount they replaced.

def harvest_bonus(gil: int, share: float) -> int:
    """First Day of Autumn."""
    return max(1, round(gil * share))


def streak_bonus(gil: int, streak: int) -> int:
    """Consecutive kills: 5% of the kill per link, up to five."""
    links = min(streak, 5)
    return max(links * 2, round(gil * 0.05 * links))


def golden_tongue_bonus(gil: int) -> int:
    """The Trickster's blessing, paid on the kill that ends the fight."""
    return max(2, round(gil * 0.25))
