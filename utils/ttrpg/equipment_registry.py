WEAPONS = {
    # Tier 1
    "rusty_dagger":   {"name": "Rusty Dagger",    "attack_bonus": 0, "damage_die": 4,  "value": 5,   "tier": 1},
    "wooden_club":    {"name": "Wooden Club",      "attack_bonus": 0, "damage_die": 4,  "value": 3,   "tier": 1},
    "wooden_staff":   {"name": "Wooden Staff",    "attack_bonus": 1, "damage_die": 6,  "value": 8,   "tier": 1, "classes": ["Mage", "Cleric"]},
    "shortbow":       {"name": "Shortbow",         "attack_bonus": 1, "damage_die": 6,  "value": 20,  "tier": 1},
    "hand_axe":       {"name": "Hand Axe",         "attack_bonus": 1, "damage_die": 6,  "value": 18,  "tier": 1},

    # Tier 2
    "iron_sword":     {"name": "Iron Sword",       "attack_bonus": 2, "damage_die": 6,  "value": 35,  "tier": 2},
    "iron_staff":     {"name": "Iron-Shod Staff", "attack_bonus": 2, "damage_die": 8,  "value": 30,  "tier": 2, "classes": ["Mage", "Cleric"]},
    "spear":          {"name": "Spear",            "attack_bonus": 2, "damage_die": 8,  "value": 40,  "tier": 2},
    "crossbow":       {"name": "Crossbow",         "attack_bonus": 3, "damage_die": 8,  "value": 55,  "tier": 2},
    "battle_axe":     {"name": "Battle Axe",       "attack_bonus": 3, "damage_die": 8,  "value": 60,  "tier": 2},

    # Tier 3
    "longsword":      {"name": "Longsword",        "attack_bonus": 4, "damage_die": 8,  "value": 80,  "tier": 3},
    "steel_blade":    {"name": "Steel Blade",      "attack_bonus": 5, "damage_die": 10, "value": 150, "tier": 3},
    "flame_sword":    {"name": "Flame Sword",      "attack_bonus": 4, "damage_die": 8,  "value": 90,  "tier": 3},
    "ice_brand":      {"name": "Ice Brand",        "attack_bonus": 4, "damage_die": 8,  "value": 95,  "tier": 3},
    "defender":       {"name": "Defender",          "attack_bonus": 5, "damage_die": 10, "value": 160, "tier": 3},
    "ghoulbane":      {"name": "Ghoulbane",        "attack_bonus": 5, "damage_die": 8,  "value": 180, "tier": 3, "classes": ["Warrior", "Cleric"]},
    "flametongue":    {"name": "Flametongue",      "attack_bonus": 5, "damage_die": 8,  "value": 250, "tier": 3},
    "frostbrand":     {"name": "Frostbrand",       "attack_bonus": 5, "damage_die": 8,  "value": 260, "tier": 3},

    # Tier 4
    "resonance_staff": {"name": "Resonance Staff", "attack_bonus": 5, "damage_die": 10, "value": 180, "tier": 4, "classes": ["Mage", "Cleric"]},
    "resonance_bow":  {"name": "Resonance Bow",    "attack_bonus": 6, "damage_die": 10, "value": 200, "tier": 4},
    "aeridorian_axe": {"name": "Aeridorian Axe",   "attack_bonus": 7, "damage_die": 12, "value": 300, "tier": 4},
    "masamune":       {"name": "Masamune",         "attack_bonus": 8, "damage_die": 12, "value": 400, "tier": 4, "classes": ["Warrior", "Rogue"]},
    "fiery_avenger":  {"name": "Fiery Avenger",    "attack_bonus": 7, "damage_die": 10, "value": 280, "tier": 4, "classes": ["Warrior"]},
    "blood_sword":    {"name": "Blood Sword",      "attack_bonus": 6, "damage_die": 8,  "value": 200, "tier": 4},
    "shining_staff":  {"name": "Shining Staff",    "attack_bonus": 6, "damage_die": 10, "value": 220, "tier": 4, "classes": ["Mage", "Cleric"]},
    "yoichi_bow":     {"name": "Yoichi Bow",       "attack_bonus": 6, "damage_die": 10, "value": 250, "tier": 4, "classes": ["Ranger"]},
    "sun_blade":      {"name": "Sun Blade",        "attack_bonus": 8, "damage_die": 10, "value": 450, "tier": 4},
    "ykesha_sword":   {"name": "Sword of Ykesha",  "attack_bonus": 6, "damage_die": 8,  "value": 220, "tier": 4},
    "disruption_mace":{"name": "Mace of Disruption","attack_bonus": 6, "damage_die": 8,  "value": 300, "tier": 4, "classes": ["Cleric"]},

    # Tier 5
    "void_blade":     {"name": "Void Blade",       "attack_bonus": 9, "damage_die": 12, "value": 500, "tier": 5},
    "holy_avenger":   {"name": "Holy Avenger",     "attack_bonus": 9, "damage_die": 12, "value": 600, "tier": 5, "classes": ["Warrior", "Cleric"]},
    "vorpal_sword":   {"name": "Vorpal Sword",     "attack_bonus": 10,"damage_die": 12, "value": 750, "tier": 5, "classes": ["Warrior", "Rogue"]},
    "staff_magi":     {"name": "Staff of the Magi","attack_bonus": 8, "damage_die": 10, "value": 650, "tier": 5, "classes": ["Mage"]},
    "soulfire":       {"name": "Soulfire",         "attack_bonus": 9, "damage_die": 12, "value": 700, "tier": 5, "classes": ["Cleric"]},
    "excalibur_ff":   {"name": "Excalibur",        "attack_bonus": 11,"damage_die": 12, "value": 900, "tier": 5, "classes": ["Warrior"]},
    "ragnarok_ff":    {"name": "Ragnarok",         "attack_bonus": 10,"damage_die": 12, "value": 850, "tier": 5, "classes": ["Warrior"]},
    "ultima_weapon":  {"name": "Ultima Weapon",    "attack_bonus": 12,"damage_die": 12, "value": 1200,"tier": 5},
    "mjolnir":        {"name": "Mjolnir",          "attack_bonus": 9, "damage_die": 12, "value": 680, "tier": 5, "classes": ["Warrior", "Cleric"]},
}

