NPCS = {
    "elara": {
        "name": "Elder Elara",
        "location": "oakhaven",
        "description": "A weary woman with silver-streaked hair and careful eyes. "
                       "She's carried OakHaven's troubles for two decades.",
        "role": "quest_giver",
        "dialogue_hook": "She watches you with measured caution. Her hands are folded "
                         "on the table. She doesn't waste words.",
    },
    "hemlock": {
        "name": "Old Man Hemlock",
        "location": "hemlocks_store",
        "description": "Grizzled, taciturn. Sells everything. Talks too much about "
                       "the old days if you let him.",
        "role": "merchant",
        "dialogue_hook": "He doesn't look up from the counter when you enter.",
    },
    "barkeep": {
        "name": "Mira",
        "location": "stone_hearth",
        "description": "The Stone Hearth's barkeep. Heard everything twice. "
                       "Doesn't judge. Charges fair.",
        "role": "innkeeper",
        "dialogue_hook": "She slides a tankard toward you without being asked.",
    },
    "hooded_figure": {
        "name": "The Hooded Figure",
        "location": "stone_hearth",
        "description": "Sits in the same corner every night. Face never visible. "
                       "Speaks rarely. When he does, people listen.",
        "role": "mystery",
        "dialogue_hook": "He doesn't acknowledge you at first. Then, slowly, he turns.",
    },
    "guard": {
        "name": "Watchtower Guard",
        "location": "watchtower",
        "description": "One of two guards posted at the Watchtower. Bored, observant, and considerably more informed than they let on. They've been watching the Whisperwood for years.",
        "role": "info",
        "dialogue_hook": "He doesn't turn from the window when you approach. His eyes stay on the treeline.",
    },
}

def get_npc(key: str) -> dict | None:
    return NPCS.get(key.lower())
