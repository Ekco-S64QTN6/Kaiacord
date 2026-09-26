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
    "iron_pup": {
        "name": "Iron Pup",
        "cost": 3000,
        "desc": "Small Aeridorian pup construct. +1 DEF, and 5% chance to find extra loot chests in dungeons.",
        "emoji": "🐶",
        "passive": "def_bonus",
        "passive_value": 1,
        "extra": {"extra_chest_pct": 0.05},
        "food": "iron_plating",
        "food_cost": 15,
        "flavor_fed": "It wags its metallic tail with a quiet whirring sound.",
        "flavor_unfed": "It sits silently by the door, its gear joints locking up.",
    },
    "tomb_bat": {
        "name": "Tomb Bat",
        "cost": 1500,
        "desc": "A bat trained in the crypts. +10% Gil from dungeon kills when fed.",
        "emoji": "🦇",
        "passive": "gil_bonus_pct",
        "passive_value": 0.10,
        "food": "blood_thistle",
        "food_cost": 10,
        "flavor_fed": "It hangs upside down and chirps softly in appreciation.",
        "flavor_unfed": "It glares at you from the rafters, rustling its wings.",
    },
    "wisp_lantern": {
        "name": "Wisp Lantern",
        "cost": 1000,
        "desc": "A floating wisp in a brass lantern. +5% XP boost when fed.",
        "emoji": "🏮",
        "passive": "xp_bonus_pct",
        "passive_value": 0.05,
        "food": "honey_sap",
        "food_cost": 5,
        "flavor_fed": "It pulses with a bright, warm amber light.",
        "flavor_unfed": "The light dims to a cold blue flicker.",
    },
}

PET_FOOD_NAMES = {
    "fish": "Fish",
    "gysahl_greens": "Gysahl Greens",
    "lantern_oil": "Lantern Oil",
    "honey_sap": "Honey Sap",
    "kupo_nut": "Kupo Nut",
    "aeridor_shard": "Aeridor Shard",
    "iron_plating": "Iron Plating",
    "blood_thistle": "Blood Thistle",
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
        for extra, extra_val in pet_data.get("extra", {}).items():
            bonuses[extra] = bonuses.get(extra, 0) + extra_val
    return bonuses

MOGNET_EVERY_FED_DAYS = 7
MOGNET_VALUE = (10, 300)                     # gil value of what a delivery can hold
_NOT_DELIVERABLE = {"adventurers_pack", "mognet_letter", "spine_memory"}


def reset_daily_pets(housing: dict) -> dict:
    """Call on daily reset — clear fed_today flags.

    A House Moogle fed on seven days queues one Mognet delivery
    (`mognet_deliveries`), handed to the player's mailbox by `deliver_mognet`
    on their next daily reset. The passive was advertised and never paid."""
    for pet in housing.get("pets", []):
        if pet.get("key") == "moogle" and pet.get("fed_today"):
            pet["fed_days"] = pet.get("fed_days", 0) + 1
            if pet["fed_days"] >= MOGNET_EVERY_FED_DAYS:
                pet["fed_days"] = 0
                housing["mognet_deliveries"] = housing.get("mognet_deliveries", 0) + 1
        pet["fed_today"] = False
        pet["days_owned"] = pet.get("days_owned", 0) + 1
    return housing


def deliver_mognet(sheet: dict, housing: dict) -> int:
    """Move queued Mognet deliveries into the sheet's mailbox, one random
    consumable each. Mutates both; returns how many were delivered."""
    n = int(housing.get("mognet_deliveries") or 0)
    if n <= 0:
        return 0
    import secrets
    from utils.ttrpg.equipment_registry import CONSUMABLES
    lo, hi = MOGNET_VALUE
    pool = sorted(k for k, v in CONSUMABLES.items()
                  if k not in _NOT_DELIVERABLE and lo <= v.get("value", 0) <= hi)
    for _ in range(n):
        sheet.setdefault("mailbox", []).append(
            {"from_name": "your House Moogle (Mognet)", "item": secrets.choice(pool), "gil": 0})
    housing["mognet_deliveries"] = 0
    return n