ARMOR = {
    # Tier 1
    "travelers_cloak":  {"name": "Traveler's Cloak",  "defense_bonus": 0, "value": 5,   "tier": 1},
    "leather_armor":    {"name": "Leather Armor",     "defense_bonus": 2, "value": 20,  "tier": 1},
    "mages_robe":       {"name": "Mage's Robe",       "defense_bonus": 1, "value": 12,  "tier": 1, "classes": ["Mage", "Cleric"]},
    "bronze_armor":     {"name": "Bronze Armor",      "defense_bonus": 3, "value": 30,  "tier": 1},
    "fur_cloak":        {"name": "Fur Cloak",         "defense_bonus": 2, "value": 18,  "tier": 1},

    # Tier 2
    "studded_leather":  {"name": "Studded Leather",   "defense_bonus": 3, "value": 40,  "tier": 2},
    "chainmail":        {"name": "Chainmail",          "defense_bonus": 5, "value": 80,  "tier": 2},
    "silken_robe":      {"name": "Silken Robe",       "defense_bonus": 3, "value": 45,  "tier": 2, "classes": ["Mage", "Cleric"]},
    "black_garb":       {"name": "Black Garb",        "defense_bonus": 5, "value": 90,  "tier": 2, "classes": ["Rogue", "Ranger"]},

    # Tier 3
    "half_plate":       {"name": "Half Plate",         "defense_bonus": 7, "value": 150, "tier": 3},
    "flame_mail":       {"name": "Flame Mail",        "defense_bonus": 7, "value": 160, "tier": 3},
    "ice_armor":        {"name": "Ice Armor",         "defense_bonus": 7, "value": 160, "tier": 3},
    "mithral_shirt":    {"name": "Mithral Chain Shirt","defense_bonus": 6, "value": 250, "tier": 3},

    # Tier 4
    "full_plate":       {"name": "Full Plate",         "defense_bonus": 9, "value": 300, "tier": 4},
    "diamond_armor":    {"name": "Diamond Armor",     "defense_bonus": 8, "value": 220, "tier": 4},
    "arcane_vestment":   {"name": "Arcane Vestment",   "defense_bonus": 6, "value": 175, "tier": 4, "classes": ["Mage", "Cleric"]},

    # Tier 5
    "aeridorian_plate": {"name": "Aeridorian Plate",  "defense_bonus": 11,"value": 500, "tier": 5},
    "rubicite_armor":   {"name": "Rubicite Armor",    "defense_bonus": 10,"value": 450, "tier": 5, "classes": ["Warrior"]},
    "dragon_scale":     {"name": "Dragon Scale Mail", "defense_bonus": 10,"value": 600, "tier": 5},
    "ethereal_plate":   {"name": "Ethereal Plate",    "defense_bonus": 12,"value": 800, "tier": 5, "classes": ["Warrior"]},
    "archmage_robe":    {"name": "Robe of the Archmagi","defense_bonus": 8,"value": 750, "tier": 5, "classes": ["Mage"]},
    "genji_armor":      {"name": "Genji Armor",       "defense_bonus": 11,"value": 700, "tier": 5, "classes": ["Warrior", "Rogue"]},
    "adamantine_plate": {"name": "Adamantine Plate",  "defense_bonus": 12,"value": 900, "tier": 5, "classes": ["Warrior"]},
}

