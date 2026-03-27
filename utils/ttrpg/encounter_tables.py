import secrets

ENCOUNTER_TABLES = {
    "whisperwood_edge": [
        ("bat",       40),
        ("goblin",    35),
        ("wolf",      20),
        ("skeleton",  5),
    ],
    "whisperwood_deep": [
        ("wolf",      25),
        ("skeleton",  25),
        ("ghost",     20),
        ("lizardman", 20),
        ("harpy",     8),
        ("ochu",      2),
    ],
    "aeridor_ruins": [
        ("skeleton",  20),
        ("ghost",     20),
        ("golem",     20),
        ("dark_knight",15),
        ("tonberry",  10),
        ("lich",      5),
        ("iron_giant", 10),
    ],
    "trade_road": [
        ("goblin",    50),
        ("wolf",      30),
        ("lizardman", 20),
    ],
}

def random_encounter(location: str, player_level: int = 1) -> str:
    """Pick a weighted random monster for the given location, filtered by player level."""
    from utils.ttrpg.calendar import get_seasonal_encounter_table
    from utils.ttrpg.monster_registry import MONSTERS

    TIER_ORDER = ["trivial", "easy", "medium", "hard", "deadly", "boss"]

    # Minimum tier thresholds based on player level
    min_tier = None
    if player_level >= 9:
        min_tier = "hard"
    elif player_level >= 7:
        min_tier = "medium"
    elif player_level >= 4:
        min_tier = "easy"

    base_table = ENCOUNTER_TABLES.get(location, ENCOUNTER_TABLES["whisperwood_edge"])
    table = get_seasonal_encounter_table(location, base_table)

    # Filter out monsters below minimum tier
    if min_tier:
        min_idx = TIER_ORDER.index(min_tier)
        filtered = [
            (key, weight) for key, weight in table
            if TIER_ORDER.index(MONSTERS.get(key, {}).get("tier", "trivial")) >= min_idx
        ]
        if filtered:  # only use filter if it leaves something to fight
            table = filtered

    total = sum(w for _, w in table)
    r = secrets.randbelow(total)
    cumulative = 0
    for monster_key, weight in table:
        cumulative += weight
        if r < cumulative:
            return monster_key
    return table[-1][0]

# Forest Event System
EVENT_CHANCE = {
    "whisperwood_edge": 12,
    "whisperwood_deep": 10,
    "aeridor_ruins":     8,
    "trade_road":       10,
}

def roll_for_event(location: str) -> bool:
    """Returns True if this hunt should be a special event."""
    chance = EVENT_CHANCE.get(location, 15)
    return secrets.randbelow(100) < chance

EVENTS = {
    "whisperwood_edge": [
        ("sylvan_sprites",       20),
        ("moogle_sighting",      12),
        ("injured_silvani",      12),
        ("old_man_riddle",       10),
        ("chocobo_tracks",       10),
        ("aeridor_fragment",      8),
        ("gilded_mushroom",       8),
        ("veiled_elder",          7),
        ("timid_tonberry",        5),
        ("mognet_delivery",       5),
        ("crystal_resonance",     3),
    ],
    "whisperwood_deep": [
        ("injured_silvani",      18),
        ("old_man_riddle",       12),
        ("veiled_elder",         12),
        ("aeridor_fragment",     12),
        ("crystal_resonance",    10),
        ("timid_tonberry",        8),
        ("moogle_sighting",       8),
        ("chocobo_tracks",        8),
        ("mognet_delivery",       7),
        ("sylvan_sprites",        5),
    ],
    "aeridor_ruins": [
        ("aeridor_fragment",     25),
        ("crystal_resonance",    20),
        ("veiled_elder",         18),
        ("old_man_riddle",       15),
        ("timid_tonberry",       12),
        ("mognet_delivery",      10),
    ],
    "trade_road": [
        ("gilded_mushroom",      20),
        ("old_man_riddle",       20),
        ("injured_silvani",      18),
        ("moogle_sighting",      15),
        ("chocobo_tracks",       15),
        ("mognet_delivery",      12),
    ],
}

def random_event(location: str) -> str:
    """Pick a weighted random event for the given location."""
    table = EVENTS.get(location, EVENTS["whisperwood_edge"])
    total = sum(w for _, w in table)
    r = secrets.randbelow(total)
    cumulative = 0
    for event_key, weight in table:
        cumulative += weight
        if r < cumulative:
            return event_key
    return table[0][0]
