WEAPONS = {
    # Tier 1
    "rusty_dagger":   {"name": "Rusty Dagger",    "attack_bonus": 0, "damage_die": 6,  "damage_bonus": 0, "value": 12,   "tier": 1, "classes": ["Rogue", "Shadowblade", "Trickster", "Mage", "Wizard", "Necromancer", "Ranger", "Warden", "Hunter"]},
    "wooden_club":    {"name": "Wooden Club",      "attack_bonus": 0, "damage_die": 6,  "damage_bonus": 0, "value": 8,   "tier": 1, "classes": ["Warrior", "Shadowknight", "Cleric", "High Priest", "Paladin", "Shaman"]},
    "wooden_staff":   {"name": "Wooden Staff",    "attack_bonus": 1, "damage_die": 6,  "damage_bonus": 0, "value": 18,   "tier": 1, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "shortbow":       {"name": "Shortbow",         "attack_bonus": 1, "damage_die": 6,  "damage_bonus": 0, "value": 28,  "tier": 1, "classes": ["Ranger", "Warden", "Hunter", "Rogue", "Shadowblade", "Trickster"]},
    "rusty_hand_axe": {"name": "Rusty Hand Axe",   "attack_bonus": 1, "damage_die": 6,  "damage_bonus": 0, "value": 22,  "tier": 1, "classes": ["Warrior", "Paladin", "Shadowknight", "Ranger", "Warden", "Hunter"]},
    "rusty_stiletto": {"name": "Rusty Stiletto",   "attack_bonus": 1, "damage_die": 6,  "damage_bonus": 0, "value": 24,  "tier": 1, "classes": ["Rogue", "Shadowblade", "Trickster"]},
    "rusty_mace":     {"name": "Rusty Mace",       "attack_bonus": 1, "damage_die": 6,  "damage_bonus": 0, "value": 20,  "tier": 1, "classes": ["Cleric", "High Priest", "Shaman", "Warrior", "Paladin", "Shadowknight"]},

    # Tier 2
    "iron_sword":     {"name": "Iron Sword",       "attack_bonus": 2, "damage_die": 8,  "damage_bonus": 2, "value": 260,  "tier": 2, "classes": ["Warrior", "Paladin", "Shadowknight", "Ranger", "Hunter", "Warden"]},
    "iron_staff":     {"name": "Iron-Shod Staff", "attack_bonus": 2, "damage_die": 8,  "damage_bonus": 2, "value": 255,  "tier": 2, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "iron_spear":     {"name": "Iron Spear",       "attack_bonus": 2, "damage_die": 8,  "damage_bonus": 2, "value": 270,  "tier": 2, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Ranger", "Warden", "Hunter", "Paladin"]},
    "crossbow":       {"name": "Crossbow",         "attack_bonus": 3, "damage_die": 8,  "damage_bonus": 2, "value": 295,  "tier": 2, "droppable_only": True, "classes": ["Ranger", "Warden", "Hunter", "Rogue", "Shadowblade", "Trickster"]},
    "iron_battle_axe":{"name": "Iron Battle Axe",  "attack_bonus": 3, "damage_die": 8,  "damage_bonus": 2, "value": 280,  "tier": 2, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "iron_dirk":      {"name": "Iron Dirk",        "attack_bonus": 2, "damage_die": 8,  "damage_bonus": 2, "value": 260,  "tier": 2, "classes": ["Rogue", "Shadowblade", "Trickster", "Ranger", "Hunter", "Warden"]},
    "iron_morning_star":{"name": "Iron Morning Star","attack_bonus": 2, "damage_die": 8,  "damage_bonus": 2, "value": 265,  "tier": 2, "classes": ["Cleric", "High Priest", "Shaman", "Warrior", "Paladin", "Shadowknight"]},

    # Tier 3
    "steel_longsword":{"name": "Steel Longsword",  "attack_bonus": 4, "damage_die": 8,  "damage_bonus": 4, "value": 800,  "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "steel_dagger":   {"name": "Steel Dagger",     "attack_bonus": 5, "damage_die": 8, "damage_bonus": 4, "value": 950, "tier": 3, "droppable_only": True, "classes": ["Rogue", "Shadowblade", "Trickster", "Ranger", "Hunter", "Warden"]},
    "flame_sword":    {"name": "Flame Sword",      "attack_bonus": 4, "damage_die": 8,  "damage_bonus": 4, "value": 870,  "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Mage", "Necromancer", "Wizard"],
                       "proc": {"name": "Engulfing Flames", "emoji": "🔥", "die": 4, "element": "fire"}},
    "ice_brand":      {"name": "Ice Brand",        "attack_bonus": 4, "damage_die": 8,  "damage_bonus": 4, "value": 895,  "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Mage", "Necromancer", "Wizard"],
                       "proc": {"name": "Frost Shock", "emoji": "❄️", "die": 4, "element": "ice"}},
    "flame_scepter":  {"name": "Flame Scepter",    "attack_bonus": 5, "damage_die": 8, "damage_bonus": 4, "value": 980, "tier": 3, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "Shaman", "High Priest"],
                       "proc": {"name": "Scorching Bolt", "emoji": "🔥", "die": 4, "element": "fire"}},
    "ghoulbane":      {"name": "Ghoulbane",        "attack_bonus": 5, "damage_die": 8,  "damage_bonus": 4, "value": 1050, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin", "Cleric", "High Priest", "Shaman"],
                       "proc": {"name": "Spirit Strike", "emoji": "👻", "die": 4, "element": "holy"}},
    "flametongue":    {"name": "Flametongue",      "attack_bonus": 5, "damage_die": 8,  "damage_bonus": 4, "value": 1150, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin"],
                       "proc": {"name": "Searing Strike", "emoji": "🔥", "die": 6, "element": "fire"}},
    "frostbrand":     {"name": "Frostbrand",       "attack_bonus": 5, "damage_die": 8,  "damage_bonus": 4, "value": 1150, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin"],
                       "proc": {"name": "Glacial Spike", "emoji": "❄️", "die": 6, "element": "ice"}},

    # Tier 4
    "resonance_staff": {"name": "Resonance Staff", "attack_bonus": 5, "damage_die": 10, "damage_bonus": 6, "value": 1200, "tier": 4, "classes": ["Mage", "Cleric", "High Priest", "Shaman", "Wizard", "Necromancer"], "droppable_only": True},
    "resonance_bow":  {"name": "Resonance Bow",    "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 1250, "tier": 4, "droppable_only": True, "classes": ["Ranger", "Warden", "Hunter"]},
    "aeridorian_axe": {"name": "Aeridorian Axe",   "attack_bonus": 7, "damage_die": 10, "damage_bonus": 6, "value": 1500, "tier": 4, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "masamune":       {"name": "Masamune",         "attack_bonus": 7, "damage_die": 10, "damage_bonus": 6, "value": 1700, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Trickster", "Shadowblade"], "droppable_only": True},
    "fiery_avenger":  {"name": "Fiery Avenger",    "attack_bonus": 7, "damage_die": 10, "damage_bonus": 6, "value": 1400, "tier": 4, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin"],
                       "proc": {"name": "Flames of Virtue", "emoji": "🔥", "die": 6, "element": "fire"}},
    "blood_sword":    {"name": "Blood Sword",      "attack_bonus": 6, "damage_die": 10,  "damage_bonus": 6, "value": 1300, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
                       "proc": {"name": "Blood Leech", "emoji": "🩸", "die": 6, "element": "drain"}},
    "shining_staff":  {"name": "Shining Staff",    "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 1300, "tier": 4, "classes": ["Mage", "Necromancer", "Cleric", "Shaman", "Wizard", "High Priest"], "droppable_only": True},
    "yoichi_bow":     {"name": "Yoichi Bow",       "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 1400, "tier": 4, "droppable_only": True, "classes": ["Ranger", "Warden", "Hunter"]},
    "sun_blade":      {"name": "Sun Blade",        "attack_bonus": 6, "damage_die": 10, "damage_bonus": 6, "value": 1800, "tier": 4, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin"],
                       "proc": {"name": "Sunfire", "emoji": "☀️", "die": 6, "element": "holy"}},
    "ykesha_sword":   {"name": "Sword of Ykesha",  "attack_bonus": 6, "damage_die": 10,  "damage_bonus": 6, "value": 1250, "tier": 4, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"],
                       "proc": {"name": "Ykesha's Curse", "emoji": "🟣", "die": 6, "element": "shadow"}},
    "disruption_mace":{"name": "Mace of Disruption","attack_bonus": 6, "damage_die": 10,  "damage_bonus": 6, "value": 1500, "tier": 4, "droppable_only": True, "classes": ["Cleric", "Shaman", "Paladin", "High Priest"],
                       "proc": {"name": "Disruption", "emoji": "💥", "die": 6, "element": "holy"}},

    # Tier 5
    "void_blade":     {"name": "Void Blade",       "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 3250, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Shadowblade"],
                       "proc": {"name": "Void Touch", "emoji": "🌑", "die": 8, "element": "void"}},
    "holy_avenger":   {"name": "Holy Avenger",     "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 3750, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin"],
                       "proc": {"name": "Holy Wrath", "emoji": "✨", "die": 8, "element": "holy"}},
    "vorpal_sword":   {"name": "Vorpal Sword",     "attack_bonus": 10,"damage_die": 12, "damage_bonus": 8, "value": 2833, "tier": 5, "classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Trickster", "Shadowblade"], "droppable_only": True,
                       "proc": {"name": "Vorpal Strike", "emoji": "⚡", "die": 8, "element": "vorpal"}},
    "staff_magi":     {"name": "Staff of the Magi","attack_bonus": 8, "damage_die": 12, "damage_bonus": 8, "value": 3750, "tier": 5, "classes": ["Mage", "Wizard", "Necromancer"], "droppable_only": True,
                       "proc": {"name": "Arcane Blast", "emoji": "🔮", "die": 8, "element": "arcane"}},
    "stardust_rod":   {"name": "Stardust Rod",     "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 3750, "tier": 5, "classes": ["Mage", "Wizard", "Necromancer"], "droppable_only": True,
                       "proc": {"name": "Cosmic Resonance", "emoji": "🌠", "die": 10, "element": "arcane"}},
    "soulfire":       {"name": "Soulfire",         "attack_bonus": 9, "damage_die": 10, "damage_bonus": 8, "value": 2666, "tier": 5, "classes": ["Paladin"], "droppable_only": True,
                       "proc": {"name": "Soulfire Blaze", "emoji": "🔥", "die": 8, "element": "fire"}},
    "excalibur_ff":   {"name": "Excalibur",        "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 3166, "tier": 5, "classes": ["Warrior", "Shadowknight", "Paladin"], "droppable_only": True,
                       "proc": {"name": "Excalibur's Light", "emoji": "✨", "die": 8, "element": "holy"}},
    "ragnarok_ff":    {"name": "Ragnarok",         "attack_bonus": 10,"damage_die": 12, "damage_bonus": 8, "value": 3000, "tier": 5, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
                       "proc": {"name": "Ragnarok Flame", "emoji": "🔥", "die": 8, "element": "fire"}},
    "ultima_weapon":  {"name": "Ultima Weapon",    "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 4333,"tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"],
                       "proc": {"name": "Ultima Burst", "emoji": "💠", "die": 8, "element": "arcane"}},
    "mjolnir":        {"name": "Mjolnir",          "attack_bonus": 9, "damage_die": 12, "damage_bonus": 8, "value": 3900, "tier": 5, "classes": ["Warrior", "Shadowknight", "Paladin", "Cleric", "High Priest", "Shaman"], "droppable_only": True,
                       "proc": {"name": "Lightning Bolt", "emoji": "⚡", "die": 8, "element": "lightning"}},

    # ══════════════════════════════════════════════════════════════
    # WARRIOR — Greatswords, Polearms, War Hammers
    # ══════════════════════════════════════════════════════════════

    # Tier 1
    "rusted_greatsword": {
        "name": "Rusted Greatsword", "attack_bonus": 1, "damage_die": 6,
        "damage_bonus": 0, "value": 20, "tier": 1,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },

    # Tier 2
    "iron_greatsword": {
        "name": "Iron Greatsword", "attack_bonus": 2, "damage_die": 6,
        "damage_bonus": 2, "value": 285, "tier": 2,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "iron_halberd": {
        "name": "Iron Halberd", "attack_bonus": 2, "damage_die": 6,
        "damage_bonus": 2, "value": 275, "tier": 2,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },

    # Tier 3
    "steel_greatsword": {
        "name": "Steel Greatsword", "attack_bonus": 4, "damage_die": 8,
        "damage_bonus": 4, "value": 845, "tier": 3,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "war_halberd": {
        "name": "War Halberd", "attack_bonus": 4, "damage_die": 8,
        "damage_bonus": 4, "value": 870, "tier": 3,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },

    # Tier 4
    "aeridorian_greatsword": {
        "name": "Aeridorian Greatsword", "attack_bonus": 7, "damage_die": 10,
        "damage_bonus": 6, "value": 1500, "tier": 4,
        "classes": ["Warrior", "Shadowknight", "Paladin"], "droppable_only": True,
    },
    "champion_spear": {
        "name": "Champion's Spear", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1350, "tier": 4,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },

    # Tier 5
    "spine_cleaver": {
        "name": "Spine Cleaver", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 2666, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "proc": {"name": "Bone Splinter", "emoji": "💀", "die": 8, "element": "physical"},
    },
    "champions_legacy": {
        "name": "Champion's Legacy", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 3500, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Shadowknight", "Paladin"],
    },

    # ══════════════════════════════════════════════════════════════
    # RANGER — Bows and Hunting Blades
    # ══════════════════════════════════════════════════════════════

    # Tier 1
    "hunting_bow": {
        "name": "Hunting Bow", "attack_bonus": 1, "damage_die": 6,
        "damage_bonus": 0, "value": 25, "tier": 1,
        "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"],
    },
    "skinning_knife": {
        "name": "Skinning Knife", "attack_bonus": 0, "damage_die": 6,
        "damage_bonus": 0, "value": 14, "tier": 1,
        "classes": ["Ranger", "Hunter", "Warden"],
    },

    # Tier 2
    "composite_bow": {
        "name": "Composite Bow", "attack_bonus": 3, "damage_die": 8,
        "damage_bonus": 2, "value": 290, "tier": 2, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "forester_shortbow": {
        "name": "Forester's Shortbow", "attack_bonus": 2, "damage_die": 8,
        "damage_bonus": 2, "value": 268, "tier": 2, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"],
    },

    # Tier 3
    "whisperwood_recurve": {
        "name": "Whisperwood Recurve", "attack_bonus": 5, "damage_die": 8,
        "damage_bonus": 4, "value": 820, "tier": 3, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "hunters_knife": {
        "name": "Hunter's Knife", "attack_bonus": 4, "damage_die": 8,
        "damage_bonus": 4, "value": 800, "tier": 3, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"],
    },

    # Tier 4
    "aeridor_longbow": {
        "name": "Aeridor Longbow", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1350, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Warden", "Hunter"],
    },
    "moonbow": {
        "name": "Moonbow", "attack_bonus": 7, "damage_die": 10,
        "damage_bonus": 6, "value": 1600, "tier": 4,
        "classes": ["Ranger", "Warden", "Hunter"], "droppable_only": True,
    },

    # Tier 5
    "silent_stalker_bow": {
        "name": "Silent Stalker Bow", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 3750, "tier": 5,
        "classes": ["Ranger", "Warden", "Hunter"], "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # MAGE — Wands, Orbs, and Focuses
    # ══════════════════════════════════════════════════════════════

    # Tier 1
    "apprentice_wand": {
        "name": "Apprentice Wand", "attack_bonus": 1, "damage_die": 6,
        "damage_bonus": 0, "value": 16, "tier": 1,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "novice_focus": {
        "name": "Novice Focus", "attack_bonus": 0, "damage_die": 6,
        "damage_bonus": 0, "value": 12, "tier": 1,
        "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"],
    },

    # Tier 2
    "crystal_wand": {
        "name": "Crystal Wand", "attack_bonus": 2, "damage_die": 8,
        "damage_bonus": 2, "value": 272, "tier": 2,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "resonance_focus": {
        "name": "Resonance Focus", "attack_bonus": 3, "damage_die": 8,
        "damage_bonus": 2, "value": 278, "tier": 2, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"],
    },

    # Tier 3
    "aeridor_wand": {
        "name": "Aeridor Wand", "attack_bonus": 5, "damage_die": 10,
        "damage_bonus": 4, "value": 920, "tier": 3, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "elder_orb": {
        "name": "Elder Orb", "attack_bonus": 4, "damage_die": 10,
        "damage_bonus": 4, "value": 895, "tier": 3,
        "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"], "droppable_only": True,
    },

    # Tier 4
    "void_orb": {
        "name": "Void Orb", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1400, "tier": 4,
        "classes": ["Mage", "Wizard", "Necromancer"], "droppable_only": True,
    },
    "the_whispering_wand": {
        "name": "The Whispering Wand", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1550, "tier": 4,
        "classes": ["Mage", "Necromancer", "Wizard"], "droppable_only": True,
    },

    # Tier 5
    "null_scepter": {
        "name": "Null Scepter", "attack_bonus": 9, "damage_die": 10,
        "damage_bonus": 8, "value": 3900, "tier": 5, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Necromancer"],
        "proc": {"name": "Null Void", "emoji": "🌑", "die": 8, "element": "void"},
    },

    # ══════════════════════════════════════════════════════════════
    # ROGUE — Daggers, Shadow Blades, and Thrown Weapons
    # ══════════════════════════════════════════════════════════════

    # Tier 1
    "shiv": {
        "name": "Shiv", "attack_bonus": 0, "damage_die": 6,
        "damage_bonus": 0, "value": 8, "tier": 1,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "throwing_knife": {
        "name": "Throwing Knife", "attack_bonus": 1, "damage_die": 6,
        "damage_bonus": 0, "value": 14, "tier": 1,
        "classes": ["Rogue", "Shadowblade", "Trickster", "Ranger", "Hunter", "Warden"],
    },

    # Tier 2
    "shadow_blade": {
        "name": "Shadow Blade", "attack_bonus": 3, "damage_die": 8,
        "damage_bonus": 2, "value": 295, "tier": 2,
        "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True,
    },
    "assassin_stiletto": {
        "name": "Assassin's Stiletto", "attack_bonus": 2, "damage_die": 8,
        "damage_bonus": 2, "value": 272, "tier": 2, "droppable_only": True,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },

    # Tier 3
    "gutting_knife": {
        "name": "Gutting Knife", "attack_bonus": 5, "damage_die": 8,
        "damage_bonus": 4, "value": 975, "tier": 3,
        "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True,
    },
    "obsidian_dagger": {
        "name": "Obsidian Dagger", "attack_bonus": 4, "damage_die": 8,
        "damage_bonus": 4, "value": 895, "tier": 3,
        "classes": ["Rogue", "Shadowblade", "Trickster", "Ranger", "Hunter", "Warden"], "droppable_only": True,
    },

    # Tier 4
    "whisper_blade": {
        "name": "Whisper Blade", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1350, "tier": 4,
        "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True,
    },
    "the_quiet_death": {
        "name": "The Quiet Death", "attack_bonus": 7, "damage_die": 10,
        "damage_bonus": 6, "value": 1550, "tier": 4,
        "classes": ["Rogue", "Trickster", "Shadowblade"], "droppable_only": True,
    },

    # Tier 5
    "voidstep_blade": {
        "name": "Voidstep Blade", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 2800, "tier": 5,
        "classes": ["Rogue", "Trickster", "Shadowblade"], "droppable_only": True,
        "proc": {"name": "Shadow Rift", "emoji": "🌑", "die": 8, "element": "void"},
    },
    "the_last_laugh": {
        "name": "The Last Laugh", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 3650, "tier": 5,
        "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # CLERIC — Maces, Flails, and War Hammers
    # ══════════════════════════════════════════════════════════════

    # Tier 1
    "acolyte_mace": {
        "name": "Acolyte's Mace", "attack_bonus": 1, "damage_die": 6,
        "damage_bonus": 0, "value": 18, "tier": 1,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "iron_flail": {
        "name": "Iron Flail", "attack_bonus": 0, "damage_die": 6,
        "damage_bonus": 0, "value": 16, "tier": 1,
        "classes": ["Cleric", "High Priest", "Shaman", "Warrior", "Paladin", "Shadowknight"],
    },

    # Tier 2
    "shrine_warhammer": {
        "name": "Shrine Warhammer", "attack_bonus": 2, "damage_die": 8,
        "damage_bonus": 2, "value": 272, "tier": 2,
        "classes": ["Cleric", "High Priest", "Shaman", "Warrior", "Paladin", "Shadowknight"],
    },
    "silver_mace": {
        "name": "Silver Mace", "attack_bonus": 3, "damage_die": 8,
        "damage_bonus": 2, "value": 285, "tier": 2, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },

    # Tier 3
    "temple_hammer": {
        "name": "Temple Hammer", "attack_bonus": 4, "damage_die": 10,
        "damage_bonus": 4, "value": 820, "tier": 3, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "sanctuary_mace": {
        "name": "Sanctuary Mace", "attack_bonus": 5, "damage_die": 10,
        "damage_bonus": 4, "value": 975, "tier": 3, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },

    # Tier 4
    "dawn_hammer": {
        "name": "Dawn Hammer", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1450, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "Shaman", "Paladin", "High Priest"],
    },
    "silent_one_mace": {
        "name": "Silent One's Mace", "attack_bonus": 6, "damage_die": 10,
        "damage_bonus": 6, "value": 1350, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },

    # Tier 5
    "morvenna_flail": {
        "name": "Morvenna's Flail", "attack_bonus": 9, "damage_die": 12,
        "damage_bonus": 8, "value": 3750, "tier": 5,
        "classes": ["Cleric", "Shaman", "Shadowknight", "High Priest"], "droppable_only": True,
        "proc": {"name": "Morvenna's Wail", "emoji": "🟣", "die": 8, "element": "shadow"},
    },
    "voice_of_dawn": {
        "name": "Voice of Dawn", "attack_bonus": 10, "damage_die": 12,
        "damage_bonus": 8, "value": 2833, "tier": 5,
        "classes": ["Cleric", "Shaman", "Paladin", "High Priest"], "droppable_only": True,
    },
}

# --- Legacy Compatibility for Renamed Weapons ---
WEAPONS["hand_axe"]     = WEAPONS["rusty_hand_axe"]
WEAPONS["stiletto"]     = WEAPONS["rusty_stiletto"]
WEAPONS["mace"]         = WEAPONS["rusty_mace"]
WEAPONS["spear"]        = WEAPONS["iron_spear"]
WEAPONS["battle_axe"]   = WEAPONS["iron_battle_axe"]
WEAPONS["morning_star"] = WEAPONS["iron_morning_star"]
WEAPONS["longsword"]    = WEAPONS["steel_longsword"]
WEAPONS["steel_blade"]  = WEAPONS["steel_dagger"]
WEAPONS["defender"]     = WEAPONS["flame_scepter"]

ARMOR = {
    # Tier 1
    "travelers_cloak":  {"name": "Traveler's Cloak",  "defense_bonus": 0, "value": 8,   "tier": 1},
    "leather_armor":    {"name": "Leather Armor",     "defense_bonus": 2, "value": 28,  "tier": 1},
    "mages_robe":       {"name": "Mage's Robe",       "defense_bonus": 1, "value": 20,  "tier": 1, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "bronze_armor":     {"name": "Bronze Armor",      "defense_bonus": 3, "value": 38,  "tier": 1, "classes": ["Warrior", "Paladin", "Shadowknight", "Ranger", "Hunter", "Warden"]},
    "fur_cloak":        {"name": "Fur Cloak",         "defense_bonus": 2, "value": 22,  "tier": 1},

    # Tier 2
    "studded_leather":  {"name": "Studded Leather",   "defense_bonus": 3, "value": 258,  "tier": 2, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"]},
    "chainmail":        {"name": "Chainmail",          "defense_bonus": 5, "value": 295,  "tier": 2, "classes": ["Warrior", "Paladin", "Shadowknight", "Ranger", "Hunter", "Warden", "Cleric", "High Priest", "Shaman"]},
    "silken_robe":      {"name": "Silken Robe",       "defense_bonus": 2, "value": 262,  "tier": 2, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "black_garb":       {"name": "Black Garb",        "defense_bonus": 5, "value": 280,  "tier": 2, "classes": ["Rogue", "Shadowblade", "Trickster", "Ranger", "Hunter", "Warden"]},

    # Tier 3
    "half_plate":       {"name": "Half Plate",         "defense_bonus": 7, "value": 920, "tier": 3, "classes": ["Warrior", "Shadowknight", "Paladin"]},
    "flame_mail":       {"name": "Flame Mail",        "defense_bonus": 7, "value": 970, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "ice_armor":        {"name": "Ice Armor",         "defense_bonus": 7, "value": 970, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "mithral_shirt":    {"name": "Mithral Chain Shirt","defense_bonus": 6, "value": 1150, "tier": 3, "classes": ["Warrior", "Paladin", "Shadowknight", "Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"], "droppable_only": True},
    "invoker_vestment": {"name": "Invoker's Vestment", "defense_bonus": 3, "stat_bonus": {"int": 1}, "value": 895, "tier": 3, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer"]},

    # Tier 4
    "full_plate":       {"name": "Full Plate",         "defense_bonus": 10, "stat_bonus": {"str": 1}, "value": 1500, "tier": 4, "droppable_only": True, "classes": ["Warrior", "Shadowknight", "Paladin"]},
    "diamond_armor":    {"name": "Diamond Armor",     "defense_bonus": 10, "value": 1350, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True},
    "arcane_vestment":  {"name": "Arcane Vestment",    "defense_bonus": 5, "stat_bonus": {"int": 1}, "hp_bonus": 5,  "value": 1200, "tier": 4, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"], "droppable_only": True},
    "void_vestment":    {"name": "Void Vestment",      "defense_bonus": 5, "stat_bonus": {"int": 1}, "hp_bonus": 5,  "value": 1500, "tier": 4, "classes": ["Mage", "Wizard", "Necromancer"], "droppable_only": True},

    # Tier 5
    "aeridorian_plate": {"name": "Aeridorian Plate",  "defense_bonus": 12,"value": 1700, "tier": 5, "droppable_only": True},
    "rubicite_armor":   {"name": "Rubicite Armor",    "defense_bonus": 12,"value": 2666, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "dragon_scale":     {"name": "Dragon Scale Mail", "defense_bonus": 9,"value": 3166, "tier": 5, "droppable_only": True},
    "ethereal_plate":   {"name": "Ethereal Plate",    "defense_bonus": 12, "stat_bonus": {"str": 1}, "hp_bonus": 8,  "value": 3666, "tier": 5, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True},
    "arcanist_shroud":  {"name": "Arcanist's Shroud",  "defense_bonus": 6, "stat_bonus": {"int": 2}, "hp_bonus": 10, "value": 3800, "tier": 5, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer"]},
    "archmage_robe":    {"name": "Robe of the Archmagi","defense_bonus": 6, "stat_bonus": {"int": 2}, "hp_bonus": 10, "value": 3166, "tier": 5, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer"]},
    "genji_armor":      {"name": "Genji Armor",       "defense_bonus": 12,"value": 3000, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Shadowblade", "Trickster"]},
    "adamantine_plate": {"name": "Adamantine Plate",   "defense_bonus": 12, "stat_bonus": {"str": 2}, "hp_bonus": 12, "value": 4000, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "voice_of_silence_armor": {"name": "Voice of Silence Armor", "defense_bonus": 10, "stat_bonus": {"wis": 3}, "hp_bonus": 8, "value": 3000, "tier": 5, "classes": ["Cleric", "Paladin", "High Priest", "Shaman"]},

    # ══════════════════════════════════════════════════════════════
    # WARRIOR — Plate Progression
    # ══════════════════════════════════════════════════════════════

    "iron_plating": {
        "name": "Iron Plating", "defense_bonus": 3, "value": 35, "tier": 1,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "battle_plate": {
        "name": "Battle Plate", "defense_bonus": 6, "value": 290, "tier": 2,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },
    "knights_plate": {
        "name": "Knight's Plate", "defense_bonus": 8, "value": 900, "tier": 3,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "warlord_plate":    {"name": "Warlord's Plate",    "defense_bonus": 10, "stat_bonus": {"str": 1}, "value": 1500, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True},
    "champion_plate":   {"name": "Champion's Plate",   "defense_bonus": 12, "stat_bonus": {"str": 2}, "hp_bonus": 10, "value": 2833, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},

    # ══════════════════════════════════════════════════════════════
    # RANGER — Natural Leather Progression
    # ══════════════════════════════════════════════════════════════

    "rangers_vest": {
        "name": "Ranger's Vest", "defense_bonus": 2, "value": 25, "tier": 1,
        "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"],
    },
    "scouts_leathers": {
        "name": "Scout's Leathers", "defense_bonus": 4, "value": 268, "tier": 2,
        "classes": ["Ranger", "Hunter", "Warden"], "droppable_only": True,
    },
    "whisperwood_garb": {
        "name": "Whisperwood Garb", "defense_bonus": 6, "value": 890, "tier": 3,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "ghost_leather": {
        "name": "Ghost Leather", "defense_bonus": 7, "value": 1400, "tier": 4,
        "classes": ["Ranger", "Hunter", "Warden"], "droppable_only": True,
    },
    "forest_sovereign_armor": {
        "name": "Forest Sovereign Armor", "defense_bonus": 9, "value": 2766, "tier": 5,
        "classes": ["Ranger", "Hunter", "Warden"],
    },

    # ══════════════════════════════════════════════════════════════
    # ROGUE — Shadow Cloth Progression
    # ══════════════════════════════════════════════════════════════

    "cutpurse_leathers": {
        "name": "Cutpurse Leathers", "defense_bonus": 2, "value": 20, "tier": 1,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "shadow_garb": {
        "name": "Shadow Garb", "defense_bonus": 4, "value": 275, "tier": 2,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "phantom_weave": {
        "name": "Phantom Weave", "defense_bonus": 6, "value": 910, "tier": 3, "droppable_only": True,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "void_cloth": {
        "name": "Void Cloth", "defense_bonus": 7, "value": 1450, "tier": 4,
        "classes": ["Rogue", "Trickster", "Shadowblade"], "droppable_only": True,
    },
    "void_mantle": {
        "name": "Void Mantle", "defense_bonus": 9, "value": 3900, "tier": 5,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },

    # ══════════════════════════════════════════════════════════════
    # MAGE — Arcane Robe Progression
    # ══════════════════════════════════════════════════════════════

    "novice_robes": {
        "name": "Novice Robes", "defense_bonus": 1, "value": 14, "tier": 1,
        "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"],
    },
    "channeler_robes": {
        "name": "Channeler's Robes", "defense_bonus": 3, "value": 262, "tier": 2,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },


    # ══════════════════════════════════════════════════════════════
    # CLERIC — Divine Armor Progression
    # ══════════════════════════════════════════════════════════════

    "acolyte_vestments": {
        "name": "Acolyte's Vestments", "defense_bonus": 2, "value": 20, "tier": 1,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "shrine_chainmail": {
        "name": "Shrine Chainmail", "defense_bonus": 5, "value": 278, "tier": 2,
        "classes": ["Cleric", "High Priest", "Shaman", "Warrior", "Shadowknight", "Paladin"],
    },
    "cleric_plate": {
        "name": "Cleric's Plate", "defense_bonus": 7, "value": 920, "tier": 3,
        "classes": ["Cleric", "High Priest", "Shaman", "Paladin"],
    },
    "saint_plate": {
        "name": "Saint's Plate", "defense_bonus": 8, "value": 1600, "tier": 4,
        "classes": ["Cleric", "Shaman", "Paladin", "High Priest"], "droppable_only": True,
    },
}

# ─── HEADGEAR ────────────────────────────────────────────────────────────────
HEADGEAR = {
    # Tier 1
    "worn_cap":          {"name": "Worn Cap",          "defense_bonus": 1, "value": 6,   "tier": 1},
    "iron_helm":         {"name": "Iron Helm",          "defense_bonus": 2, "value": 24,  "tier": 1, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "scouts_hood":       {"name": "Scout's Hood",       "defense_bonus": 1, "value": 20,  "tier": 1, "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"]},
    "mages_cap":         {"name": "Mage's Cap",         "defense_bonus": 1, "value": 16,  "tier": 1, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "bronze_helm":       {"name": "Bronze Helm",        "defense_bonus": 1, "value": 22,  "tier": 1},

    # Tier 2
    "steel_visor":       {"name": "Steel Visor",        "defense_bonus": 3, "value": 272,  "tier": 2, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "leather_coif":      {"name": "Leather Coif",       "defense_bonus": 2, "value": 258,  "tier": 2, "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"]},
    "silken_cowl":       {"name": "Silken Cowl",        "defense_bonus": 2, "value": 262,  "tier": 2, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "horned_helmet":     {"name": "Horned Helmet",      "defense_bonus": 3, "value": 268,  "tier": 2, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "sages_hat":         {"name": "Sage's Hat",         "defense_bonus": 2, "value": 272,  "tier": 2, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},

    # Tier 3
    "siege_helm":        {"name": "Siege Helm",         "defense_bonus": 2, "value": 840, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "stalkers_cowl":     {"name": "Stalker's Cowl",     "defense_bonus": 2, "value": 820,  "tier": 3, "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"], "droppable_only": True},
    "arcane_circlet":    {"name": "Arcane Circlet",     "defense_bonus": 1, "value": 830,  "tier": 3, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "flame_helm":        {"name": "Flame Helm",         "defense_bonus": 2, "value": 835,  "tier": 3, "droppable_only": True},
    "gold_hairpin":      {"name": "Gold Hairpin",       "defense_bonus": 2, "value": 820,  "tier": 3, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "ribbon":            {"name": "Ribbon",             "defense_bonus": 2, "value": 920, "tier": 3, "droppable_only": True},
    "executioner_hood":  {"name": "Executioner's Hood", "defense_bonus": 1, "value": 815,  "tier": 3, "classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Shadowblade", "Trickster"]},
    "circlet_persuasion":{"name": "Circlet of Persuasion","defense_bonus": 1, "value": 975, "tier": 3, "droppable_only": True},

    # Tier 4
    "aeridorian_helm":   {"name": "Aeridorian Helm",    "defense_bonus": 3, "value": 1400, "tier": 4, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "shadowweave_mask":  {"name": "Shadowweave Mask",   "defense_bonus": 3, "value": 1350, "tier": 4, "droppable_only": True, "classes": ["Rogue", "Shadowblade", "Trickster"]},
    "resonance_crown":   {"name": "Resonance Crown",    "defense_bonus": 2, "value": 1400, "tier": 4, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "diamond_helm":      {"name": "Diamond Helm",       "defense_bonus": 3, "value": 1350, "tier": 4, "droppable_only": True},

    # Tier 5
    "void_helm":         {"name": "Void Helm",          "defense_bonus": 3, "value": 3500, "tier": 5, "droppable_only": True},
    "brilliance_helm":   {"name": "Helm of Brilliance", "defense_bonus": 3, "value": 3750, "tier": 5, "droppable_only": True},
    "crown_stars":       {"name": "Crown of Stars",     "defense_bonus": 2, "value": 3650, "tier": 5, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "genji_helm":        {"name": "Genji Helm",         "defense_bonus": 3, "value": 3500, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Shadowblade", "Trickster"]},

    # ══════════════════════════════════════════════════════════════
    # WARRIOR — Helms
    # ══════════════════════════════════════════════════════════════

    "soldiers_cap": {
        "name": "Soldier's Cap", "defense_bonus": 1, "value": 18, "tier": 1,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "battle_visor": {
        "name": "Battle Visor", "defense_bonus": 2, "value": 268, "tier": 2,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },
    "warlord_helm": {
        "name": "Warlord's Helm", "defense_bonus": 3, "value": 860, "tier": 3,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "champion_helm": {
        "name": "Champion's Helm", "defense_bonus": 3, "value": 1450, "tier": 4, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "the_iron_crown": {
        "name": "The Iron Crown", "defense_bonus": 4, "value": 2666, "tier": 5,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # RANGER — Hoods and Tracking Gear
    # ══════════════════════════════════════════════════════════════

    "ranger_hat": {
        "name": "Ranger's Hat", "defense_bonus": 1, "value": 18, "tier": 1,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "camouflage_cowl": {
        "name": "Camouflage Cowl", "defense_bonus": 2, "value": 260, "tier": 2, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "whisperwood_cowl": {
        "name": "Whisperwood Cowl", "defense_bonus": 2, "value": 840, "tier": 3,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "hunters_visor": {
        "name": "Hunter's Visor", "defense_bonus": 3, "value": 1400, "tier": 4,
        "classes": ["Ranger", "Hunter", "Warden"], "droppable_only": True,
    },
    "forest_crown": {
        "name": "Forest Crown", "defense_bonus": 4, "value": 3750, "tier": 5, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden"],
    },

    # ══════════════════════════════════════════════════════════════
    # MAGE — Arcane Headgear
    # ══════════════════════════════════════════════════════════════

    "ember_cowl": {
        "name": "Ember Cowl", "defense_bonus": 1, "value": 15, "tier": 1,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "channeler_hat": {
        "name": "Channeler's Hat", "defense_bonus": 1, "value": 258, "tier": 2,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "invoker_circlet": {
        "name": "Invoker's Circlet", "defense_bonus": 2, "value": 835, "tier": 3,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "arcanist_circlet": {
        "name": "Arcanist's Circlet", "defense_bonus": 3, "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "void_crown": {
        "name": "Void Crown", "defense_bonus": 4, "value": 3750, "tier": 5,
        "classes": ["Mage", "Wizard", "Necromancer"], "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # ROGUE — Shadow Hoods and Masks
    # ══════════════════════════════════════════════════════════════

    "shadow_cap": {
        "name": "Shadow Cap", "defense_bonus": 1, "value": 15, "tier": 1,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "phantom_hood": {
        "name": "Phantom Hood", "defense_bonus": 1, "value": 258, "tier": 2,
        "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True,
    },
    "void_cowl": {
        "name": "Void Cowl", "defense_bonus": 2, "value": 850, "tier": 3, "droppable_only": True,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "ghost_mask": {
        "name": "Ghost Mask", "defense_bonus": 3, "value": 1350, "tier": 4,
        "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True,
    },
    "the_last_face": {
        "name": "The Last Face", "defense_bonus": 4, "value": 3750, "tier": 5,
        "classes": ["Rogue", "Shadowblade", "Trickster"],
    },

    # ══════════════════════════════════════════════════════════════
    # CLERIC — Mitres and Devotional Headgear
    # ══════════════════════════════════════════════════════════════

    "novice_hood": {
        "name": "Novice Hood", "defense_bonus": 1, "value": 15, "tier": 1,
        "classes": ["Cleric", "High Priest", "Shaman", "Mage", "Wizard", "Necromancer"],
    },
    "priest_mitre": {
        "name": "Priest's Mitre", "defense_bonus": 2, "value": 262, "tier": 2, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "temple_circlet": {
        "name": "Temple Circlet", "defense_bonus": 2, "value": 840, "tier": 3, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "high_priest_mitre": {
        "name": "High Priest's Mitre", "defense_bonus": 3, "value": 1450, "tier": 4,
        "classes": ["Cleric", "High Priest", "Shaman"], "droppable_only": True,
    },
    "silence_crown": {
        "name": "Silence Crown", "defense_bonus": 4, "value": 2666, "tier": 5,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

# ─── BOOTS ───────────────────────────────────────────────────────────────────
BOOTS = {
    # Tier 1
    "worn_boots":        {"name": "Worn Boots",         "defense_bonus": 1, "value": 8,   "tier": 1},
    "heavy_boots":       {"name": "Heavy Boots",        "defense_bonus": 2, "value": 26,  "tier": 1, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "trackers_boots":    {"name": "Tracker's Boots",    "defense_bonus": 1, "value": 22,  "tier": 1, "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"]},
    "soft_slippers":     {"name": "Soft Slippers",      "defense_bonus": 1, "value": 16,  "tier": 1, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "bronze_sabatons":   {"name": "Bronze Sabatons",   "defense_bonus": 1, "value": 24,  "tier": 1},

    # Tier 2
    "iron_shod_boots":   {"name": "Iron-Shod Boots",   "defense_bonus": 3, "value": 268,  "tier": 2, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "shadow_treads":     {"name": "Shadow Treads",      "defense_bonus": 2, "value": 262,  "tier": 2, "classes": ["Rogue", "Shadowblade", "Trickster"], "droppable_only": True},
    "foresters_boots":   {"name": "Forester's Boots",  "defense_bonus": 2, "value": 258,  "tier": 2, "droppable_only": True, "classes": ["Ranger", "Hunter", "Warden"]},
    "ley_walkers":       {"name": "Ley-Walker Sandals","defense_bonus": 2, "value": 258,  "tier": 2, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},

    # Tier 3
    "wardens_greaves":   {"name": "Warden's Greaves",  "defense_bonus": 2, "value": 840, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "whisperwood_boots": {"name": "Whisperwood Boots", "defense_bonus": 2, "value": 830, "tier": 3, "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"]},
    "resonance_treads":  {"name": "Resonance Treads",  "defense_bonus": 1, "value": 835, "tier": 3, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},
    "flame_greaves":     {"name": "Flame Greaves",     "defense_bonus": 2, "value": 825,  "tier": 3, "droppable_only": True},
    "striding_boots":    {"name": "Boots of Striding",  "defense_bonus": 1, "value": 820,  "tier": 3, "droppable_only": True},

    # Tier 4
    "aeridorian_greaves":{"name": "Aeridorian Greaves","defense_bonus": 3, "value": 1450, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True},
    "shadow_striders":   {"name": "Shadow Striders",   "defense_bonus": 3, "value": 1400, "tier": 4, "droppable_only": True, "classes": ["Rogue", "Shadowblade", "Trickster"]},
    "diamond_boots":     {"name": "Diamond Boots",     "defense_bonus": 3, "value": 1400, "tier": 4, "droppable_only": True},
    "winged_boots":      {"name": "Winged Boots",       "defense_bonus": 2, "value": 1600, "tier": 4, "droppable_only": True},
    "boots_speed":       {"name": "Boots of Speed",     "defense_bonus": 2, "value": 1500, "tier": 4, "droppable_only": True},

    # Tier 5
    "void_striders":     {"name": "Void Striders",     "defense_bonus": 3, "value": 3750, "tier": 5, "droppable_only": True},
    "hermes_boots":      {"name": "Hermes Boots",       "defense_bonus": 2, "value": 2666, "tier": 5, "droppable_only": True},
    "genji_boots":       {"name": "Genji Boots",        "defense_bonus": 3, "value": 2833, "tier": 5, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight", "Rogue", "Shadowblade", "Trickster"]},
    "seven_league_boots":{"name": "7-League Boots",    "defense_bonus": 2, "value": 3750, "tier": 5, "droppable_only": True},

    # ══════════════════════════════════════════════════════════════
    # WARRIOR — Iron and Battle Greaves
    # ══════════════════════════════════════════════════════════════

    "iron_greaves": {
        "name": "Iron Greaves", "defense_bonus": 3, "value": 272, "tier": 2,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },
    "battle_greaves": {
        "name": "Battle Greaves", "defense_bonus": 2, "value": 850, "tier": 3,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "warlord_greaves": {
        "name": "Warlord's Greaves", "defense_bonus": 3, "value": 1450, "tier": 4,
        "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True,
    },
    "champion_sabatons": {
        "name": "Champion's Sabatons", "defense_bonus": 4, "value": 2666, "tier": 5,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },

    # ══════════════════════════════════════════════════════════════
    # RANGER — Trail and Forest Boots
    # ══════════════════════════════════════════════════════════════

    "trail_boots": {
        "name": "Trail Boots", "defense_bonus": 2, "value": 260, "tier": 2,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "whisper_stride": {
        "name": "Whisper Stride", "defense_bonus": 2, "value": 835, "tier": 3, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "silent_runner": {
        "name": "Silent Runner", "defense_bonus": 2, "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Hunter", "Warden"],
    },
    "forest_stride": {
        "name": "Forest Stride", "defense_bonus": 3, "value": 3900, "tier": 5,
        "classes": ["Ranger", "Hunter", "Warden"],
        "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # MAGE — Arcane Sandals
    # ══════════════════════════════════════════════════════════════

    "resonance_sandals": {
        "name": "Resonance Sandals", "defense_bonus": 2, "value": 258, "tier": 2,
        "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "arcane_walkers": {
        "name": "Arcane Walkers", "defense_bonus": 1, "value": 830, "tier": 3,
        "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"],
    },
    "void_walkers": {
        "name": "Void Walkers", "defense_bonus": 2, "value": 1400, "tier": 4,
        "classes": ["Mage", "Wizard", "Necromancer"],
        "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # CLERIC — Blessed Footwear
    # ══════════════════════════════════════════════════════════════

    "blessed_sandals": {
        "name": "Blessed Sandals", "defense_bonus": 2, "value": 260, "tier": 2,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "shrine_greaves": {
        "name": "Shrine Greaves", "defense_bonus": 2, "value": 835, "tier": 3,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "saints_boots": {
        "name": "Saint's Boots", "defense_bonus": 3, "value": 1450, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "silence_treads": {
        "name": "Silence Treads", "defense_bonus": 3, "value": 2666, "tier": 5,
        "classes": ["Cleric", "High Priest", "Shaman"],
        "droppable_only": True,
    },
}

# ─── ACCESSORIES (rings / bracers / bracelets) ───────────────────────────────
ACCESSORIES = {
    # Tier 1
    "copper_ring":       {"name": "Copper Ring",        "defense_bonus": 1, "attack_bonus": 0, "value": 12,   "tier": 1},
    "warriors_bracer":   {"name": "Warrior's Bracer",   "defense_bonus": 1, "attack_bonus": 1, "value": 25,  "tier": 1, "classes": ["Warrior", "Paladin", "Shadowknight"]},
    "scouts_bracer":     {"name": "Scout's Bracer",     "defense_bonus": 1, "attack_bonus": 1, "value": 20,  "tier": 1, "classes": ["Ranger", "Hunter", "Warden", "Rogue", "Shadowblade", "Trickster"]},
    "scholars_bracelet": {"name": "Scholar's Bracelet", "defense_bonus": 1, "attack_bonus": 0, "value": 16,  "tier": 1, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},

    # Tier 2
    "iron_ring":         {"name": "Iron Ring",          "defense_bonus": 2, "attack_bonus": 1, "value": 258,  "tier": 2, "droppable_only": True},
    "oak_bracelet":      {"name": "Oak Bracelet",       "defense_bonus": 2, "attack_bonus": 1, "value": 262,  "tier": 2},
    "crystal_bracelet":  {"name": "Crystal Bracelet",  "defense_bonus": 1, "attack_bonus": 1, "value": 262,  "tier": 2, "droppable_only": True, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"]},

    # Tier 3
    "silver_ring":       {"name": "Silver Ring",        "defense_bonus": 1, "attack_bonus": 1, "value": 840,  "tier": 3, "droppable_only": True},
    "tricklebrook_charm":{"name": "Tricklebrook Charm","defense_bonus": 1, "attack_bonus": 0, "value": 820,  "tier": 3, "droppable_only": True},
    "aeridor_bangle":    {"name": "Aeridor Bangle",    "defense_bonus": 1, "attack_bonus": 2, "value": 870, "tier": 3, "droppable_only": True},
    "serpentine_bracer": {"name": "Serpentine Bracer", "defense_bonus": 1, "attack_bonus": 2, "value": 850,  "tier": 3, "droppable_only": True, "classes": ["Rogue", "Shadowblade", "Trickster", "Ranger", "Hunter", "Warden"]},
    "gold_ring":         {"name": "Gold Ring",          "defense_bonus": 1, "attack_bonus": 1, "value": 865, "tier": 3, "droppable_only": True},
    "ring_protection":   {"name": "Ring of Protection", "defense_bonus": 1, "attack_bonus": 1, "value": 920, "tier": 3, "droppable_only": True},
    "periapt_poison":    {"name": "Periapt of Poison",  "defense_bonus": 1, "attack_bonus": 0, "value": 840, "tier": 3, "droppable_only": True},

    # Tier 4
    "resonance_ring":    {"name": "Resonance Ring",    "defense_bonus": 2, "attack_bonus": 2, "value": 1450, "tier": 4, "droppable_only": True},
    "elaras_token":      {"name": "Elara's Token",     "defense_bonus": 1, "attack_bonus": 0, "value": 0,   "tier": 4, "droppable_only": True},
    "djarns_ring":       {"name": "Djarn's Ring",       "defense_bonus": 2, "attack_bonus": 3, "value": 1550, "tier": 4, "droppable_only": True},
    "bracers_defense":   {"name": "Bracers of Defense", "defense_bonus": 1, "attack_bonus": 0, "value": 1450, "tier": 4, "droppable_only": True},
    "amulet_health":     {"name": "Amulet of Health",   "defense_bonus": 1, "attack_bonus": 0, "value": 1350, "tier": 4, "droppable_only": True},
    "ogre_gauntlets":    {"name": "Ogre Gauntlets",     "defense_bonus": 0, "attack_bonus": 4, "value": 1700, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True},
    "displacement_cloak":{"name": "Displacement Cloak", "defense_bonus": 2, "attack_bonus": 0, "value": 1850, "tier": 4, "droppable_only": True},

    # Tier 5
    "void_band":         {"name": "Void Band",         "defense_bonus": 2, "attack_bonus": 3, "value": 3750, "tier": 5, "droppable_only": True},
    "mox_pearl":         {"name": "Mox Pearl",          "defense_bonus": 0, "attack_bonus": 3, "value": 4333,"tier": 5, "droppable_only": True},
    "giant_belt":        {"name": "Giant Strength Belt","defense_bonus": 0, "attack_bonus": 5, "value": 2666, "tier": 5, "classes": ["Warrior", "Paladin", "Shadowknight"], "droppable_only": True},
    "black_lotus":       {"name": "Black Lotus",        "defense_bonus": 0, "attack_bonus": 4, "value": 18333,"tier": 5, "classes": ["Wizard", "Necromancer"], "droppable_only": True},

    # ══════════════════════════════════════════════════════════════
    # WARRIOR — Gauntlets and Power Bracers
    # ══════════════════════════════════════════════════════════════

    "iron_gauntlets": {
        "name": "Iron Gauntlets", "defense_bonus": 1, "attack_bonus": 1,
        "value": 268, "tier": 2, "classes": ["Warrior", "Paladin", "Shadowknight"],
        "droppable_only": True,
    },
    "battle_bracer": {
        "name": "Battle Bracer", "defense_bonus": 1, "attack_bonus": 2,
        "value": 860, "tier": 3, "droppable_only": True, "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "warlords_gauntlets": {
        "name": "Warlord's Gauntlets", "defense_bonus": 1, "attack_bonus": 3,
        "value": 1450, "tier": 4, "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "champion_bracers": {
        "name": "Champion's Bracers", "defense_bonus": 2, "attack_bonus": 4,
        "value": 2666, "tier": 5, "classes": ["Warrior", "Paladin", "Shadowknight"],
        "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # RANGER — Precision Accessories
    # ══════════════════════════════════════════════════════════════

    "quiver_bracer": {
        "name": "Quiver Bracer", "defense_bonus": 1, "attack_bonus": 1,
        "value": 260, "tier": 2, "droppable_only": True, "classes": ["Ranger", "Hunter", "Warden"],
    },
    "hunters_charm": {
        "name": "Hunter's Charm", "defense_bonus": 1, "attack_bonus": 2,
        "value": 855, "tier": 3, "classes": ["Ranger", "Hunter", "Warden"],
    },
    "forest_ring": {
        "name": "Forest Ring", "defense_bonus": 1, "attack_bonus": 2,
        "value": 1400, "tier": 4, "classes": ["Ranger", "Hunter", "Warden"],
        "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # MAGE — Arcane Focuses and Rings
    # ══════════════════════════════════════════════════════════════

    "arcane_focus_ring": {
        "name": "Arcane Focus Ring", "defense_bonus": 0, "attack_bonus": 2,
        "value": 260, "tier": 2, "classes": ["Mage", "Wizard", "Necromancer"],
    },
    "resonance_orb_acc": {
        "name": "Resonance Orb", "defense_bonus": 0, "attack_bonus": 2,
        "value": 860, "tier": 3, "classes": ["Mage", "Wizard", "Necromancer", "Cleric", "High Priest", "Shaman"],
    },
    "void_focus": {
        "name": "Void Focus", "defense_bonus": 1, "attack_bonus": 3,
        "value": 1450, "tier": 4, "classes": ["Mage", "Wizard", "Necromancer"],
        "droppable_only": True,
    },

    # ══════════════════════════════════════════════════════════════
    # ROGUE — Precision and Luck Trinkets
    # ══════════════════════════════════════════════════════════════

    "shadow_ring": {
        "name": "Shadow Ring", "defense_bonus": 1, "attack_bonus": 1,
        "value": 258, "tier": 2, "classes": ["Rogue", "Shadowblade", "Trickster"],
        "droppable_only": True,
    },
    "phantom_bracer": {
        "name": "Phantom Bracer", "defense_bonus": 1, "attack_bonus": 2,
        "value": 850, "tier": 3, "classes": ["Rogue", "Shadowblade", "Trickster"],
    },
    "void_ring": {
        "name": "Void Ring", "defense_bonus": 1, "attack_bonus": 3,
        "value": 1400, "tier": 4, "droppable_only": True, "classes": ["Rogue", "Shadowblade", "Trickster"],
    },

    # ══════════════════════════════════════════════════════════════
    # CLERIC — Holy Symbols and Divine Relics
    # ══════════════════════════════════════════════════════════════

    "holy_symbol": {
        "name": "Holy Symbol", "defense_bonus": 1, "attack_bonus": 1,
        "value": 262, "tier": 2, "droppable_only": True, "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "blessed_rosary": {
        "name": "Blessed Rosary", "defense_bonus": 1, "attack_bonus": 1,
        "value": 855, "tier": 3, "classes": ["Cleric", "High Priest", "Shaman"],
    },
    "saints_medallion": {
        "name": "Saint's Medallion", "defense_bonus": 2, "attack_bonus": 1,
        "value": 1450, "tier": 4, "classes": ["Cleric", "High Priest", "Shaman"],
        "droppable_only": True,
    },
    "silence_sigil": {
        "name": "Silence Sigil", "defense_bonus": 2, "attack_bonus": 2,
        "value": 2666, "tier": 5, "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

# What Hemlock sells (Tier 1 ONLY — Oakhaven starter stock)
HEMLOCK_STOCK_WEAPONS = ['shortbow', 'rusty_hand_axe', 'rusty_stiletto', 'rusty_mace', 'wooden_staff', 'hunting_bow', 'skinning_knife', 'rusted_greatsword', 'apprentice_wand', 'novice_focus', 'shiv', 'throwing_knife', 'iron_flail', 'acolyte_mace']
HEMLOCK_STOCK_ARMOR   = ['leather_armor', 'mages_robe', 'bronze_armor', 'fur_cloak', 'iron_plating', 'rangers_vest', 'cutpurse_leathers', 'novice_robes', 'acolyte_vestments']
HEMLOCK_STOCK_HEADGEAR = ['iron_helm', 'scouts_hood', 'mages_cap', 'bronze_helm', 'soldiers_cap', 'ranger_hat', 'shadow_cap', 'ember_cowl', 'novice_hood']
HEMLOCK_STOCK_BOOTS    = ['worn_boots', 'heavy_boots', 'trackers_boots', 'soft_slippers', 'bronze_sabatons']
HEMLOCK_STOCK_ACCESSORIES = ['copper_ring', 'warriors_bracer', 'scouts_bracer', 'scholars_bracelet']
HEMLOCK_STOCK_CONSUMABLES = ['healing_herb', 'bandage', 'tonic', 'torch', 'antidote']

CONSUMABLES = {
    "potion_standard": {"name": "Health Potion", "hp_restore": 25, "value": 40, "tier": 2,
                        "description": "A standard restorative brew. Smells like copper and honey."},
    "adventurers_pack": {"name": "Adventurer's Pack", "hp_restore": 0, "value": 0, "on_use": "starter_kit", "description": "starter pack — use to open"},
    "lightstone": {
        "name": "Lightstone",
        "value": 25,
        "description": "A wisp's core, still glowing. Permanent light source. Does not deplete.",
        "tier": 2,
    },
    "healing_herb":   {"name": "Healing Herb",    "hp_restore": 8,  "value": 10,  "tier": 1},
    "bandage":        {"name": "Bandage",          "hp_restore": 5,  "value": 6,   "tier": 1},
    "tonic":          {"name": "Tonic",            "hp_restore": 15, "value": 20,  "tier": 2},
    "elixir":         {"name": "Elixir",           "hp_restore": 30, "value": 50,  "tier": 4},
    "hi_potion":      {"name": "Hi-Potion",        "hp_restore": 20, "value": 30,  "tier": 3},
    "phoenix_down":   {"name": "Phoenix Down",     "hp_restore": 50, "value": 80,  "description": "A feather of rebirth. Restores a great deal of HP.", "tier": 4},
    "ether":          {"name": "Ether",             "value": 60,  "description": "A shimmering blue liquid. Restores mental clarity.", "tier": 3},
    "eye_drops":      {"name": "Eye Drops",         "value": 12,  "on_use": "cure_blind", "description": "Clears blurred vision.", "tier": 1},
    # Flavor/Event items
    "torch":          {"name": "Torch",            "value": 15, "description": "A simple torch. Lights the way.", "tier": 1},
    "aeridor_shard":  {"name": "Aeridor Crystal Shard", "value": 100, "tier": 3},
    "tonberry_knife": {"name": "Tonberry's Knife",      "value": 100, "tier": 3},
    "lucky_charm":    {"name": "Lucky Charm",          "value": 40, "on_use": "luck_roll_bonus", "tier": 2},
    "antidote":       {"name": "Antidote",             "value": 8,   "on_use": "cure_poison", "tier": 1},
    # Herbalism Ingredients
    "silver_moss":    {"name": "Silvermoss",           "value": 40, "description": "A glowing moss found near water.", "tier": 2},
    "silverleaf":     {"name": "Silverleaf",           "value": 200, "description": "A rare, shimmering herb found on the Trade Road.", "tier": 3},
    "dire_root":      {"name": "Dire Root",            "value": 100, "description": "A tough, bitter root from deep woods.", "tier": 3},
    "blood_thistle":  {"name": "Blood Thistle",        "value": 40, "description": "A prickly red flower.", "tier": 2},
    "honey_sap":      {"name": "Honey Sap",            "value": 15, "description": "Sweet, sticky sap from ancient trees.", "tier": 1},
    "gilded_mushroom": {"name": "Gilded Mushroom",     "value": 600, "description": "A rare, gold-capped mushroom. Hemlock pays well for these.", "tier": 5},
    "mognet_letter":   {"name": "Mognet Letter",       "value": 0,  "description": "A sealed letter addressed to 'Someone in Oakhaven'.", "tier": 0},
    "panacea":        {"name": "Panacea",             "value": 80,  "description": "Cures all status ailments.", "tier": 4},
    "gold_needle":    {"name": "Gold Needle",         "value": 40, "description": "Cures petrification.", "tier": 2},
    "maidens_kiss":   {"name": "Maiden's Kiss",       "value": 40, "description": "Cures the 'Toad' status.", "tier": 2},
    "soft":           {"name": "Soft",                "value": 40, "description": "Cures petrification.", "tier": 2},
    # Craftable Buff Potions
    "xp_tonic":       {"name": "Experience Tonic",    "value": 60, "on_use": "xp_boost",  "description": "+25% XP on next hunt.",      "tier": 3},
    "hunters_draught": {"name": "Hunter's Draught",   "value": 55, "on_use": "hunt_bonus", "description": "+1 bonus hunt today.",       "tier": 3},
    "ironbark_tonic": {"name": "Ironbark Tonic",      "value": 50, "on_use": "def_boost",  "description": "+2 DEF until next combat.",  "tier": 3},
    "firebrew":       {"name": "Firebrew",            "value": 50, "on_use": "atk_boost",  "description": "+2 ATK until next combat.",  "tier": 3},
    "pearl":          {"name": "Pearl",          "value": 25,   "gem_tier": 1, "description": "A lustrous white pearl. Smooth and cold to the touch."},
    "topaz":          {"name": "Topaz",          "value": 50,   "gem_tier": 1, "description": "A pale golden stone that catches candlelight well."},
    "peridot":        {"name": "Peridot",        "value": 75,   "gem_tier": 1, "description": "Pale green. Found in the ruins occasionally, origin unclear."},
    "emerald":        {"name": "Emerald",        "value": 100,  "gem_tier": 1, "description": "Deep green. Worth more than most people earn in a month."},
    "opal":           {"name": "Opal",           "value": 150,  "gem_tier": 1, "description": "Shifts color in different light. Hemlock keeps a jar of them behind the clock."},
    "black_pearl":    {"name": "Black Pearl",    "value": 200,  "gem_tier": 2, "description": "A dark lustrous pearl. Rare enough that Hemlock straightens up when you show him."},
    "fire_opal":      {"name": "Fire Opal",      "value": 300,  "gem_tier": 2, "description": "Burns orange and red inside. Warm to the touch in a way that doesn't make sense."},
    "star_ruby":      {"name": "Star Ruby",      "value": 400,  "gem_tier": 2, "description": "A six-pointed light moves inside it when you turn it. Nobody explains why."},
    "fire_emerald":   {"name": "Fire Emerald",   "value": 500,  "gem_tier": 2, "description": "Deep green threaded with veins of red. Aeridorian resonance does strange things to gems."},
    "sapphire":       {"name": "Sapphire",       "value": 600,  "gem_tier": 3, "description": "Clear blue. This belonged to someone important once. They aren't around anymore."},
    "ruby":           {"name": "Ruby",           "value": 700,  "gem_tier": 3, "description": "Blood red. The deep ruins produce them occasionally. Nobody asks how."},
    "jacinth":        {"name": "Jacinth",        "value": 800,  "gem_tier": 3, "description": "Orange-red. The Aeridorian archives describe it as a focusing stone. For what, they don't say."},
    "black_sapphire": {"name": "Black Sapphire", "value": 850,  "gem_tier": 3, "description": "Deep black with a blue core. The light inside moves on its own. Don't stare."},
    "diamond":        {"name": "Diamond",        "value": 900,  "gem_tier": 3, "description": "Flawless. Heavy. Elara wouldn't say where the one on her desk came from."},
    "blue_diamond":   {"name": "Blue Diamond",   "value": 1000, "gem_tier": 3, "description": "The rarest thing you'll find in the ruins. The light inside it doesn't come from outside."},
}

def get_equipment(key: str) -> dict | None:
    """Returns an item from any gear registry if found. Returns None otherwise."""
    for reg in (WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES, CONSUMABLES):
        if key in reg:
            item = reg[key].copy()
            item["key"] = key
            return item
    return None

def get_caravan_stock():
    """
    Returns Tier 2 and Tier 3 purchasable (non-droppable) items for the Caravan.
    Items with droppable_only=True must be looted from monsters.
    """
    gear_keys = []
    consumable_keys = []
    for reg in (WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES):
        for k, v in reg.items():
            if v.get("tier") in (2, 3) and not v.get("droppable_only"):
                gear_keys.append(k)
    consumable_keys = ["potion_standard", "lightstone", "gold_needle", "maidens_kiss", "soft"]
    return gear_keys, consumable_keys


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
    "silverleaf": "silverleaf",
    # Headgear / Boots / Accessories
    "helm":     "iron_helm",
    "cap":      "worn_cap",
    "boots":    "worn_boots",
    "ring":     "copper_ring",
    "bracer":   "warriors_bracer",
    "bracelet": "scholars_bracelet",
    "circlet":  "arcane_circlet",
    "stiletto": "rusty_stiletto",
    "dirk":     "iron_dirk",
    "mace":     "rusty_mace",
    "star":     "iron_morning_star",
    "spear":    "iron_spear",
    "iron spear": "iron_spear",
    "axe":      "iron_battle_axe",
    "dagger":   "steel_dagger",
    "scepter":  "flame_scepter",
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
    "xptonic":      "xp_tonic",
    "xp tonic":     "xp_tonic",
    "draught":      "hunters_draught",
    "hunter draught":"hunters_draught",
    "ironbark":     "ironbark_tonic",
    "firebrew":     "firebrew",
}




# ── Aliases for new items ────────────────────────────────────────────────────
ALIASES.update({
    "greatsword":       "iron_greatsword",
    "halberd":          "iron_halberd",
    "warhammer":        "shrine_warhammer",
    "hunting":          "hunting_bow",
    "recurve":          "whisperwood_recurve",
    "longbow":          "aeridor_longbow",
    "wand":             "apprentice_wand",
    "orb":              "void_orb",
    "focus":            "resonance_focus",
    "shiv":             "shiv",
    "shadow":           "shadow_blade",
    "quiet":            "the_quiet_death",
    "flail":            "iron_flail",
    "hammer":           "shrine_warhammer",
    "dawn":             "dawn_hammer",
    "morvenna":         "morvenna_flail",
    "champion":         "champion_plate",
    "phantom":          "phantom_weave",
    "void cloth":       "void_cloth",
    "novice robes":     "novice_robes",
    "channeler":        "channeler_robes",
    "shrine mail":      "shrine_chainmail",
    "saint":            "saint_plate",
    "mitre":            "priest_mitre",
    "forest crown":     "forest_crown",
    "silence":          "silence_crown",
    "iron crown":       "the_iron_crown",
    "ghost mask":       "ghost_mask",
    "last face":        "the_last_face",
    "gauntlets":        "iron_gauntlets",
    "quiver":           "quiver_bracer",
    "hunters charm":    "hunters_charm",
    "holy symbol":      "holy_symbol",
    "rosary":           "blessed_rosary",
    "medallion":        "saints_medallion",
    "sigil":            "silence_sigil",
    "phantom bracer":   "phantom_bracer",
    "void ring":        "void_ring",
    "forest ring":      "forest_ring",
    "warlord bracer":   "warlords_gauntlets",
    "gem":              "pearl",
    "gems":             "pearl",
})