# ─── HEADGEAR ────────────────────────────────────────────────────────────────
HEADGEAR = {
    # Tier 1
    "worn_cap":          {"name": "Worn Cap",          "defense_bonus": 1, "value": 4,   "tier": 1},
    "iron_helm":         {"name": "Iron Helm",          "defense_bonus": 3, "value": 18,  "tier": 1, "classes": ["Warrior"]},
    "scouts_hood":       {"name": "Scout's Hood",       "defense_bonus": 2, "value": 14,  "tier": 1, "classes": ["Ranger", "Rogue"]},
    "mages_cap":         {"name": "Mage's Cap",         "defense_bonus": 1, "value": 10,  "tier": 1, "classes": ["Mage", "Cleric"]},
    "bronze_helm":       {"name": "Bronze Helm",        "defense_bonus": 2, "value": 15,  "tier": 1},

    # Tier 2
    "steel_visor":       {"name": "Steel Visor",        "defense_bonus": 5, "value": 55,  "tier": 2, "classes": ["Warrior"]},
    "leather_coif":      {"name": "Leather Coif",       "defense_bonus": 3, "value": 35,  "tier": 2, "classes": ["Ranger", "Rogue"]},
    "silken_cowl":       {"name": "Silken Cowl",        "defense_bonus": 2, "value": 40,  "tier": 2, "classes": ["Mage", "Cleric"]},
    "horned_helmet":     {"name": "Horned Helmet",      "defense_bonus": 4, "value": 45,  "tier": 2, "classes": ["Warrior"]},
    "sages_hat":         {"name": "Sage's Hat",         "defense_bonus": 3, "value": 60,  "tier": 2, "classes": ["Mage", "Cleric"]},

    # Tier 3
    "siege_helm":        {"name": "Siege Helm",         "defense_bonus": 7, "value": 100, "tier": 3, "classes": ["Warrior"]},
    "stalkers_cowl":     {"name": "Stalker's Cowl",     "defense_bonus": 5, "value": 80,  "tier": 3, "classes": ["Ranger", "Rogue"]},
    "arcane_circlet":    {"name": "Arcane Circlet",     "defense_bonus": 4, "value": 90,  "tier": 3, "classes": ["Mage", "Cleric"]},
    "flame_helm":        {"name": "Flame Helm",         "defense_bonus": 6, "value": 85,  "tier": 3},
    "gold_hairpin":      {"name": "Gold Hairpin",       "defense_bonus": 5, "value": 75,  "tier": 3, "classes": ["Mage", "Cleric"]},
    "ribbon":            {"name": "Ribbon",             "defense_bonus": 3, "value": 120, "tier": 3},
    "executioner_hood":  {"name": "Executioner's Hood", "defense_bonus": 4, "value": 70,  "tier": 3, "classes": ["Warrior", "Rogue"]},
    "circlet_persuasion":{"name": "Circlet of Persuasion","defense_bonus": 2, "value": 150, "tier": 3},

    # Tier 4
    "aeridorian_helm":   {"name": "Aeridorian Helm",    "defense_bonus": 9, "value": 200, "tier": 4, "classes": ["Warrior"]},
    "shadowweave_mask":  {"name": "Shadowweave Mask",   "defense_bonus": 7, "value": 180, "tier": 4, "classes": ["Rogue"]},
    "resonance_crown":   {"name": "Resonance Crown",    "defense_bonus": 6, "value": 190, "tier": 4, "classes": ["Mage", "Cleric"]},
    "diamond_helm":      {"name": "Diamond Helm",       "defense_bonus": 8, "value": 180, "tier": 4},

    # Tier 5
    "void_helm":         {"name": "Void Helm",          "defense_bonus": 12, "value": 450, "tier": 5},
    "brilliance_helm":   {"name": "Helm of Brilliance", "defense_bonus": 10,"value": 500, "tier": 5},
    "crown_stars":       {"name": "Crown of Stars",     "defense_bonus": 8, "value": 450, "tier": 5, "classes": ["Mage", "Cleric"]},
    "genji_helm":        {"name": "Genji Helm",         "defense_bonus": 9, "value": 400, "tier": 5, "classes": ["Warrior", "Rogue"]},
}

