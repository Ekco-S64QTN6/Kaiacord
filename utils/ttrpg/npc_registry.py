NPCS = {
    "elara": {
        "name": "Elder Elara",
        "location": "oakhaven",
        "description": "A weary woman with silver-streaked hair and careful eyes. "
                       "She's carried OakHaven's troubles for two decades.",
        "role": "quest_giver",
        "dialogue_hook": "She watches you with measured caution. Her hands are folded "
                         "on the table. She doesn't waste words.",
        "topics": [
            "The Whisperwood boundary moved twelve feet last night. I measured.",
            "Something came back from the ruins that shouldn't have. I'm handling it.",
            "There's a reason nobody builds east of the Tricklebrook.",
            "Your kind showing up here isn't an accident. I'm still deciding if that's good."
        ],
    },
    "hemlock": {
        "name": "Old Man Hemlock",
        "location": "hemlocks_store",
        "description": "Grizzled, taciturn. Sells everything. Talks too much about "
                       "the old days if you let him.",
        "role": "merchant",
        "dialogue_hook": "He doesn't look up from the counter when you enter.",
        "topics": [
            "Back in Aeridor's time this whole store would've been a resonance depot. Not that anyone knows what that means anymore.",
            "I've raised the price on elixirs. Supply chain. Don't ask.",
            "A Silvani came through last week and bought every antidote I had. Left without saying why.",
            "The watchtower guards ordered extra rope. Won't say what for."
        ],
    },
    "barkeep": {
        "name": "Mira",
        "location": "stone_hearth",
        "description": "The Stone Hearth's barkeep. Heard everything twice. "
                       "Doesn't judge. Charges fair.",
        "role": "innkeeper",
        "dialogue_hook": "She slides a tankard toward you without being asked.",
        "topics": [
            "The Ironclad Guild men have been in three nights running. Something about the Trade Road.",
            "A traveler from Riverbend said the Silverstream is running black.",
            "Someone left flowers at Elara's door. Nobody's admitting to it.",
            "The hooded figure paid in coins nobody's seen before."
        ],
    },
    "hooded_figure": {
        "name": "The Hooded Figure",
        "location": "stone_hearth",
        "description": "Sits in the same corner every night. Face never visible. "
                       "Speaks rarely. When he does, people listen.",
        "role": "mystery",
        "dialogue_hook": "He doesn't acknowledge you at first. Then, slowly, he turns.",
        "topics": [
            "The ruins are not ruins.",
            "Aeridor didn't fall. It was absorbed.",
            "Ask Elara what she found at the Shrine before you arrived.",
            "[says nothing. Doesn't look at you. Somehow you feel seen.]"
        ],
    },
    "guard": {
        "name": "Watchtower Guard",
        "location": "watchtower",
        "description": "One of two guards posted at the Watchtower. Bored, observant, and considerably more informed than they let on. They've been watching the Whisperwood for years.",
        "role": "info",
        "dialogue_hook": "He doesn't turn from the window when you approach. His eyes stay on the treeline.",
        "topics": [
            "The canopy's thicker this year. Can't see the smoke from Aeridor anymore.",
            "Saw a light in the deep woods last night. Moved too fast for a lantern.",
            "Hemlock keep asking about the road. Tell him it's as dangerous as ever.",
            "Don't go east. Not today."
        ],
    },
    "maren": {
        "name": "Sister Maren",
        "location": "herbalists_hut",
        "description": "A quiet woman with hands stained by soil and sap. She lives in a small lean-to behind the shrine, tending to her garden of rare herbs.",
        "role": "herbalist",
        "dialogue_hook": "She is carefully pruning a silver-leafed plant as you approach. She doesn't look up, but gestures for you to wait.",
        "topics": [
            "The Silvermoss is blooming early this year. The soil must be changing.",
            "Hemlock keeps asking for more Antidote, but the ingredients are getting harder to find.",
            "Some plants only grow where the forest is thinnest. Others only where it's thickest.",
            "There's a root that only grows in the ruins. I haven't seen it in years."
        ],
    },
}

def get_npc(key: str) -> dict | None:
    return NPCS.get(key.lower())
