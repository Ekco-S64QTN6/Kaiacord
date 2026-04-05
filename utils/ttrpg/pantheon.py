"""
pantheon.py — The Aethelgard Pantheon
======================================
Six primary deities, each with class alignment, epithets, and
domain flavor. Referenced by npcs, prompt builders, and class advancement.
"""

DEITIES = {
    "aerthis": {
        "name": "Aerthis",
        "title": "The Unbending",
        "domain": "Order, law, structure, light",
        "symbol": "A balanced scale, one side holding flame",
        "classes": ["Cleric", "High Priest", "Paladin"],
        "alignment": "lawful",
        "holy_days": ["First Day of Spring", "The Remembrance"],
        "shrine_flavor": "The flame at the Shrine burns white-blue when Aerthis is acknowledged.",
        "epithets": [
            "the Unbending", "the Lawgiver", "He Who Does Not Yield",
            "First Light", "the Undimmed",
        ],
        "npc_topics": [
            "Aerthis does not reward the devout for faith. He rewards them for action. There's a distinction.",
            "A Paladin's oath to Aerthis is not symbolic. The god hears every word.",
            "Aerthis and Sylvara have not spoken since the Sundering. Neither will say why.",
            "The Shrine was Aerthis's first. The other gods arrived later, as guests.",
        ],
        "monster_connection": "Undead are anathema to Aerthis — his priests are compelled to destroy them.",
        "desc": "God of Order, law, and unwavering light. Patron of Clerics and Paladins.",
    },
    "sylvara": {
        "name": "Sylvara",
        "title": "The Unbound",
        "domain": "Chaos, change, raw magic, storms",
        "symbol": "A broken circle with lightning across the gap",
        "classes": ["Mage", "Wizard", "Necromancer"],
        "alignment": "chaotic",
        "holy_days": ["Festival of Fools", "The Amber Night"],
        "shrine_flavor": "The flame stutters and forks when Sylvara's power moves through an area.",
        "epithets": [
            "the Unbound", "the Stormcaller", "She Who Breaks the Circle",
            "Wild Fire", "the Unmade",
        ],
        "npc_topics": [
            "Sylvara doesn't grant power. She tears open the door to it and steps aside.",
            "The gap between an Apprentice and a Wizard is the moment they stopped asking permission from the rules.",
            "Necromancy is Sylvara's gift misunderstood. Death is change. She sees no difference.",
            "Aeridor's mages served Sylvara, at the end. That's one theory for why it ended the way it did.",
        ],
        "monster_connection": "Magic constructs and resonance entities are touched by her domain.",
        "desc": "Goddess of chaos, raw magic, and change. Patron of Mages and Wizards.",
    },
    "thornax": {
        "name": "Thornax",
        "title": "The Patient",
        "domain": "Balance, nature, cycles, seasons",
        "symbol": "Three roots coiled into a spiral",
        "classes": ["Ranger", "Warden", "Shaman", "Hunter"],
        "alignment": "neutral",
        "holy_days": ["Beltane — The Long Fire", "First Day of Autumn"],
        "shrine_flavor": "The Whisperwood is Thornax's expression. The forest has opinions, and they are his.",
        "epithets": [
            "the Patient", "the Root-Speaker", "He Who Grows Around",
            "Balance", "the Oldest Watcher",
        ],
        "npc_topics": [
            "Thornax doesn't answer prayers. He answers behavior. Prove you belong, and the forest opens.",
            "The Whisperwood is not a place Thornax made. It is a part of him that became too large to contain.",
            "Rangers pray to Thornax before the first hunt of a season. Not for luck. For permission.",
            "The Silvani call him by a different name. They say ours is a child's word for something older.",
        ],
        "monster_connection": "The elder treants and deep forest creatures are his to command.",
        "desc": "God of balance, nature, and cycles. Patron of Rangers, Wardens, and Shamans.",
    },
    "morvenna": {
        "name": "Morvenna",
        "title": "The Inevitable",
        "domain": "Death, transformation, endings, undeath",
        "symbol": "A moth above a candle flame",
        "classes": ["Shadowknight", "Necromancer"],
        "alignment": "dark",
        "holy_days": ["Morvenna's Eve"],
        "shrine_flavor": "The flame burns amber-black on Morvenna's feast night. Elara calls it a warning. The Hooded Figure calls it an invitation.",
        "epithets": [
            "the Inevitable", "the Last Warmth", "She Who Waits at the Door",
            "the Transformer", "the Welcomed End",
        ],
        "npc_topics": [
            "Morvenna doesn't want worship. She wants witnesses. Someone to see what death really is.",
            "A Shadowknight serves Morvenna not because they fear death, but because they've stopped.",
            "Necromancy isn't defying death. It's reading her handwriting aloud.",
            "On Morvenna's Eve, she walks Aethelgard like anyone else. She says she just wants to see how it's going.",
        ],
        "monster_connection": "The undead are her soldiers, her failed experiments, and sometimes her messengers.",
        "desc": "Goddess of death, transformation, and endings. Patron of Shadowknights and Necromancers.",
    },
    "vethran": {
        "name": "Vethran",
        "title": "The Blade Forged",
        "domain": "War, honor, the blade, strength",
        "symbol": "A greatsword driven into an anvil",
        "classes": ["Warrior"],
        "alignment": "neutral",
        "holy_days": ["The Amber Night"],
        "shrine_flavor": "There is no shrine to Vethran in Oakhaven. Warriors carve his mark into their weapons instead.",
        "epithets": [
            "the Blade Forged", "the Unwavering", "He Who Stands Last",
            "the Tested", "the Weight of Iron",
        ],
        "npc_topics": [
            "Vethran has no church. He has veterans.",
            "A warrior who survives enough battles stops praying and starts being answered.",
            "Vethran doesn't distinguish between a soldier and a mercenary. He only distinguishes between those who held and those who ran.",
            "Hemlock keeps a chip of iron behind the counter. Old custom. Vethran's domain, gil's domain — both about value held in the hand.",
        ],
        "monster_connection": "None specific — Vethran claims the fallen of all sides.",
        "desc": "God of war, honor, and the blade. Patron of Warriors.",
    },
    "corvus": {
        "name": "Corvus",
        "title": "The Laughing Road",
        "domain": "Travelers, merchants, trickery, secrets, luck",
        "symbol": "A coin balanced on its edge",
        "classes": ["Rogue", "Trickster"],
        "alignment": "chaotic",
        "holy_days": ["Festival of Fools", "New Year — The Turning"],
        "shrine_flavor": "Corvus has no shrine. He has back rooms, loose floorboards, and the pause before someone laughs.",
        "epithets": [
            "the Laughing Road", "the Slim Margin", "He Who Travels Ahead",
            "the Coin's Edge", "the Well-Named Stranger",
        ],
        "npc_topics": [
            "Corvus blesses no one. He arranges circumstances. What you do with them is your prayer.",
            "Every caravan runner carries his mark. Not faith — insurance. He's the one who knows where all the roads lead.",
            "Rogues call him the Patron of Favorable Odds. He would say that's an overcompliment. He just likes being in the room.",
            "The Hooded Figure paid in Corvus coins once. Nobody knows what that means.",
        ],
        "monster_connection": "Corvus claims no monsters — only the people who made poor choices near them.",
        "desc": "God of travelers, merchants, trickery, and luck. Patron of Rogues and Tricksters.",
    },
}

# Class → primary deity lookup
CLASS_DEITY = {
    "Warrior":    "vethran",
    "Ranger":     "thornax",
    "Mage":       "sylvara",
    "Rogue":      "corvus",
    "Cleric":     "aerthis",
    "Paladin":    "aerthis",
    "Shadowknight": "morvenna",
    "Hunter":     "thornax",
    "Warden":     "thornax",
    "Wizard":     "sylvara",
    "Necromancer":"morvenna",
    "Shadowblade":"corvus",
    "Trickster":  "corvus",
    "High Priest":"aerthis",
    "Shaman":     "thornax",
}


def get_deity_for_class(class_name: str) -> dict | None:
    key = CLASS_DEITY.get(class_name)
    return DEITIES.get(key) if key else None


def get_class_deity_name(class_name: str) -> str:
    d = get_deity_for_class(class_name)
    return d["name"] if d else "the Silent Ones"


def get_class_deity_epithet(class_name: str) -> str:
    """Return a random epithet for the class's deity."""
    import secrets as _sec
    d = get_deity_for_class(class_name)
    if not d or not d.get("epithets"):
        return "the Unknown"
    return _sec.choice(d["epithets"])
