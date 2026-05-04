"""
encounter_tables.py — Uses the full monster_registry bestiary.
Replaces the deprecated stub tables with proper registry import.
"""
import secrets
from utils.ttrpg.calendar import get_seasonal_encounter_table, get_special_day
from utils.ttrpg.monster_registry import ENCOUNTER_TABLES, MONSTERS

EVENT_CHANCE = {
    "whisperwood_edge": 20,
    "whisperwood_deep": 18,
    "aeridor_ruins":    12,
    "trade_road":       15,
}

# Quest-boosted encounter tables — keyed by synthetic location strings
QUEST_ENCOUNTER_OVERRIDES = {
    "trade_road_maren": [
        ("bandit",       55),   # heavily boosted for Sister Maren's quest
        ("goblin",       15),
        ("goblin_guard", 10),
        ("wolf",          8),
        ("snow_bandit",   7),
        ("kobold",        5),
    ],
    "whisperwood_deep_hunt": [
        ("owlbear",      35),   # heavily boosted for deep hunt
        ("frost_wolf",   35),   # heavily boosted for deep hunt
        ("dire_wolf",    15),
        ("troll",        10),
        ("ghost",         5),
    ],
    "aeridor_ruins_remnant": [
        ("iron_golem",      60),   # heavily boosted for remnant quest
        ("stone_golem",     20),
        ("clockwork_guard", 15),
        ("basilisk",         5),
    ],
    "whisperwood_deep_shadow": [
        ("shadow_lich",  50),   # heavily boosted for shadow incursion
        ("lich",         25),
        ("wraith",       15),
        ("ghost",        10),
    ],
}

def random_encounter(location: str, player_level: int = 1) -> str:
    # Quest override tables take full precedence
    if location in QUEST_ENCOUNTER_OVERRIDES:
        table = QUEST_ENCOUNTER_OVERRIDES[location]
        total = sum(w for _, w in table)
        r = secrets.randbelow(total)
        cum = 0
        for monster_key, weight in table:
            cum += weight
            if r < cum:
                return monster_key
        return table[-1][0]

    TIER_ORDER = ["trivial", "easy", "medium", "hard", "deadly", "boss"]

    # Level-based tier window: (min_tier, max_tier)
    # Prevents low-level players from encountering high-tier monsters
    if player_level >= 13:  min_tier, max_tier = "deadly",  "boss"
    elif player_level >= 11: min_tier, max_tier = "hard",   "boss"
    elif player_level >= 9:  min_tier, max_tier = "hard",   "boss"
    elif player_level >= 7: min_tier, max_tier = "medium",  "deadly"
    elif player_level >= 4: min_tier, max_tier = "easy",    "medium"
    else:                   min_tier, max_tier = "trivial", "easy"

    base_table = ENCOUNTER_TABLES.get(location, ENCOUNTER_TABLES["whisperwood_edge"])
    if isinstance(base_table, dict):
        # Flatten dictionary for overworld hunts
        flat_table = []
        for zone_list in base_table.values():
            flat_table.extend(zone_list)
        base_table = flat_table
        
    table = get_seasonal_encounter_table(location, base_table)
    
    special = get_special_day()
    special_mod = special.get("encounter_mod", {}) if special else {}

    min_idx = TIER_ORDER.index(min_tier)
    max_idx = TIER_ORDER.index(max_tier)

    tier_shift = special_mod.get("tier_shift", 0)
    if tier_shift:
        min_idx = min(len(TIER_ORDER) - 1, max(0, min_idx + tier_shift))
        max_idx = min(len(TIER_ORDER) - 1, max(0, max_idx + tier_shift))

    if special_mod.get("undead_bonus"):
        table = table + [("skeleton", 15), ("ghost", 15)]

    filtered = [
        (k, w) for k, w in table
        if min_idx <= TIER_ORDER.index(
            MONSTERS.get(k, {}).get("tier", "trivial")
        ) <= max_idx
    ]
    if filtered:
        table = filtered

    total = sum(w for _, w in table)
    r = secrets.randbelow(total)
    cum = 0
    for monster_key, weight in table:
        cum += weight
        if r < cum:
            return monster_key
    return table[-1][0]


def roll_for_event(location: str) -> bool:
    chance = EVENT_CHANCE.get(location, 15)
    return secrets.randbelow(100) < chance


EVENTS = {
    "whisperwood_edge": [
        ("sylvan_sprites",    18), ("moogle_sighting",   10),
        ("injured_silvani",   10), ("old_man_riddle",     8),
        ("chocobo_tracks",     8), ("aeridor_fragment",   6),
        ("gilded_mushroom",    6), ("veiled_elder",       6),
        ("timid_tonberry",     5), ("mognet_delivery",    4),
        ("crystal_resonance",  3), ("whisper_in_bark",    5),
        ("abandoned_camp",     5), ("dream_walker",       4),
        ("twin_wisps",         4), ("lost_merchant",      4),
        ("ancient_coin",       4),
    ],
    "whisperwood_deep": [
        ("injured_silvani",   15), ("old_man_riddle",    10),
        ("veiled_elder",      10), ("aeridor_fragment",  10),
        ("crystal_resonance",  8), ("timid_tonberry",     8),
        ("moogle_sighting",    6), ("chocobo_tracks",     6),
        ("mognet_delivery",    6), ("sylvan_sprites",     4),
        ("whisper_in_bark",    8), ("strange_statue",     5),
        ("echo_of_aeridor",    8), ("dream_walker",       5),
        ("twin_wisps",         5), ("cactuar_sighting",   2),
    ],
    "aeridor_ruins": [
        ("aeridor_fragment",  20), ("crystal_resonance", 18),
        ("veiled_elder",      14), ("old_man_riddle",    12),
        ("timid_tonberry",    10), ("mognet_delivery",    8),
        ("echo_of_aeridor",   10), ("strange_statue",     8),
    ],
    "trade_road": [
        ("gilded_mushroom",   16), ("old_man_riddle",    14),
        ("injured_silvani",   14), ("moogle_sighting",   12),
        ("chocobo_tracks",    12), ("mognet_delivery",   10),
        ("lost_merchant",     12), ("abandoned_camp",    10),
    ],
}


def random_event(location: str) -> str:
    table = EVENTS.get(location, EVENTS["whisperwood_edge"])
    total = sum(w for _, w in table)
    r = secrets.randbelow(total)
    cum = 0
    for event_key, weight in table:
        cum += weight
        if r < cum:
            return event_key
    return table[0][0]
