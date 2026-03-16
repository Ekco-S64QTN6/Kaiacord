import secrets

ENCOUNTER_TABLES = {
    "whisperwood_edge": [
        # (monster_key, weight)  — higher weight = more common
        ("bat",       40),
        ("goblin",    35),
        ("wolf",      20),
        ("skeleton",  5),   # rare
    ],
    "whisperwood_deep": [
        ("wolf",      25),
        ("skeleton",  25),
        ("ghost",     20),
        ("lizardman", 20),
        ("harpy",     8),
        ("ochu",      2),   # rare
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

def random_encounter(location: str) -> str:
    """Pick a weighted random monster for the given location."""
    table = ENCOUNTER_TABLES.get(location, ENCOUNTER_TABLES["whisperwood_edge"])
    total = sum(w for _, w in table)
    r = secrets.randbelow(total)
    cumulative = 0
    for monster_key, weight in table:
        cumulative += weight
        if r < cumulative:
            return monster_key
    return table[-1][0]
