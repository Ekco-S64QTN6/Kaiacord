"""
Furniture & Decoration Catalog — Aethelgard
Purchased from Barnaby's Furnishings in the Housing District.
Furniture is cosmetic + some provide passive bonuses.
"""

FURNITURE = {
    # ── Tier 1 — Basic (Available at Hut) ────────────────────────────────
    "straw_bed": {
        "name": "Straw Bed",
        "cost": 80,
        "desc": "Better than the floor.",
        "emoji": "🛏️",
        "tier": 1,
        "bonus": None,
    },
    "hearth": {
        "name": "Stone Hearth",
        "cost": 150,
        "desc": "A small hearth. Makes the place feel like somewhere.",
        "emoji": "🔥",
        "tier": 1,
        "bonus": None,
    },
    "weapon_rack": {
        "name": "Weapon Rack",
        "cost": 100,
        "desc": "Holds up to 3 weapons for display. Grants +1 ATK while in your home.",
        "emoji": "⚔️",
        "tier": 1,
        "bonus": {"type": "home_atk", "value": 1},
    },
    "herb_shelf": {
        "name": "Herb Shelf",
        "cost": 120,
        "desc": "A shelf for your alchemy ingredients. +1 yield from all farm harvests.",
        "emoji": "🌿",
        "tier": 1,
        "bonus": {"type": "farm_yield", "value": 1},
    },
    "candles": {
        "name": "Candlestand",
        "cost": 40,
        "desc": "Warm light. Oakhaven feels less grey.",
        "emoji": "🕯️",
        "tier": 1,
        "bonus": None,
    },
    "bookshelf": {
        "name": "Bookshelf",
        "cost": 200,
        "desc": "A shelf of recovered texts. +5 XP from all NPC talk interactions while owned.",
        "emoji": "📚",
        "tier": 1,
        "bonus": {"type": "talk_xp", "value": 5},
    },

    # ── Tier 2 — Comfortable (Cottage+) ──────────────────────────────────
    "oak_table": {
        "name": "Oak Dining Table",
        "cost": 300,
        "desc": "Seats six. You probably live alone. It's the thought that counts.",
        "emoji": "🪑",
        "tier": 2,
        "bonus": None,
    },
    "mounted_trophy": {
        "name": "Monster Trophy Mount",
        "cost": 250,
        "desc": "A taxidermied head from something you killed. +2 ATK when hunting at your home location.",
        "emoji": "🐺",
        "tier": 2,
        "bonus": {"type": "local_atk", "value": 2},
    },
    "alchemy_table": {
        "name": "Alchemy Workbench",
        "cost": 500,
        "desc": "A proper brewing setup. Allows brewing from your home without going to Maren's.",
        "emoji": "⚗️",
        "tier": 2,
        "bonus": {"type": "home_brewing", "value": 1},
    },
    "training_dummy": {
        "name": "Training Dummy",
        "cost": 400,
        "desc": "A battered stuffed figure. +1 extra daily hunt when used (once per day).",
        "emoji": "🪆",
        "tier": 2,
        "bonus": {"type": "daily_training", "value": 1},
    },
    "aeridor_tapestry": {
        "name": "Aeridorian Tapestry",
        "cost": 600,
        "desc": "A woven reproduction of Aeridorian resonance maps. +10 XP per dungeon room cleared.",
        "emoji": "🗺️",
        "tier": 2,
        "bonus": {"type": "dungeon_xp", "value": 10},
    },

    # ── Tier 3 — Grand (Longhouse+) ──────────────────────────────────────
    "shrine_replica": {
        "name": "Shrine Replica",
        "cost": 1200,
        "desc": "A personal shrine to the Silent Ones. Pray from home once per day.",
        "emoji": "⛩️",
        "tier": 3,
        "bonus": {"type": "home_pray", "value": 1},
    },
    "vault_chest": {
        "name": "Ironbound Vault Chest",
        "cost": 1500,
        "desc": "A heavy locked chest. +500g bank storage cap.",
        "emoji": "🔐",
        "tier": 3,
        "bonus": {"type": "bank_cap", "value": 500},
    },
    "portrait": {
        "name": "Commissioned Portrait",
        "cost": 800,
        "desc": "A painting of your character. Purely cosmetic. Entirely worth it.",
        "emoji": "🖼️",
        "tier": 3,
        "bonus": None,
    },

    # ── Tier 4 — Keep-worthy ──────────────────────────────────────────────
    "throne": {
        "name": "Stone Throne",
        "cost": 5000,
        "desc": "A carved stone seat of authority. +5 to CHA when talking NPCs from home.",
        "emoji": "👑",
        "tier": 4,
        "bonus": {"type": "home_cha", "value": 5},
    },
    "war_map": {
        "name": "Tactical War Map",
        "cost": 3000,
        "desc": "A detailed map of Aethelgard with troop markers. Scout is free and always available from home.",
        "emoji": "📌",
        "tier": 4,
        "bonus": {"type": "home_scout", "value": 1},
    },
}

def get_furniture_by_tier(max_tier: int) -> dict:
    """Return all furniture available up to max_tier."""
    return {k: v for k, v in FURNITURE.items() if v["tier"] <= max_tier}

HOUSING_TIER_TO_FURNITURE_TIER = {
    "hut": 1,
    "cottage": 2,
    "longhouse": 3,
    "keep": 4,
}

def get_home_bonuses(housing: dict) -> dict:
    """Aggregate all furniture bonuses for a player's home."""
    bonuses = {}
    for item_key in housing.get("furniture", []):
        item = FURNITURE.get(item_key)
        if item and item.get("bonus"):
            b = item["bonus"]
            bonuses[b["type"]] = bonuses.get(b["type"], 0) + b["value"]
    return bonuses
