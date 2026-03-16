WEAPONS = {
    # Starter / Cheap
    "rusty_dagger":   {"name": "Rusty Dagger",    "attack_bonus": 0, "damage_die": 4,  "value": 5,   "tier": 1},
    "wooden_staff":   {"name": "Wooden Staff",    "attack_bonus": 1, "damage_die": 6,  "value": 8,   "tier": 1, "classes": ["Mage", "Cleric"]},
    "iron_staff":     {"name": "Iron-Shod Staff", "attack_bonus": 2, "damage_die": 8,  "value": 30,  "tier": 2, "classes": ["Mage", "Cleric"]},
    "resonance_staff": {"name": "Resonance Staff", "attack_bonus": 5, "damage_die": 10, "value": 180, "tier": 4, "classes": ["Mage", "Cleric"]},
    "wooden_club":    {"name": "Wooden Club",      "attack_bonus": 0, "damage_die": 4,  "value": 3,   "tier": 1},
    "shortbow":       {"name": "Shortbow",         "attack_bonus": 1, "damage_die": 6,  "value": 20,  "tier": 1},
    "hand_axe":       {"name": "Hand Axe",         "attack_bonus": 1, "damage_die": 6,  "value": 18,  "tier": 1},
    "iron_sword":     {"name": "Iron Sword",       "attack_bonus": 2, "damage_die": 6,  "value": 35,  "tier": 2},
    # Mid-tier
    "spear":          {"name": "Spear",            "attack_bonus": 2, "damage_die": 8,  "value": 40,  "tier": 2},
    "crossbow":       {"name": "Crossbow",         "attack_bonus": 3, "damage_die": 8,  "value": 55,  "tier": 2},
    "battle_axe":     {"name": "Battle Axe",       "attack_bonus": 3, "damage_die": 8,  "value": 60,  "tier": 2},
    "longsword":      {"name": "Longsword",        "attack_bonus": 4, "damage_die": 8,  "value": 80,  "tier": 3},
    # High-tier (Grimstone / ruins drops only)
    "steel_blade":    {"name": "Steel Blade",      "attack_bonus": 5, "damage_die": 10, "value": 150, "tier": 3},
    "resonance_bow":  {"name": "Resonance Bow",    "attack_bonus": 6, "damage_die": 10, "value": 200, "tier": 4},
    "aeridorian_axe": {"name": "Aeridorian Axe",   "attack_bonus": 7, "damage_die": 12, "value": 300, "tier": 4},
    "void_blade":     {"name": "Void Blade",       "attack_bonus": 9, "damage_die": 12, "value": 500, "tier": 5},
}

ARMOR = {
    "travelers_cloak":  {"name": "Traveler's Cloak",  "defense_bonus": 0, "value": 5,   "tier": 1},
    "mages_robe":       {"name": "Mage's Robe",       "defense_bonus": 1, "value": 12,  "tier": 1, "classes": ["Mage", "Cleric"]},
    "silken_robe":      {"name": "Silken Robe",       "defense_bonus": 3, "value": 45,  "tier": 2, "classes": ["Mage", "Cleric"]},
    "arcane_vestment":   {"name": "Arcane Vestment",   "defense_bonus": 6, "value": 175, "tier": 4, "classes": ["Mage", "Cleric"]},
    "leather_armor":    {"name": "Leather Armor",     "defense_bonus": 2, "value": 20,  "tier": 1},
    "studded_leather":  {"name": "Studded Leather",   "defense_bonus": 3, "value": 40,  "tier": 2},
    "chainmail":        {"name": "Chainmail",          "defense_bonus": 5, "value": 80,  "tier": 2},
    "half_plate":       {"name": "Half Plate",         "defense_bonus": 7, "value": 150, "tier": 3},
    "full_plate":       {"name": "Full Plate",         "defense_bonus": 9, "value": 300, "tier": 4},
    "aeridorian_plate": {"name": "Aeridorian Plate",  "defense_bonus": 11,"value": 500, "tier": 5},
}

# What Hemlock sells (tier 1-2 only — high tier from ruins drops or Grimstone)
HEMLOCK_STOCK_WEAPONS = ["rusty_dagger", "wooden_club", "shortbow", "hand_axe",
                          "iron_sword", "spear", "crossbow", "battle_axe",
                          "wooden_staff", "iron_staff"]
HEMLOCK_STOCK_ARMOR   = ["travelers_cloak", "leather_armor", "studded_leather", "chainmail",
                          "mages_robe", "silken_robe"]

CONSUMABLES = {
    "healing_herb":   {"name": "Healing Herb",    "hp_restore": 8,  "value": 10},
    "bandage":        {"name": "Bandage",          "hp_restore": 5,  "value": 6},
    "tonic":          {"name": "Tonic",            "hp_restore": 15, "value": 20},
    "elixir":         {"name": "Elixir",           "hp_restore": 30, "value": 50},
}