# ─── BOOTS ───────────────────────────────────────────────────────────────────
BOOTS = {
    # Tier 1
    "worn_boots":        {"name": "Worn Boots",         "defense_bonus": 1, "value": 5,   "tier": 1},
    "heavy_boots":       {"name": "Heavy Boots",        "defense_bonus": 3, "value": 20,  "tier": 1, "classes": ["Warrior"]},
    "trackers_boots":    {"name": "Tracker's Boots",    "defense_bonus": 2, "value": 18,  "tier": 1, "classes": ["Ranger", "Rogue"]},
    "soft_slippers":     {"name": "Soft Slippers",      "defense_bonus": 1, "value": 12,  "tier": 1, "classes": ["Mage", "Cleric"]},
    "bronze_sabatons":   {"name": "Bronze Sabatons",   "defense_bonus": 2, "value": 18,  "tier": 1},

    # Tier 2
    "iron_shod_boots":   {"name": "Iron-Shod Boots",   "defense_bonus": 5, "value": 60,  "tier": 2, "classes": ["Warrior"]},
    "shadow_treads":     {"name": "Shadow Treads",      "defense_bonus": 4, "value": 50,  "tier": 2, "classes": ["Rogue"]},
    "foresters_boots":   {"name": "Forester's Boots",  "defense_bonus": 3, "value": 45,  "tier": 2, "classes": ["Ranger"]},
    "ley_walkers":       {"name": "Ley-Walker Sandals","defense_bonus": 2, "value": 40,  "tier": 2, "classes": ["Mage", "Cleric"]},

    # Tier 3
    "wardens_greaves":   {"name": "Warden's Greaves",  "defense_bonus": 7, "value": 120, "tier": 3, "classes": ["Warrior"]},
    "whisperwood_boots": {"name": "Whisperwood Boots", "defense_bonus": 5, "value": 100, "tier": 3, "classes": ["Ranger", "Rogue"]},
    "resonance_treads":  {"name": "Resonance Treads",  "defense_bonus": 4, "value": 110, "tier": 3, "classes": ["Mage", "Cleric"]},
    "flame_greaves":     {"name": "Flame Greaves",     "defense_bonus": 6, "value": 95,  "tier": 3},
    "striding_boots":    {"name": "Boots of Striding",  "defense_bonus": 4, "value": 80,  "tier": 3},

    # Tier 4
    "aeridorian_greaves":{"name": "Aeridorian Greaves","defense_bonus": 9, "value": 220, "tier": 4, "classes": ["Warrior"]},
    "shadow_striders":   {"name": "Shadow Striders",   "defense_bonus": 8, "value": 200, "tier": 4, "classes": ["Rogue"]},
    "diamond_boots":     {"name": "Diamond Boots",     "defense_bonus": 8, "value": 195, "tier": 4},
    "winged_boots":      {"name": "Winged Boots",       "defense_bonus": 5, "value": 300, "tier": 4},
    "boots_speed":       {"name": "Boots of Speed",     "defense_bonus": 6, "value": 250, "tier": 4},

    # Tier 5
    "void_striders":     {"name": "Void Striders",     "defense_bonus": 12, "value": 480, "tier": 5},
    "hermes_boots":      {"name": "Hermes Boots",       "defense_bonus": 8, "value": 450, "tier": 5},
    "genji_boots":       {"name": "Genji Boots",        "defense_bonus": 9, "value": 550, "tier": 5, "classes": ["Warrior", "Rogue"]},
    "seven_league_boots":{"name": "7-League Boots",    "defense_bonus": 7, "value": 600, "tier": 5},
}

