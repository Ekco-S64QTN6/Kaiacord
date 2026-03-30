"""
Pet System — Aethelgard
Purchased from Pip the Pet Vendor in the Housing District.
Pets provide passive bonuses when fed daily.
"""

PET_REGISTRY = {
    "cat": {
        "name": "Oakhaven Cat",
        "cost": 200,
        "desc": "A grey tabby that judges you constantly. Occasionally brings you dead things. +5% Gil from kills when fed.",
        "emoji": "🐈",
        "passive": "gil_bonus_pct",
        "passive_value": 0.05,
        "food": "fish",
        "food_cost": 5,
        "flavor_fed": "It bumps its head against your leg once. Highest praise.",
        "flavor_unfed": "It sits with its back to you and stares at the wall.",
    },
    "chocobo_chick": {
        "name": "Chocobo Chick",
        "cost": 500,
        "desc": "Tiny. Loud. Aggressively affectionate. +1 hunt per day when fed.",
        "emoji": "🐥",
        "passive": "extra_hunt",
        "passive_value": 1,
        "food": "gysahl_greens",
        "food_cost": 8,
        "flavor_fed": "It runs in three tight circles and then falls over. *Kweh.*",
        "flavor_unfed": "It pecks at the floor and refuses to look at you.",
    },
    "tonberry_companion": {
        "name": "Tiny Tonberry",
        "cost": 1500,
        "desc": "Somehow docile. Carries a small lantern and a very small knife. +2 to all combat rolls when fed.",
        "emoji": "🏮",
        "passive": "combat_bonus",
        "passive_value": 2,
        "food": "lantern_oil",
        "food_cost": 15,
        "flavor_fed": "It regards you for a long moment. Then nods. Then waddles away.",
        "flavor_unfed": "The lantern dims. It holds the knife slightly more deliberately.",
    },
    "whisperwood_sprite": {
        "name": "Sylvan Sprite",
        "cost": 800,
        "desc": "A small glowing creature from the Whisperwood. Restores 3 HP after every combat when fed.",
        "emoji": "✨",
        "passive": "combat_heal",
        "passive_value": 3,
        "food": "honey_sap",
        "food_cost": 5,
        "flavor_fed": "It spins once, emitting a brief warm light.",
        "flavor_unfed": "The glow is noticeably dimmer. It doesn't look at you.",
    },
    "moogle": {
        "name": "House Moogle",
        "cost": 2000,
        "desc": "A moogle that has decided to live with you. Delivers one random item per week from the Mognet network.",
        "emoji": "🎀",
        "passive": "weekly_delivery",
        "passive_value": 1,
        "food": "kupo_nut",
        "food_cost": 20,
        "flavor_fed": "*Kupo!* It immediately begins sorting your inventory without permission.",
        "flavor_unfed": "It sulks in the corner and refuses to say kupo.",
    },
    "aeridor_construct": {
        "name": "Miniature Construct",
        "cost": 5000,
        "desc": "A palm-sized Aeridorian construct. Still active. Still running its original directives. Nobody knows what they are. +3 DEF passively while fed.",
        "emoji": "💎",
        "passive": "def_bonus",
        "passive_value": 3,
        "food": "aeridor_shard",
        "food_cost": 30,
        "flavor_fed": "It vibrates at a frequency you feel rather than hear. Something in the house responds.",
        "flavor_unfed": "The crystal core dims to a flat grey. Its eyes (carved stone) remain open.",
    },
}

PET_FOOD_NAMES = {
    "fish": "Fish",
    "gysahl_greens": "Gysahl Greens",
    "lantern_oil": "Lantern Oil",
    "honey_sap": "Honey Sap",
    "kupo_nut": "Kupo Nut",
    "aeridor_shard": "Aeridor Shard",
}

def get_pet_passive(housing: dict) -> dict:
    """
    Aggregate all active pet passives (fed today only).
    Returns a dict of bonus_type -> total_value.
    """
    bonuses = {}
    for pet in housing.get("pets", []):
        if not pet.get("fed_today"):
            continue
        pet_data = PET_REGISTRY.get(pet["key"])
        if not pet_data:
            continue
        passive = pet_data["passive"]
        val = pet_data["passive_value"]
        bonuses[passive] = bonuses.get(passive, 0) + val
    return bonuses

def reset_daily_pets(housing: dict) -> dict:
    """Call on daily reset — clear fed_today flags."""
    for pet in housing.get("pets", []):
        pet["fed_today"] = False
        pet["days_owned"] = pet.get("days_owned", 0) + 1
    return housing