# ─── ACCESSORIES (rings / bracers / bracelets) ───────────────────────────────
ACCESSORIES = {
    # Tier 1
    "copper_ring":       {"name": "Copper Ring",        "defense_bonus": 1, "attack_bonus": 0, "value": 8,   "tier": 1},
    "warriors_bracer":   {"name": "Warrior's Bracer",   "defense_bonus": 2, "attack_bonus": 1, "value": 18,  "tier": 1, "classes": ["Warrior"]},
    "scouts_bracer":     {"name": "Scout's Bracer",     "defense_bonus": 1, "attack_bonus": 1, "value": 15,  "tier": 1, "classes": ["Ranger", "Rogue"]},
    "scholars_bracelet": {"name": "Scholar's Bracelet", "defense_bonus": 1, "attack_bonus": 0, "value": 12,  "tier": 1, "classes": ["Mage", "Cleric"]},

    # Tier 2
    "iron_ring":         {"name": "Iron Ring",          "defense_bonus": 2, "attack_bonus": 0, "value": 35,  "tier": 2},
    "oak_bracelet":      {"name": "Oak Bracelet",       "defense_bonus": 2, "attack_bonus": 1, "value": 40,  "tier": 2},
    "crystal_bracelet":  {"name": "Crystal Bracelet",  "defense_bonus": 2, "attack_bonus": 0, "value": 45,  "tier": 2, "classes": ["Mage", "Cleric"]},

    # Tier 3
    "silver_ring":       {"name": "Silver Ring",        "defense_bonus": 3, "attack_bonus": 1, "value": 80,  "tier": 3},
    "tricklebrook_charm":{"name": "Tricklebrook Charm","defense_bonus": 3, "attack_bonus": 0, "value": 75,  "tier": 3},
    "aeridor_bangle":    {"name": "Aeridor Bangle",    "defense_bonus": 4, "attack_bonus": 2, "value": 100, "tier": 3},
    "serpentine_bracer": {"name": "Serpentine Bracer", "defense_bonus": 3, "attack_bonus": 2, "value": 85,  "tier": 3, "classes": ["Rogue", "Ranger"]},
    "gold_ring":         {"name": "Gold Ring",          "defense_bonus": 4, "attack_bonus": 1, "value": 110, "tier": 3},
    "ring_protection":   {"name": "Ring of Protection", "defense_bonus": 2, "attack_bonus": 1, "value": 150, "tier": 3},
    "periapt_poison":    {"name": "Periapt of Poison",  "defense_bonus": 2, "attack_bonus": 0, "value": 100, "tier": 3},

    # Tier 4
    "resonance_ring":    {"name": "Resonance Ring",    "defense_bonus": 5, "attack_bonus": 2, "value": 200, "tier": 4},
    "elaras_token":      {"name": "Elara's Token",     "defense_bonus": 4, "attack_bonus": 0, "value": 0,   "tier": 4},
    "djarns_ring":       {"name": "Djarn's Ring",       "defense_bonus": 5, "attack_bonus": 3, "value": 250, "tier": 4},
    "bracers_defense":   {"name": "Bracers of Defense", "defense_bonus": 4, "attack_bonus": 0, "value": 250, "tier": 4},
    "amulet_health":     {"name": "Amulet of Health",   "defense_bonus": 4, "attack_bonus": 0, "value": 200, "tier": 4},
    "ogre_gauntlets":    {"name": "Ogre Gauntlets",     "defense_bonus": 2, "attack_bonus": 4, "value": 350, "tier": 4, "classes": ["Warrior"]},
    "displacement_cloak":{"name": "Displacement Cloak", "defense_bonus": 5, "attack_bonus": 0, "value": 450, "tier": 4},

    # Tier 5
    "void_band":         {"name": "Void Band",         "defense_bonus": 7, "attack_bonus": 3, "value": 500, "tier": 5},
    "mox_pearl":         {"name": "Mox Pearl",          "defense_bonus": 0, "attack_bonus": 3, "value": 1000,"tier": 5},
    "giant_belt":        {"name": "Giant Strength Belt","defense_bonus": 0, "attack_bonus": 5, "value": 600, "tier": 5, "classes": ["Warrior"]},
    "black_lotus":       {"name": "Black Lotus",        "defense_bonus": 0, "attack_bonus": 10,"value": 5000,"tier": 5},
}

# What Hemlock sells (Tier 1 ONLY — Oakhaven starter stock)
HEMLOCK_STOCK_WEAPONS = ["shortbow", "hand_axe", "wooden_staff", "iron_sword", "iron_staff", "spear", "crossbow", "battle_axe"]
HEMLOCK_STOCK_ARMOR   = ["leather_armor", "mages_robe", "bronze_armor", "fur_cloak", "studded_leather", "chainmail", "silken_robe", "black_garb"]
HEMLOCK_STOCK_HEADGEAR = ["iron_helm", "scouts_hood", "mages_cap", "bronze_helm", "steel_visor", "leather_coif", "silken_cowl", "horned_helmet", "sages_hat"]
HEMLOCK_STOCK_BOOTS    = ["worn_boots", "heavy_boots", "trackers_boots", "soft_slippers", "bronze_sabatons"]
HEMLOCK_STOCK_ACCESSORIES = ["copper_ring", "warriors_bracer", "scouts_bracer", "scholars_bracelet"]
HEMLOCK_STOCK_CONSUMABLES = ["healing_herb", "bandage", "tonic", "torch", "antidote"]

CONSUMABLES = {
    "potion_standard": {"name": "Health Potion", "hp_restore": 25, "value": 15, "tier": 2,
                        "description": "A standard restorative brew. Smells like copper and honey."},
    "adventurers_pack": {"name": "Adventurer's Pack", "hp_restore": 0, "value": 0, "on_use": "starter_kit", "description": "starter pack — use to open"},
    "lightstone": {
        "name": "Lightstone",
        "value": 25,
        "description": "A wisp's core, still glowing. Permanent light source. Does not deplete.",
        "tier": 2,
    },
    "healing_herb":   {"name": "Healing Herb",    "hp_restore": 8,  "value": 10, "tier": 1},
    "bandage":        {"name": "Bandage",          "hp_restore": 5,  "value": 6,  "tier": 1},
    "tonic":          {"name": "Tonic",            "hp_restore": 15, "value": 20, "tier": 2},
    "elixir":         {"name": "Elixir",           "hp_restore": 30, "value": 50, "tier": 4},
    "hi_potion":      {"name": "Hi-Potion",        "hp_restore": 20, "value": 30, "tier": 3},
    "phoenix_down":   {"name": "Phoenix Down",     "hp_restore": 50, "value": 80, "description": "A feather of rebirth. Restores a great deal of HP.", "tier": 4},
    "ether":          {"name": "Ether",             "value": 25, "description": "A shimmering blue liquid. Restores mental clarity.", "tier": 3},
    "eye_drops":      {"name": "Eye Drops",         "value": 6,  "on_use": "cure_blind", "description": "Clears blurred vision.", "tier": 1},
    # Flavor/Event items
    "torch":          {"name": "Torch",            "value": 2, "description": "A simple torch. Lights the way.", "tier": 1},
    "aeridor_shard":  {"name": "Aeridor Crystal Shard", "value": 60, "tier": 3},
    "tonberry_knife": {"name": "Tonberry's Knife",      "value": 40, "tier": 3},
    "lucky_charm":    {"name": "Lucky Charm",          "value": 15, "on_use": "luck_roll_bonus", "tier": 2},
    "antidote":       {"name": "Antidote",             "value": 8,  "on_use": "cure_poison", "tier": 1},
    # Herbalism Ingredients
    "silver_moss":    {"name": "Silvermoss",           "value": 5, "description": "A glowing moss found near water.", "tier": 2},
    "dire_root":      {"name": "Dire Root",            "value": 10, "description": "A tough, bitter root from deep woods.", "tier": 3},
    "blood_thistle":  {"name": "Blood Thistle",        "value": 8, "description": "A prickly red flower.", "tier": 2},
    "honey_sap":      {"name": "Honey Sap",            "value": 5, "description": "Sweet, sticky sap from ancient trees.", "tier": 1},
    "gilded_mushroom": {"name": "Gilded Mushroom",     "value": 40, "description": "A rare, gold-capped mushroom. Hemlock pays well for these.", "tier": 5},
    "mognet_letter":   {"name": "Mognet Letter",       "value": 0,  "description": "A sealed letter addressed to 'Someone in Oakhaven'.", "tier": 0},
    "panacea":        {"name": "Panacea",             "value": 50, "description": "Cures all status ailments.", "tier": 4},
    "gold_needle":    {"name": "Gold Needle",         "value": 15, "description": "Cures petrification.", "tier": 2},
    "maidens_kiss":   {"name": "Maiden's Kiss",       "value": 10, "description": "Cures the 'Toad' status.", "tier": 2},
    "soft":           {"name": "Soft",                "value": 12, "description": "Cures petrification.", "tier": 2},
}

ALIASES = {
    "health_potion": "potion_standard",
    "herb": "healing_herb",
    "pack": "adventurers_pack",
    "light": "lightstone",
    "wisp_core": "lightstone",
    "shard": "aeridor_shard",
    "knife": "tonberry_knife",
    "staff": "wooden_staff",
    "bow": "shortbow",
    "fur": "fur_cloak",
    "charm": "lucky_charm",
    "anti": "antidote",
    "mushroom": "gilded_mushroom",
    "letter": "mognet_letter",
    # Headgear / Boots / Accessories
    "helm":     "iron_helm",
    "cap":      "worn_cap",
    "boots":    "worn_boots",
    "ring":     "copper_ring",
    "bracer":   "warriors_bracer",
    "bracelet": "scholars_bracelet",
    "circlet":  "arcane_circlet",
    # EQ / FF aliases
    "potion":   "hi_potion",
    "hipot":    "hi_potion",
    "phoenix":  "phoenix_down",
    "feather":  "phoenix_down",
    "drops":    "eye_drops",
    "katana":   "masamune",
    "avenger":  "fiery_avenger",
    "lotus":    "black_lotus",
    "mox":      "mox_pearl",
    "belt":     "giant_belt",
    "gauntlets":"ogre_gauntlets",
    "needle":   "gold_needle",
    "kiss":     "maidens_kiss",
    "excalibur":"excalibur_ff",
    "ragnarok": "ragnarok_ff",
    "ultima":   "ultima_weapon",
    "vorpal":   "vorpal_sword",
    "holy":     "holy_avenger",
    "genji":    "genji_armor",
    "brilliance":"brilliance_helm",
}
