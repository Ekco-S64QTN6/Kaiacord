"""
fishing.py — Aethelgard Fishing System
=======================================
250 unique fish, 5 bait types, 5 poles.
Seasonal and time-of-day tables drive encounter weighting.

Fish categories: common · uncommon · rare · epic · legendary · mythic
Seasons:  spring / summer / autumn / winter
Times:    dawn / morning / midday / afternoon / evening / night
"""

# ── Season/time shorthand constants ──────────────────────────────────────────
_ALL_S  = ["spring", "summer", "autumn", "winter"]
_SP_SU  = ["spring", "summer"]
_AU_WI  = ["autumn", "winter"]
_SP     = ["spring"]
_SU     = ["summer"]
_AU     = ["autumn"]
_WI     = ["winter"]
_SP_AU  = ["spring", "autumn"]

_ALL_T  = ["dawn", "morning", "midday", "afternoon", "evening", "night"]
_DAY    = ["morning", "midday", "afternoon"]
_NIGHT  = ["evening", "night"]
_DAWN   = ["dawn"]
_DUSK   = ["evening"]
_DD     = ["dawn", "evening"]           # dawn and dusk
_NOTMID = ["dawn", "morning", "afternoon", "evening", "night"]

# ── Bait registry ─────────────────────────────────────────────────────────────
BAIT = {
    "earthworm": {
        "name": "Earthworm",
        "cost": 2,
        "catch_bonus": 0,
        "rarity_ceiling": "rare",       # max rarity accessible with this bait
        "preferred_cats": ["common", "uncommon"],
        "desc": "Classic. Reliable. Fish have been falling for it since before Oakhaven was founded.",
    },
    "fat_grub": {
        "name": "Fat Grub",
        "cost": 5,
        "catch_bonus": 5,
        "rarity_ceiling": "epic",
        "preferred_cats": ["uncommon", "rare"],
        "desc": "Wriggling and unpleasant. Exactly what most fish want.",
    },
    "glowfly": {
        "name": "Glowfly",
        "cost": 12,
        "catch_bonus": 10,
        "rarity_ceiling": "epic",
        "preferred_cats": ["rare", "epic"],
        "desc": "Catches the light in the water. Catches fish that want that light.",
    },
    "aeridor_lure": {
        "name": "Aeridor Lure",
        "cost": 30,
        "catch_bonus": 20,
        "rarity_ceiling": "legendary",
        "preferred_cats": ["epic", "legendary"],
        "desc": "Crystal-tipped. Hums faintly. Resonance-touched fish respond to it.",
    },
    "crystal_bait": {
        "name": "Crystal Bait",
        "cost": 100,
        "catch_bonus": 30,
        "rarity_ceiling": "mythic",
        "preferred_cats": ["legendary", "mythic"],
        "desc": "Aeridorian crystal dust, compressed into bait. The water around it goes still.",
    },
}

# ── Pole registry ──────────────────────────────────────────────────────────────
POLES = {
    "birchwood_rod": {
        "name": "Birchwood Rod",
        "cost": 0,
        "catch_bonus": 0,
        "bite_time_reduction": 0,   # seconds off waiting time
        "reel_window": 12,          # seconds to click Reel
        "desc": "Cut from the birch by the pond bank. It flexes alarmingly. It works.",
    },
    "ironwood_rod": {
        "name": "Ironwood Rod",
        "cost": 50,
        "catch_bonus": 2,
        "bite_time_reduction": 1,
        "reel_window": 14,
        "desc": "Dense hardwood. Gives you an edge in the fight.",
    },
    "whittled_willow": {
        "name": "Whittled Willow",
        "cost": 120,
        "catch_bonus": 5,
        "bite_time_reduction": 2,
        "reel_window": 16,
        "desc": "Flexible. Responsive. The fish hate how patient it makes you.",
    },
    "resonance_rod": {
        "name": "Resonance Rod",
        "cost": 400,
        "catch_bonus": 10,
        "bite_time_reduction": 3,
        "reel_window": 18,
        "desc": "Aeridorian material. Hums. Rare fish are drawn to the frequency.",
    },
    "aeridorian_spire": {
        "name": "Aeridorian Spire",
        "cost": 1500,
        "catch_bonus": 20,
        "bite_time_reduction": 4,
        "reel_window": 22,
        "desc": "Crystal-tipped, ancient, perfect. Legendary fish have been caught on this exact pole.",
    },
}

# ── Fish Registry ──────────────────────────────────────────────────────────────
# Fields:
#   name          display name
#   category      common / uncommon / rare / epic / legendary / mythic
#   weight_range  (min_lbs, max_lbs)
#   sell_value    base gil (before weight multiplier)
#   seasons       list of valid season strings
#   time_of_day   list of valid time strings
#   bait_pref     preferred bait keys (bonus chance when used)
#   desc          one-sentence flavor text
# ─────────────────────────────────────────────────────────────────────────────

FISH = {

    # ══════════════════════════════════════════════════════
    # COMMON  (100 fish)  — 2-8g · 0.1-5 lbs
    # ══════════════════════════════════════════════════════

    "trickle_gudgeon": {
        "name": "Tricklebrook Gudgeon",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "The first fish most adventurers ever catch. It seems resigned to this.",
    },
    "mud_minnow": {
        "name": "Mud Minnow",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Tiny. Technically a fish.",
    },
    "silver_carp": {
        "name": "Silver Carp",
        "category": "common", "weight_range": (0.5, 4.0), "sell_value": 5,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "Leaps when startled. You were startled first.",
    },
    "creek_perch": {
        "name": "Creek Perch",
        "category": "common", "weight_range": (0.2, 2.0), "sell_value": 4,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Spiny fins. Annoying to handle. Plentiful.",
    },
    "speckled_roach": {
        "name": "Speckled Roach",
        "category": "common", "weight_range": (0.1, 1.5), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Common as rain in the Tricklebrook. Tastes like creek.",
    },
    "brown_dace": {
        "name": "Brown Dace",
        "category": "common", "weight_range": (0.1, 0.9), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "A fast little thing that somehow got itself caught.",
    },
    "bleak": {
        "name": "Bleak",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Named for how it makes you feel catching one.",
    },
    "rudd": {
        "name": "Rudd",
        "category": "common", "weight_range": (0.2, 2.0), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Red-finned. More color than it deserves.",
    },
    "shallow_tench": {
        "name": "Shallow Tench",
        "category": "common", "weight_range": (0.5, 4.0), "sell_value": 5,
        "seasons": _SP_SU, "time_of_day": _NOTMID, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "Slimy. Hemlock says some people eat them on purpose.",
    },
    "bronze_bream": {
        "name": "Bronze Bream",
        "category": "common", "weight_range": (0.3, 3.5), "sell_value": 4,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Flat and wide. Looks like someone sat on a real fish.",
    },
    "fat_chub": {
        "name": "Fat Chub",
        "category": "common", "weight_range": (0.3, 2.5), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Larger than a minnow. Smaller than dignity.",
    },
    "creek_smelt": {
        "name": "Creek Smelt",
        "category": "common", "weight_range": (0.1, 0.6), "sell_value": 3,
        "seasons": _SP, "time_of_day": _DD, "bait_pref": ["earthworm"],
        "desc": "Smells exactly like its name suggests.",
    },
    "stone_goby": {
        "name": "Stone Goby",
        "category": "common", "weight_range": (0.1, 0.5), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Lives under rocks. Probably wishes it still did.",
    },
    "millers_thumb": {
        "name": "Miller's Thumb",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Squat and bottom-feeding. The bar has been set.",
    },
    "loach": {
        "name": "Loach",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _NOTMID, "bait_pref": ["earthworm"],
        "desc": "Wriggles. A lot. Don't put it down.",
    },
    "mudfish": {
        "name": "Mudfish",
        "category": "common", "weight_range": (0.2, 1.5), "sell_value": 2,
        "seasons": _AU_WI, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Its natural habitat is the worst part of the creek.",
    },
    "common_sculpin": {
        "name": "Common Sculpin",
        "category": "common", "weight_range": (0.1, 0.9), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Wide head, narrow prospects.",
    },
    "spotfin": {
        "name": "Spotfin",
        "category": "common", "weight_range": (0.1, 0.6), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Spotted fins. That's the whole story.",
    },
    "creek_darter": {
        "name": "Creek Darter",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Darts. In the creek. Accurate name.",
    },
    "fallfish": {
        "name": "Fallfish",
        "category": "common", "weight_range": (0.3, 2.5), "sell_value": 4,
        "seasons": _AU, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Large minnow. Autumn runs heavy.",
    },
    "stoneroller": {
        "name": "Stoneroller",
        "category": "common", "weight_range": (0.1, 0.7), "sell_value": 2,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Rolls stones. You've rolled worse.",
    },
    "longnose_dace": {
        "name": "Longnose Dace",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Distinguished by its nose. Otherwise, not distinguished.",
    },
    "blacknose_dace": {
        "name": "Blacknose Dace",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "The nose is the interesting part.",
    },
    "pearl_dace": {
        "name": "Pearl Dace",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DD, "bait_pref": ["earthworm"],
        "desc": "Pale silver. The kindest description it gets.",
    },
    "fathead": {
        "name": "Fathead Minnow",
        "category": "common", "weight_range": (0.05, 0.25), "sell_value": 2,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "The name is accurate and unkind.",
    },
    "bluntnose": {
        "name": "Bluntnose Minnow",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Stubby. Persists anyway.",
    },
    "creek_shiner": {
        "name": "Creek Shiner",
        "category": "common", "weight_range": (0.1, 0.5), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Catches the light. That's something.",
    },
    "sand_shiner": {
        "name": "Sand Shiner",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Found in sandy shallows. Exactly as boring as that sounds.",
    },
    "common_sucker": {
        "name": "Common Sucker",
        "category": "common", "weight_range": (0.5, 4.0), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _NOTMID, "bait_pref": ["earthworm"],
        "desc": "Vacuums the creek bottom for food. Effective, if undignified.",
    },
    "quillback": {
        "name": "Quillback",
        "category": "common", "weight_range": (0.3, 3.0), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Spiny back. Handle with care. Doesn't care.",
    },
    "white_sucker": {
        "name": "White Sucker",
        "category": "common", "weight_range": (0.5, 3.5), "sell_value": 3,
        "seasons": _AU_WI, "time_of_day": _NOTMID, "bait_pref": ["earthworm"],
        "desc": "Pale. Suctions. You take what you get.",
    },
    "hogsucker": {
        "name": "Hogsucker",
        "category": "common", "weight_range": (0.3, 2.0), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Named by someone who was having a bad day.",
    },
    "common_sunfish": {
        "name": "Common Sunfish",
        "category": "common", "weight_range": (0.2, 1.5), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Bright colors, small ambitions.",
    },
    "green_sunfish": {
        "name": "Green Sunfish",
        "category": "common", "weight_range": (0.2, 1.5), "sell_value": 4,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Aggressive for its size. Ineffectual.",
    },
    "pumpkinseed": {
        "name": "Pumpkinseed",
        "category": "common", "weight_range": (0.2, 1.2), "sell_value": 5,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Round, orange-spotted. Autumn catches particularly well.",
    },
    "warmouth": {
        "name": "Warmouth",
        "category": "common", "weight_range": (0.3, 2.0), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "The name suggests more fight than it delivers.",
    },
    "bantam_sunfish": {
        "name": "Bantam Sunfish",
        "category": "common", "weight_range": (0.1, 0.7), "sell_value": 3,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "The very smallest sunfish. Still considers itself a sunfish.",
    },
    "dollar_sunfish": {
        "name": "Dollar Sunfish",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 3,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Round as a coin. Worth less.",
    },
    "mud_perch": {
        "name": "Mud Perch",
        "category": "common", "weight_range": (0.2, 2.0), "sell_value": 3,
        "seasons": _AU_WI, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Perch that lives in mud. Prefers it.",
    },
    "yellow_perch": {
        "name": "Yellow Perch",
        "category": "common", "weight_range": (0.3, 2.5), "sell_value": 5,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Classic. Striped. Unambiguous.",
    },
    "brook_silverside": {
        "name": "Brook Silverside",
        "category": "common", "weight_range": (0.05, 0.25), "sell_value": 2,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Thin as paper. Transparent sides. Good light.",
    },
    "creek_chub": {
        "name": "Creek Chub",
        "category": "common", "weight_range": (0.2, 2.0), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Bottom of the barrel in the best way.",
    },
    "common_carp": {
        "name": "Common Carp",
        "category": "common", "weight_range": (1.0, 5.0), "sell_value": 6,
        "seasons": _SP_SU, "time_of_day": _DD, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "Old. Wary. Caught anyway.",
    },
    "grass_carp": {
        "name": "Grass Carp",
        "category": "common", "weight_range": (1.0, 5.0), "sell_value": 5,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Eats the vegetation. The vegetation objects.",
    },
    "crucian_carp": {
        "name": "Crucian Carp",
        "category": "common", "weight_range": (0.3, 3.0), "sell_value": 4,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Hardy survivor. Thrives where others don't.",
    },
    "pond_loach": {
        "name": "Pond Loach",
        "category": "common", "weight_range": (0.1, 0.7), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Breathes air when the pond goes low. Resourceful.",
    },
    "ruffe": {
        "name": "Ruffe",
        "category": "common", "weight_range": (0.1, 0.6), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Spiny perch-relative. Pokey.",
    },
    "dawn_minnow": {
        "name": "Dawn Minnow",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["earthworm"],
        "desc": "Only bites at sunrise. Gives off a faint glow when caught.",
    },
    "surface_sitter": {
        "name": "Surface Sitter",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 2,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Floats near the top all day doing nothing. Relatable.",
    },
    "bog_darter": {
        "name": "Bog Darter",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 3,
        "seasons": _SP_AU, "time_of_day": _DD, "bait_pref": ["earthworm"],
        "desc": "Darting around the muddy edges. Perpetually anxious.",
    },
    "trickle_tetra": {
        "name": "Tricklebrook Tetra",
        "category": "common", "weight_range": (0.02, 0.15), "sell_value": 2,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Schooling fish. You caught one of many. Many remain.",
    },
    "threadfin": {
        "name": "Threadfin",
        "category": "common", "weight_range": (0.1, 0.6), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Long trailing fin. More graceful than most.",
    },
    "emerald_dace": {
        "name": "Emerald Dace",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 4,
        "seasons": _SP, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Green-tinged. A small flash of color in dull water.",
    },
    "autumn_roach": {
        "name": "Autumn Roach",
        "category": "common", "weight_range": (0.2, 1.5), "sell_value": 4,
        "seasons": _AU, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Only abundant in autumn. Tastes of falling leaves. Not really.",
    },
    "ice_minnow": {
        "name": "Ice Minnow",
        "category": "common", "weight_range": (0.05, 0.25), "sell_value": 4,
        "seasons": _WI, "time_of_day": _DAWN, "bait_pref": ["earthworm"],
        "desc": "Winter only. Pale blue. Very cold to the touch.",
    },
    "snowmelt_dace": {
        "name": "Snowmelt Dace",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 3,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["earthworm"],
        "desc": "Appears with the thaw. Gone before spring settles.",
    },
    "summer_bleak": {
        "name": "Summer Bleak",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 3,
        "seasons": _SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Abundant in summer. Leaps at everything.",
    },
    "harvest_bream": {
        "name": "Harvest Bream",
        "category": "common", "weight_range": (0.5, 4.0), "sell_value": 6,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "Autumn fat. Best eating of the season.",
    },
    "mud_carp": {
        "name": "Mud Carp",
        "category": "common", "weight_range": (0.5, 3.0), "sell_value": 3,
        "seasons": _AU_WI, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Lives in the worst part of the pond. Smells like it.",
    },
    "river_sprat": {
        "name": "River Sprat",
        "category": "common", "weight_range": (0.05, 0.2), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Small, oily, forgotten immediately.",
    },
    "whisperwood_gudgeon": {
        "name": "Whisperwood Gudgeon",
        "category": "common", "weight_range": (0.1, 0.9), "sell_value": 5,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Caught where the forest meets the water. Its eyes are slightly wrong.",
    },
    "pond_smelt": {
        "name": "Pond Smelt",
        "category": "common", "weight_range": (0.1, 0.5), "sell_value": 3,
        "seasons": _AU_WI, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Smells like pond. Accurately named.",
    },
    "night_darter": {
        "name": "Night Darter",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 4,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Dawn and dusk only. Very fast. Rarely seen.",
    },
    "moon_minnow": {
        "name": "Moon Minnow",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 5,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Night only. Pale. Almost luminescent.",
    },
    "shadow_bleak": {
        "name": "Shadow Bleak",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Hugs the shaded banks at night. Darker than normal bleak.",
    },
    "midnight_loach": {
        "name": "Midnight Loach",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 4,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Bottom-feeding at night exclusively. Pale underside.",
    },
    "torch_perch": {
        "name": "Torch Perch",
        "category": "common", "weight_range": (0.2, 2.0), "sell_value": 4,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Caught under lamplight. Drawn to it.",
    },
    "dusk_chub": {
        "name": "Dusk Chub",
        "category": "common", "weight_range": (0.2, 2.5), "sell_value": 4,
        "seasons": _SU, "time_of_day": _DUSK, "bait_pref": ["earthworm"],
        "desc": "Evening peak activity. Lazy the rest of the day.",
    },
    "bog_minnow": {
        "name": "Bog Minnow",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _SP_AU, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "From the dark bog edges. Hardier than it looks.",
    },
    "silt_crawler": {
        "name": "Silt Crawler",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _AU_WI, "time_of_day": _NOTMID, "bait_pref": ["earthworm"],
        "desc": "Barely fish-shaped. Technically a fish.",
    },
    "reed_perch": {
        "name": "Reed Perch",
        "category": "common", "weight_range": (0.2, 1.8), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Hides in reeds. You found it.",
    },
    "bottom_feeder": {
        "name": "Common Bottom Feeder",
        "category": "common", "weight_range": (0.3, 2.5), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "It's right there in the name.",
    },
    "green_dace": {
        "name": "Green Dace",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 3,
        "seasons": _SP, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Faint green tinge. Algae-adjacent.",
    },
    "rusty_perch": {
        "name": "Rusty Perch",
        "category": "common", "weight_range": (0.2, 2.0), "sell_value": 3,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Orange-brown coloring. Looks older than it is.",
    },
    "pale_roach": {
        "name": "Pale Roach",
        "category": "common", "weight_range": (0.1, 1.5), "sell_value": 3,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Washed-out coloring. Winter river variant.",
    },
    "spotted_minnow": {
        "name": "Spotted Minnow",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Has spots. Minnow-sized.",
    },
    "weed_goby": {
        "name": "Weed Goby",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Lives in aquatic plants. Green-tinged.",
    },
    "stone_perch": {
        "name": "Stone Perch",
        "category": "common", "weight_range": (0.2, 1.5), "sell_value": 3,
        "seasons": _AU_WI, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Grey, rocklike. Almost blends in.",
    },
    "stubby_loach": {
        "name": "Stubby Loach",
        "category": "common", "weight_range": (0.05, 0.5), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "Shorter than usual. Stubborn.",
    },
    "common_bleak": {
        "name": "Common Bleak",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "The most common of all common fish.",
    },
    "pale_dace": {
        "name": "Pale Dace",
        "category": "common", "weight_range": (0.05, 0.3), "sell_value": 2,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Colorless. Translucent in good light.",
    },
    "creek_rudd": {
        "name": "Creek Rudd",
        "category": "common", "weight_range": (0.2, 1.8), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Creek variant. Red fins. Slightly more interesting than pond rudd.",
    },
    "small_tench": {
        "name": "Small Tench",
        "category": "common", "weight_range": (0.3, 2.5), "sell_value": 4,
        "seasons": _SP_SU, "time_of_day": _NOTMID, "bait_pref": ["earthworm"],
        "desc": "Young tench. Slimy like all tench. It's going to get bigger.",
    },
    "common_minnow": {
        "name": "Common Minnow",
        "category": "common", "weight_range": (0.02, 0.15), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _ALL_T, "bait_pref": ["earthworm"],
        "desc": "The benchmark. The floor. The first thing and the last thing.",
    },
    "river_bream": {
        "name": "River Bream",
        "category": "common", "weight_range": (0.4, 3.5), "sell_value": 5,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Slightly larger than pond bream. River life suits it.",
    },
    "bank_gudgeon": {
        "name": "Bank Gudgeon",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Under rocks near banks. Easy to find. Easy to catch.",
    },
    "small_catfish": {
        "name": "Small Catfish",
        "category": "common", "weight_range": (0.5, 4.0), "sell_value": 6,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "Whiskers. Bottom dwelling. A glimpse of what's below.",
    },
    "creek_eel_pup": {
        "name": "Creek Eel (Juvenile)",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 5,
        "seasons": _SP_SU, "time_of_day": _NIGHT, "bait_pref": ["earthworm"],
        "desc": "Young eel. Wriggly beyond all proportion to its size.",
    },
    "shore_sculpin": {
        "name": "Shore Sculpin",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Clings to the shallow bank. Territorial.",
    },
    "sprat_kin": {
        "name": "Spratkin",
        "category": "common", "weight_range": (0.05, 0.2), "sell_value": 2,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Closely related to the sprat. Claims not to be.",
    },
    "tarn_trout_pup": {
        "name": "Tarn Trout (Juvenile)",
        "category": "common", "weight_range": (0.1, 0.8), "sell_value": 5,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["earthworm"],
        "desc": "Young trout. Not a trout yet. Promising.",
    },
    "bankside_chub": {
        "name": "Bankside Chub",
        "category": "common", "weight_range": (0.2, 2.5), "sell_value": 3,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Always near the bank. Never far from easy.",
    },
    "zander_pup": {
        "name": "Zander (Juvenile)",
        "category": "common", "weight_range": (0.2, 1.5), "sell_value": 5,
        "seasons": _SP, "time_of_day": _DD, "bait_pref": ["earthworm"],
        "desc": "Juvenile zander. Not ready for anything yet. Alarming teeth though.",
    },
    "river_goby": {
        "name": "River Goby",
        "category": "common", "weight_range": (0.05, 0.4), "sell_value": 2,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["earthworm"],
        "desc": "Sucker-finned bottom dweller. Holds onto things.",
    },
    "spine_loach": {
        "name": "Spine Loach",
        "category": "common", "weight_range": (0.05, 0.5), "sell_value": 3,
        "seasons": _ALL_S, "time_of_day": _NOTMID, "bait_pref": ["earthworm"],
        "desc": "Has spines under its eyes. Handle carefully.",
    },

    # ══════════════════════════════════════════════════════
    # UNCOMMON  (60 fish)  — 10-30g · 0.5-15 lbs
    # ══════════════════════════════════════════════════════

    "trickle_trout": {
        "name": "Tricklebrook Trout",
        "category": "uncommon", "weight_range": (0.5, 8.0), "sell_value": 15,
        "seasons": _ALL_S, "time_of_day": _DD, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "The real catch. Actually fights back.",
    },
    "brown_trout": {
        "name": "Brown Trout",
        "category": "uncommon", "weight_range": (0.8, 10.0), "sell_value": 18,
        "seasons": _SP_AU, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Spotted, wary. Requires patience and a good morning.",
    },
    "rainbow_trout": {
        "name": "Rainbow Trout",
        "category": "uncommon", "weight_range": (1.0, 12.0), "sell_value": 22,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Colorful, leaping. Worth the effort.",
    },
    "brook_trout": {
        "name": "Brook Trout",
        "category": "uncommon", "weight_range": (0.5, 6.0), "sell_value": 16,
        "seasons": _AU, "time_of_day": _DD, "bait_pref": ["fat_grub"],
        "desc": "Cold water preference. Autumn peak. Beautiful markings.",
    },
    "arctic_char": {
        "name": "Arctic Char",
        "category": "uncommon", "weight_range": (1.0, 10.0), "sell_value": 20,
        "seasons": _WI, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Winter only. Cold-adapted, beautiful, hard to land.",
    },
    "grayling": {
        "name": "Grayling",
        "category": "uncommon", "weight_range": (0.5, 5.0), "sell_value": 17,
        "seasons": _AU_WI, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Dorsal sail fin. Caught in fast water. Smells of thyme.",
    },
    "river_pike": {
        "name": "River Pike",
        "category": "uncommon", "weight_range": (2.0, 15.0), "sell_value": 25,
        "seasons": _AU_WI, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Long, aggressive ambush predator. Gives real resistance.",
    },
    "striped_perch": {
        "name": "Striped Perch",
        "category": "uncommon", "weight_range": (0.5, 4.0), "sell_value": 12,
        "seasons": _ALL_S, "time_of_day": _DD, "bait_pref": ["fat_grub"],
        "desc": "Larger variant. More stripes than the common perch.",
    },
    "walleye": {
        "name": "Walleye",
        "category": "uncommon", "weight_range": (1.0, 10.0), "sell_value": 22,
        "seasons": _SP_AU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Glassy eyes. Excellent eating. Night bites hard.",
    },
    "zander": {
        "name": "Zander",
        "category": "uncommon", "weight_range": (1.5, 12.0), "sell_value": 24,
        "seasons": _SP_AU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Pike-perch. Sharp teeth. Very cautious. Worth the wait.",
    },
    "tench": {
        "name": "Tench",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 15,
        "seasons": _SP_SU, "time_of_day": _NOTMID, "bait_pref": ["fat_grub"],
        "desc": "Doctor fish. Slimy to handle, good to eat.",
    },
    "silver_bream": {
        "name": "Silver Bream",
        "category": "uncommon", "weight_range": (0.8, 5.0), "sell_value": 13,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Larger, brighter than the common bream. Better eating.",
    },
    "ide": {
        "name": "Ide",
        "category": "uncommon", "weight_range": (1.0, 7.0), "sell_value": 18,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Golden-orange variant. River fish. Spring spawning run.",
    },
    "asp": {
        "name": "Asp",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 20,
        "seasons": _SU, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Surface-hunting predator. Dramatic strikes.",
    },
    "burbot": {
        "name": "Burbot",
        "category": "uncommon", "weight_range": (1.5, 10.0), "sell_value": 22,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Freshwater cod. Underrated. Winter deep water.",
    },
    "common_eel": {
        "name": "Common Eel",
        "category": "uncommon", "weight_range": (0.5, 8.0), "sell_value": 18,
        "seasons": _SP_AU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Wriggles. A lot. A real fight to land.",
    },
    "whisperwood_bass": {
        "name": "Whisperwood Bass",
        "category": "uncommon", "weight_range": (0.8, 7.0), "sell_value": 20,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Bass from the forest-edge water. Unusual flavor. Don't ask.",
    },
    "stone_bass": {
        "name": "Stone Bass",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 18,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Lives under flat rocks. Territorial. Fights for the flat rock.",
    },
    "aeridor_carp": {
        "name": "Aeridor Carp",
        "category": "uncommon", "weight_range": (2.0, 12.0), "sell_value": 25,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Slightly iridescent. From resonance-touched water near the ruins.",
    },
    "grass_pike": {
        "name": "Grass Pike",
        "category": "uncommon", "weight_range": (1.5, 10.0), "sell_value": 20,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Hunts in the reeds. Patient. Fast when it moves.",
    },
    "chain_pickerel": {
        "name": "Chain Pickerel",
        "category": "uncommon", "weight_range": (0.8, 6.0), "sell_value": 15,
        "seasons": _AU_WI, "time_of_day": _DD, "bait_pref": ["fat_grub"],
        "desc": "Chain-patterned sides. Effective predator. Doesn't hesitate.",
    },
    "redfin_pickerel": {
        "name": "Redfin Pickerel",
        "category": "uncommon", "weight_range": (0.5, 4.0), "sell_value": 14,
        "seasons": _SP_AU, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Small pike family. Red fins. More aggressive than its size suggests.",
    },
    "whitefish": {
        "name": "Whitefish",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 16,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Clean flavor. Silvery. Winter lake-run variety.",
    },
    "cisco": {
        "name": "Cisco",
        "category": "uncommon", "weight_range": (0.5, 5.0), "sell_value": 14,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Deep water. Silver. Oily. Rarely seen in shallow ponds.",
    },
    "tiger_trout": {
        "name": "Tiger Trout",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 25,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Natural hybrid. Striking tiger-stripe pattern. Aggressive.",
    },
    "night_perch": {
        "name": "Night Perch",
        "category": "uncommon", "weight_range": (0.5, 4.5), "sell_value": 14,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Night only. Larger than day perch. Harder to land.",
    },
    "moon_trout": {
        "name": "Moon Trout",
        "category": "uncommon", "weight_range": (1.0, 9.0), "sell_value": 22,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Night variant of trout. Pale-spotted. Moves with the moonlight.",
    },
    "autumn_char": {
        "name": "Autumn Char",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 20,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Autumn spawning run. Orange-red coloring. Short window.",
    },
    "spring_smelt": {
        "name": "Spring Smelt Run",
        "category": "uncommon", "weight_range": (0.2, 1.5), "sell_value": 12,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["earthworm", "fat_grub"],
        "desc": "Spring only. Runs in enormous schools. Catch many or none.",
    },
    "oakhaven_eel": {
        "name": "Oakhaven Eel",
        "category": "uncommon", "weight_range": (0.5, 9.0), "sell_value": 20,
        "seasons": _SP_SU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Tricklebrook-specific variant. Long. Very long.",
    },
    "ironscale_carp": {
        "name": "Ironscale Carp",
        "category": "uncommon", "weight_range": (2.0, 12.0), "sell_value": 22,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Dark, heavy scales. Tough fight. Worth the trouble.",
    },
    "amber_perch": {
        "name": "Amber Perch",
        "category": "uncommon", "weight_range": (0.5, 4.0), "sell_value": 15,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Autumn coloring. Warm-toned. Hemlock buys them for the dye.",
    },
    "copper_bream": {
        "name": "Copper Bream",
        "category": "uncommon", "weight_range": (0.8, 6.0), "sell_value": 16,
        "seasons": _AU, "time_of_day": _DD, "bait_pref": ["fat_grub"],
        "desc": "Metallic copper sheen. Autumn only. Uncommon even then.",
    },
    "freckled_trout": {
        "name": "Freckled Trout",
        "category": "uncommon", "weight_range": (1.0, 9.0), "sell_value": 20,
        "seasons": _SP_AU, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Heavily spotted. Found in Whisperwood-edge water.",
    },
    "silvertail": {
        "name": "Silvertail",
        "category": "uncommon", "weight_range": (0.5, 5.0), "sell_value": 15,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Silver tail fin. Fast swimmer. Hard to bring in.",
    },
    "greenback_chub": {
        "name": "Greenback Chub",
        "category": "uncommon", "weight_range": (0.3, 3.0), "sell_value": 12,
        "seasons": _SP, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Green dorsal coloring. Spring only.",
    },
    "spotted_bass": {
        "name": "Spotted Bass",
        "category": "uncommon", "weight_range": (0.8, 7.0), "sell_value": 18,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Rocky substrate. Good fighter. Earns its name.",
    },
    "flint_pike": {
        "name": "Flint Pike",
        "category": "uncommon", "weight_range": (1.5, 10.0), "sell_value": 20,
        "seasons": _AU_WI, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Grey-brown. Blends with gravel. Strikes without warning.",
    },
    "velvet_catfish": {
        "name": "Velvet Catfish",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 18,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Smooth-skin variant. Night bites. Named for the texture.",
    },
    "bronze_catfish": {
        "name": "Bronze Catfish",
        "category": "uncommon", "weight_range": (1.5, 10.0), "sell_value": 20,
        "seasons": _SP_SU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Metallic coloring. River dwelling. Strong pull.",
    },
    "ghost_eel": {
        "name": "Ghost Eel",
        "category": "uncommon", "weight_range": (0.5, 6.0), "sell_value": 22,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Pale, almost translucent. Night only. Eerie to hold.",
    },
    "river_lamprey": {
        "name": "River Lamprey",
        "category": "uncommon", "weight_range": (0.3, 2.5), "sell_value": 14,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Ancient jawless fish. Unchanged for eons. Unnerving.",
    },
    "shadow_carp": {
        "name": "Shadow Carp",
        "category": "uncommon", "weight_range": (1.5, 10.0), "sell_value": 18,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Dark coloring. Near the Whisperwood water at night.",
    },
    "large_ruffe": {
        "name": "River Ruffe",
        "category": "uncommon", "weight_range": (0.3, 2.5), "sell_value": 10,
        "seasons": _ALL_S, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Larger ruffe. More spines. More problematic.",
    },
    "eclipse_bass": {
        "name": "Eclipse Bass",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 25,
        "seasons": _SP_AU, "time_of_day": _DD, "bait_pref": ["glowfly"],
        "desc": "Only during the twilight transitions. The window is brief.",
    },
    "blue_zander": {
        "name": "Blue Zander",
        "category": "uncommon", "weight_range": (1.5, 11.0), "sell_value": 28,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Bluish variant. Rare in any season. Beautiful.",
    },
    "opalescent_roach": {
        "name": "Opalescent Roach",
        "category": "uncommon", "weight_range": (0.3, 2.5), "sell_value": 20,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["fat_grub"],
        "desc": "Iridescent scales. Only in spring dawn water.",
    },
    "amber_catfish": {
        "name": "Amber Catfish",
        "category": "uncommon", "weight_range": (1.5, 12.0), "sell_value": 25,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Orange-amber coloring. Autumn night bites hard.",
    },
    "mire_eel": {
        "name": "Mire Eel",
        "category": "uncommon", "weight_range": (0.8, 7.0), "sell_value": 20,
        "seasons": _SP_AU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "From the bog edges. Slimy. Strange. Smells of the mire.",
    },
    "rune_bream": {
        "name": "Rune Bream",
        "category": "uncommon", "weight_range": (0.8, 6.0), "sell_value": 22,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Marked with natural rune patterns. Aeridor water influence.",
    },
    "pale_chub": {
        "name": "Pale Chub",
        "category": "uncommon", "weight_range": (0.3, 3.0), "sell_value": 12,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Uncommon chub variant. Clear cold water. Pale as snow.",
    },
    "winter_cod": {
        "name": "Winter Cod",
        "category": "uncommon", "weight_range": (1.5, 12.0), "sell_value": 25,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Cold season only. Deep feeding. Excellent eating.",
    },
    "summer_bass": {
        "name": "Summer Bass",
        "category": "uncommon", "weight_range": (1.0, 9.0), "sell_value": 20,
        "seasons": _SU, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Peak summer. Energetic fight. Hard to keep on the line.",
    },
    "elder_roach": {
        "name": "Elder Roach",
        "category": "uncommon", "weight_range": (0.5, 4.0), "sell_value": 15,
        "seasons": _AU_WI, "time_of_day": _NOTMID, "bait_pref": ["fat_grub"],
        "desc": "Old roach. Larger, wiser. Harder to fool.",
    },
    "deep_perch": {
        "name": "Deepwater Perch",
        "category": "uncommon", "weight_range": (0.5, 5.0), "sell_value": 18,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Dwells in the cold deep. Rarely comes up for bait.",
    },
    "thornback": {
        "name": "Thornback",
        "category": "uncommon", "weight_range": (0.5, 5.0), "sell_value": 16,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Unusual spiky back. Autumn only. Handle with gloves.",
    },
    "shallowdweller": {
        "name": "Shallowdweller Pike",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 18,
        "seasons": _SP_SU, "time_of_day": _DAY, "bait_pref": ["fat_grub"],
        "desc": "Hunts in the very shallows. Visible before you catch it.",
    },
    "spectral_dace": {
        "name": "Spectral Dace",
        "category": "uncommon", "weight_range": (0.1, 0.8), "sell_value": 20,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Nearly transparent. Almost invisible in the water at night.",
    },
    "copper_eel": {
        "name": "Copper Eel",
        "category": "uncommon", "weight_range": (0.5, 7.0), "sell_value": 22,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Reddish-copper coloring. Summer night. Unusually beautiful for an eel.",
    },
    "granite_catfish": {
        "name": "Granite Catfish",
        "category": "uncommon", "weight_range": (2.0, 13.0), "sell_value": 26,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["fat_grub"],
        "desc": "Grey-mottled. Blends with rocky bottom. Very heavy.",
    },
    "moonfish": {
        "name": "Moonfish",
        "category": "uncommon", "weight_range": (1.0, 8.0), "sell_value": 24,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Round, silver-white, flat. Active only on clear nights.",
    },

    # ══════════════════════════════════════════════════════
    # RARE  (40 fish)  — 35-100g · 1-40 lbs
    # ══════════════════════════════════════════════════════

    "golden_trout": {
        "name": "Golden Trout",
        "category": "rare", "weight_range": (2.0, 20.0), "sell_value": 60,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["glowfly", "aeridor_lure"],
        "desc": "Brilliant yellow-gold. A rare spring catch that fishers brag about for years.",
    },
    "crystal_perch": {
        "name": "Crystal Perch",
        "category": "rare", "weight_range": (1.0, 10.0), "sell_value": 55,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Almost transparent. Aeridorian water influence. Rings like glass.",
    },
    "resonance_carp": {
        "name": "Resonance Carp",
        "category": "rare", "weight_range": (5.0, 30.0), "sell_value": 80,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Faint hum when held. Heavy. Scales catch light strangely.",
    },
    "whisper_eel": {
        "name": "Whisper Eel",
        "category": "rare", "weight_range": (2.0, 20.0), "sell_value": 70,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Dark blue-black. Deep under Whisperwood shadow. Cold to touch.",
    },
    "oakhaven_pike": {
        "name": "Oakhaven Pike",
        "category": "rare", "weight_range": (8.0, 40.0), "sell_value": 90,
        "seasons": _AU_WI, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "The monster pike of the Tricklebrook. Old. Covered in lure-scars.",
    },
    "moonsong_trout": {
        "name": "Moonsong Trout",
        "category": "rare", "weight_range": (3.0, 22.0), "sell_value": 75,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Night only. Soft luminescence. The water around it glows faintly.",
    },
    "deep_char": {
        "name": "Deepwater Char",
        "category": "rare", "weight_range": (3.0, 25.0), "sell_value": 70,
        "seasons": _WI, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "From the very bottom. Cold season. Almost never surfaces.",
    },
    "aeridor_eel": {
        "name": "Aeridorian Eel",
        "category": "rare", "weight_range": (2.0, 18.0), "sell_value": 80,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Slightly crystalline scales. Resonance-touched. Hums softly.",
    },
    "shadow_pike": {
        "name": "Shadow Pike",
        "category": "rare", "weight_range": (5.0, 30.0), "sell_value": 75,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly", "aeridor_lure"],
        "desc": "Near-black coloring. Whisperwood edge only. Never in daylight.",
    },
    "void_carp": {
        "name": "Void Carp",
        "category": "rare", "weight_range": (4.0, 25.0), "sell_value": 85,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Very dark. Found only at night near the ruins. No eyes.",
    },
    "gilded_perch": {
        "name": "Gilded Perch",
        "category": "rare", "weight_range": (2.0, 12.0), "sell_value": 65,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["glowfly"],
        "desc": "Bright gold variant. Lucky catch. Elara won't say what it means.",
    },
    "runic_trout": {
        "name": "Runic Trout",
        "category": "rare", "weight_range": (3.0, 20.0), "sell_value": 72,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Faint rune-like markings on its sides. Aeridor water. Rare even there.",
    },
    "trickle_ghost": {
        "name": "Tricklebrook Ghost",
        "category": "rare", "weight_range": (2.0, 15.0), "sell_value": 78,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Pale, semi-translucent. Night only. Seems to absorb light.",
    },
    "blood_tench": {
        "name": "Blood Tench",
        "category": "rare", "weight_range": (2.0, 15.0), "sell_value": 68,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Dark red variant. Autumn spawning. Deeper than the regular tench.",
    },
    "winter_ghost": {
        "name": "Winter Ghost Fish",
        "category": "rare", "weight_range": (1.0, 10.0), "sell_value": 65,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "White. Winter only. Very cold to the touch. Eyes like chips of ice.",
    },
    "spring_herald": {
        "name": "Spring Herald",
        "category": "rare", "weight_range": (2.0, 14.0), "sell_value": 62,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["fat_grub", "glowfly"],
        "desc": "Appears with the snowmelt. Bright green. First rare catch of spring.",
    },
    "midsummer_bass": {
        "name": "Midsummer Bass",
        "category": "rare", "weight_range": (3.0, 20.0), "sell_value": 70,
        "seasons": _SU, "time_of_day": _DAWN, "bait_pref": ["glowfly"],
        "desc": "Peak of summer only. Only during the solstice week.",
    },
    "crystal_goby": {
        "name": "Crystal Goby",
        "category": "rare", "weight_range": (0.5, 4.0), "sell_value": 55,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Near-transparent. Aeridorian influence. Rare even near the ruins.",
    },
    "war_pike": {
        "name": "War Pike",
        "category": "rare", "weight_range": (8.0, 38.0), "sell_value": 95,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Old pike. Covered in lure scars from decades of escapes. Very angry.",
    },
    "fossil_carp": {
        "name": "Fossil Carp",
        "category": "rare", "weight_range": (5.0, 30.0), "sell_value": 85,
        "seasons": _WI, "time_of_day": _DAY, "bait_pref": ["aeridor_lure"],
        "desc": "Ancient variant. Unchanged for centuries. Recognizes nothing.",
    },
    "elder_trout": {
        "name": "Elder Trout",
        "category": "rare", "weight_range": (5.0, 35.0), "sell_value": 90,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Very old, very wary. Has escaped many lines before yours.",
    },
    "temple_eel": {
        "name": "Temple Eel",
        "category": "rare", "weight_range": (2.0, 18.0), "sell_value": 80,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Found near the shrine pond overflow. Sacred? Sister Maren says yes.",
    },
    "sentinel_pike": {
        "name": "Sentinel Pike",
        "category": "rare", "weight_range": (8.0, 40.0), "sell_value": 95,
        "seasons": _ALL_S, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Always alone. Always watching. Old. Has seen things.",
    },
    "bog_lurker": {
        "name": "Bog Lurker",
        "category": "rare", "weight_range": (3.0, 20.0), "sell_value": 72,
        "seasons": _SP_AU, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Not quite a fish. Mostly is. From the bog edges.",
    },
    "ironclad_catfish": {
        "name": "Ironclad Catfish",
        "category": "rare", "weight_range": (5.0, 35.0), "sell_value": 88,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Heavy armored plates. Very tough to bring in. Heavy.",
    },
    "ghost_trout": {
        "name": "Ghost Trout",
        "category": "rare", "weight_range": (2.0, 18.0), "sell_value": 78,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Pale, almost white. Winter deep water. Looks like a haunting.",
    },
    "stonecold_char": {
        "name": "Stonecold Char",
        "category": "rare", "weight_range": (3.0, 22.0), "sell_value": 75,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Winter deep water. Almost frozen. Burns to touch.",
    },
    "emerald_pike": {
        "name": "Emerald Pike",
        "category": "rare", "weight_range": (4.0, 25.0), "sell_value": 80,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["glowfly", "aeridor_lure"],
        "desc": "Green iridescent. Spring only. Brief window after the thaw.",
    },
    "twilight_perch": {
        "name": "Twilight Perch",
        "category": "rare", "weight_range": (1.5, 12.0), "sell_value": 65,
        "seasons": _SP_AU, "time_of_day": _DD, "bait_pref": ["glowfly"],
        "desc": "Dawn or dusk only. Brief windows. Very specific.",
    },
    "resonance_eel": {
        "name": "Resonance Eel",
        "category": "rare", "weight_range": (3.0, 22.0), "sell_value": 85,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Hums. Faint electric feel when touched. Don't ask why.",
    },
    "harvest_pike": {
        "name": "Harvest Pike",
        "category": "rare", "weight_range": (6.0, 35.0), "sell_value": 88,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Autumn only. Fattened for winter. The seasonal prize.",
    },
    "winter_king_trout": {
        "name": "Winter King Trout",
        "category": "rare", "weight_range": (5.0, 35.0), "sell_value": 92,
        "seasons": _WI, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "The premier winter catch. Cold-adapted, beautiful, rare.",
    },
    "blue_eel": {
        "name": "Blue Eel",
        "category": "rare", "weight_range": (2.0, 18.0), "sell_value": 75,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["glowfly"],
        "desc": "Vivid blue coloring. Winter deep water. Eerie to hold.",
    },
    "amber_titan_perch": {
        "name": "Amber Titan Perch",
        "category": "rare", "weight_range": (3.0, 22.0), "sell_value": 80,
        "seasons": _AU, "time_of_day": _DAY, "bait_pref": ["aeridor_lure"],
        "desc": "Golden-orange giant perch. Autumn only. Impressive.",
    },
    "dawn_bream": {
        "name": "Dawn Bream",
        "category": "rare", "weight_range": (2.0, 15.0), "sell_value": 65,
        "seasons": _SP_SU, "time_of_day": _DAWN, "bait_pref": ["glowfly"],
        "desc": "Only in the first hour of light. Gone by sunrise.",
    },
    "obsidian_carp": {
        "name": "Obsidian Carp",
        "category": "rare", "weight_range": (5.0, 30.0), "sell_value": 88,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Black as volcanic glass. Winter night. Cold weight in the hand.",
    },
    "sunken_carp": {
        "name": "Sunken Carp",
        "category": "rare", "weight_range": (4.0, 28.0), "sell_value": 82,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Bottom-dweller. Very old. Barely moves until it does.",
    },
    "autumn_sovereign": {
        "name": "Autumn Sovereign",
        "category": "rare", "weight_range": (4.0, 28.0), "sell_value": 95,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "The grand autumn catch. Peak October. Fishers compete for it.",
    },
    "deep_ruler_catfish": {
        "name": "Deep Ruler Catfish",
        "category": "rare", "weight_range": (8.0, 40.0), "sell_value": 100,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Apex of the deep water. Winter night. The heaviest common type.",
    },

    # ══════════════════════════════════════════════════════
    # EPIC  (30 fish)  — 120-400g · 5-100 lbs
    # ══════════════════════════════════════════════════════

    "old_bones": {
        "name": "Old Bones",
        "category": "epic", "weight_range": (15.0, 60.0), "sell_value": 180,
        "seasons": _AU_WI, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "An ancient pike, scarred from a hundred battles. Older than Oakhaven.",
    },
    "moonfire_carp": {
        "name": "Moonfire Carp",
        "category": "epic", "weight_range": (10.0, 55.0), "sell_value": 200,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Glows faintly at night. Scales flash like moonlight on still water.",
    },
    "aeridorian_trout": {
        "name": "Aeridorian Trout",
        "category": "epic", "weight_range": (8.0, 45.0), "sell_value": 250,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Crystalline spots. Resonance-infused. Rings like a chime when caught.",
    },
    "whisperpike": {
        "name": "Whisperpike",
        "category": "epic", "weight_range": (20.0, 80.0), "sell_value": 320,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "The Whisperwood's apex freshwater predator. Near-black.",
    },
    "deep_titan_catfish": {
        "name": "Deep Titan Catfish",
        "category": "epic", "weight_range": (25.0, 100.0), "sell_value": 350,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "The largest catfish in the Tricklebrook system. Barely fits the bank.",
    },
    "ghost_king_eel": {
        "name": "Ghost King Eel",
        "category": "epic", "weight_range": (10.0, 60.0), "sell_value": 300,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Enormous. Pale. Seen only in deep night water. Silently vast.",
    },
    "void_serpent_eel": {
        "name": "Void Serpent Eel",
        "category": "epic", "weight_range": (8.0, 50.0), "sell_value": 380,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Near the ruins at midnight. Not entirely natural.",
    },
    "trickle_giant_carp": {
        "name": "Tricklebrook Giant Carp",
        "category": "epic", "weight_range": (20.0, 90.0), "sell_value": 300,
        "seasons": _SP_SU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "The legendary overgrown carp of the deep pool. Stories predate Oakhaven.",
    },
    "crimson_bass": {
        "name": "Crimson Bass",
        "category": "epic", "weight_range": (8.0, 50.0), "sell_value": 250,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Deep red variant. Autumn spawn. A season-specific trophy.",
    },
    "star_trout": {
        "name": "Starfall Trout",
        "category": "epic", "weight_range": (8.0, 50.0), "sell_value": 280,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Silver-white. Night only. Very rare. Scales like stars.",
    },
    "iron_pike": {
        "name": "Iron Pike",
        "category": "epic", "weight_range": (15.0, 65.0), "sell_value": 320,
        "seasons": _AU_WI, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Scales feel metallic. Grey-blue. Enormous. Devastating pull.",
    },
    "rune_pike": {
        "name": "Rune Pike",
        "category": "epic", "weight_range": (12.0, 60.0), "sell_value": 350,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Covered in natural rune markings. Aeridor-influenced. Hums.",
    },
    "echo_carp": {
        "name": "Echo Carp",
        "category": "epic", "weight_range": (10.0, 55.0), "sell_value": 280,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Makes a faint resonance hum when out of water. Gets louder.",
    },
    "elder_pike": {
        "name": "Elder Pike",
        "category": "epic", "weight_range": (18.0, 75.0), "sell_value": 360,
        "seasons": _WI, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "The oldest pike. It remembers things you don't want things to remember.",
    },
    "shadow_titan": {
        "name": "Shadow Titan",
        "category": "epic", "weight_range": (20.0, 80.0), "sell_value": 340,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Massive dark catfish. Night deep water. Almost invisible.",
    },
    "resonance_giant_carp": {
        "name": "Resonance Giant Carp",
        "category": "epic", "weight_range": (15.0, 70.0), "sell_value": 320,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Heavy with resonance. Hums loudly. Water vibrates near it.",
    },
    "opalescent_trout": {
        "name": "Opalescent Trout",
        "category": "epic", "weight_range": (8.0, 45.0), "sell_value": 270,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Shifts color. Dawn only. Gone before the sun is fully up.",
    },
    "crystal_titan_perch": {
        "name": "Crystal Titan Perch",
        "category": "epic", "weight_range": (12.0, 55.0), "sell_value": 300,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Almost entirely transparent. Very heavy. Cold as ice.",
    },
    "void_pike": {
        "name": "Void Pike",
        "category": "epic", "weight_range": (15.0, 65.0), "sell_value": 380,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Near the ruins at night. Unnatural darkness follows it.",
    },
    "midnight_titan_bass": {
        "name": "Midnight Titan Bass",
        "category": "epic", "weight_range": (12.0, 60.0), "sell_value": 290,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure"],
        "desc": "Night deep water. Massive. Surface-breaches before dawn.",
    },
    "spring_king_salmon": {
        "name": "Spring King Salmon",
        "category": "epic", "weight_range": (15.0, 70.0), "sell_value": 350,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Rare spring run. Magnificent. The finest spring catch.",
    },
    "winter_leviathan": {
        "name": "Winter Leviathan",
        "category": "epic", "weight_range": (20.0, 90.0), "sell_value": 380,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Deep winter water. Huge. Cold. Old. Patient.",
    },
    "summer_crown_bass": {
        "name": "Summer Crown Bass",
        "category": "epic", "weight_range": (8.0, 50.0), "sell_value": 260,
        "seasons": _SU, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Peak midsummer. Energetic. The summer trophy.",
    },
    "blood_moon_bass": {
        "name": "Blood Moon Bass",
        "category": "epic", "weight_range": (10.0, 55.0), "sell_value": 400,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Only during the blood moon weather event. Crimson. Violent pull.",
    },
    "frozen_king_char": {
        "name": "Frozen King Char",
        "category": "epic", "weight_range": (12.0, 58.0), "sell_value": 340,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["aeridor_lure", "crystal_bait"],
        "desc": "Winter deep. Cold burns to touch. Beautiful ice-blue coloring.",
    },
    "dawn_serpent": {
        "name": "Dawn Serpent Eel",
        "category": "epic", "weight_range": (8.0, 50.0), "sell_value": 320,
        "seasons": _SP_AU, "time_of_day": _DAWN, "bait_pref": ["aeridor_lure"],
        "desc": "Appears only at first light. Once per season window.",
    },
    "whisper_leviathan": {
        "name": "Whisper Leviathan",
        "category": "epic", "weight_range": (15.0, 75.0), "sell_value": 400,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "The Whisperwood's own fish. Not entirely from water.",
    },
    "night_sovereign": {
        "name": "Night Sovereign",
        "category": "epic", "weight_range": (12.0, 60.0), "sell_value": 350,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Claims the deep water after midnight. Other fish avoid it.",
    },
    "trickle_behemoth": {
        "name": "Tricklebrook Behemoth",
        "category": "epic", "weight_range": (25.0, 100.0), "sell_value": 400,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "The largest non-legendary thing in the pond. Still enormous.",
    },
    "ancient_carp_lord": {
        "name": "Ancient Carp Lord",
        "category": "epic", "weight_range": (20.0, 90.0), "sell_value": 380,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Old enough to have earned the title. Takes an hour to land.",
    },

    # ══════════════════════════════════════════════════════
    # LEGENDARY  (15 fish)  — 500-2000g · 20-300 lbs
    # ══════════════════════════════════════════════════════

    "the_pale_king": {
        "name": "The Pale King",
        "category": "legendary", "weight_range": (40.0, 85.0), "sell_value": 800,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "An albino pike the length of a man. Seen twice in living memory. Once was enough.",
    },
    "old_aeridor": {
        "name": "Old Aeridor",
        "category": "legendary", "weight_range": (50.0, 95.0), "sell_value": 1200,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "A carp that predates the ruins. The resonance has done things to it.",
    },
    "tricklemother": {
        "name": "The Tricklemother",
        "category": "legendary", "weight_range": (35.0, 75.0), "sell_value": 1000,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "The eel that made the Tricklebrook. Or so Elara says. She won't clarify.",
    },
    "moonwarden": {
        "name": "Moonwarden",
        "category": "legendary", "weight_range": (45.0, 90.0), "sell_value": 1400,
        "seasons": _SU, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Full moon nights only. Ancient, scarred, glowing. Has a name older than the town.",
    },
    "thorn_serpent": {
        "name": "Thorn Serpent",
        "category": "legendary", "weight_range": (25.0, 65.0), "sell_value": 900,
        "seasons": _SP_AU, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Not a serpent. Not comfortable to catch. Definitely alive.",
    },
    "iron_father": {
        "name": "Iron Father",
        "category": "legendary", "weight_range": (50.0, 95.0), "sell_value": 1500,
        "seasons": _AU_WI, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "The patriarch of all pike. Grey as iron. Ancient. Fights like a rock.",
    },
    "deepest_one": {
        "name": "The Deepest One",
        "category": "legendary", "weight_range": (40.0, 80.0), "sell_value": 1200,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "From a depth the Tricklebrook shouldn't have. Cold beyond reason.",
    },
    "ancient_leviathan": {
        "name": "Ancient Leviathan",
        "category": "legendary", "weight_range": (60.0, 110.0), "sell_value": 1800,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Whatever this is, it remembers Aeridor. It has seen the civilization rise and fall.",
    },
    "gilded_ghost": {
        "name": "The Gilded Ghost",
        "category": "legendary", "weight_range": (30.0, 70.0), "sell_value": 1600,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Gold and translucent. The bait vanished. The fish appeared. No explanation offered.",
    },
    "sentinel_of_the_deep": {
        "name": "Sentinel of the Deep",
        "category": "legendary", "weight_range": (45.0, 85.0), "sell_value": 1300,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Watches from below. Was caught once. Released. Still watching.",
    },
    "crown_of_the_brook": {
        "name": "Crown of the Brook",
        "category": "legendary", "weight_range": (55.0, 95.0), "sell_value": 2000,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "The Tricklebrook's apex. Old enough to have a name older than Oakhaven.",
    },
    "elara_secret_fish": {
        "name": "Elara's Secret",
        "category": "legendary", "weight_range": (25.0, 150.0), "sell_value": 1100,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "A fish Elara denies exists. She gets very quiet when you show her one.",
    },
    "the_silent_catch": {
        "name": "The Silent Catch",
        "category": "legendary", "weight_range": (35.0, 190.0), "sell_value": 1700,
        "seasons": _AU, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "Described in the Silent Ones' oldest texts. It still exists. That's interesting.",
    },
    "shadow_sovereign": {
        "name": "Shadow Sovereign",
        "category": "legendary", "weight_range": (30.0, 160.0), "sell_value": 1400,
        "seasons": _AU_WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "The final, oldest shadow that the Whisperwood threw into the water.",
    },
    "gregor_nemesis": {
        "name": "Gregor's Nemesis",
        "category": "legendary", "weight_range": (50.0, 300.0), "sell_value": 2000,
        "seasons": _ALL_S, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "The fish Old Gregor has been trying to catch for thirty years. Don't let him see it.",
    },

    # ══════════════════════════════════════════════════════
    # MYTHIC  (5 fish)  — Effectively impossible · Enormous
    # ══════════════════════════════════════════════════════

    "the_world_carp": {
        "name": "The World Carp",
        "category": "mythic", "weight_range": (80.0, 140.0), "sell_value": 15000,
        "seasons": _ALL_S, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "It is said the Tricklebrook flows around it, not through it. Older than the stream.",
    },
    "gods_hook": {
        "name": "What Hangs on the Gods' Hook",
        "category": "mythic", "weight_range": (60.0, 130.0), "sell_value": 25000,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "You aren't sure what you caught. Neither is it. It looks as surprised as you.",
    },
    "silent_one_fish": {
        "name": "The Silent One's Fish",
        "category": "mythic", "weight_range": (50.0, 110.0), "sell_value": 20000,
        "seasons": _SP, "time_of_day": _DAWN, "bait_pref": ["crystal_bait"],
        "desc": "The offering bowl at the shrine has always had a fish shape carved in it. Now you know why.",
    },
    "aeridor_heart": {
        "name": "Heart of Aeridor",
        "category": "mythic", "weight_range": (70.0, 150.0), "sell_value": 50000,
        "seasons": _AU, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "The resonance crystallized. The crystal learned to swim. It hums at a frequency that makes thought difficult.",
    },
    "trickle_end": {
        "name": "End of the Trickle",
        "category": "mythic", "weight_range": (75.0, 160.0), "sell_value": 30000,
        "seasons": _WI, "time_of_day": _NIGHT, "bait_pref": ["crystal_bait"],
        "desc": "Whatever made the Tricklebrook stop flowing for one day, long ago. You caught it. You're not sure what happens now.",
    },
}

# ── Sell value scaling by category ───────────────────────────────────────────
CATEGORY_WEIGHT_BONUS = {
    # Additional gil multiplier based on (actual_weight / max_weight)
    # Final value = base_sell * (1 + WEIGHT_BONUS * weight_pct)
    "common":    0.30,
    "uncommon":  0.40,
    "rare":      0.50,
    "epic":      0.60,
    "legendary": 0.75,
    "mythic":    1.00,
}

CATEGORY_RARITY_WEIGHT = {
    "common":    55,
    "uncommon":  28,
    "rare":      12,
    "epic":       4,
    "legendary":  0.8,
    "mythic":     0.2,
}

# Rarity ceiling by bait (max category roll when using this bait)
BAIT_RARITY_CEILING = {
    "earthworm":   ["common", "uncommon", "rare"],
    "fat_grub":    ["common", "uncommon", "rare", "epic"],
    "glowfly":     ["common", "uncommon", "rare", "epic"],
    "aeridor_lure":["common", "uncommon", "rare", "epic", "legendary"],
    "crystal_bait":["common", "uncommon", "rare", "epic", "legendary", "mythic"],
}

# ── Catch table lookup helpers ────────────────────────────────────────────────

def get_fish_by_category(category: str) -> list[tuple[str, dict]]:
    return [(k, v) for k, v in FISH.items() if v["category"] == category]


def get_available_fish(season: str, time_of_day: str, bait_key: str) -> dict[str, list[tuple[str, dict]]]:
    """
    Return dict of category → list of (key, fish) tuples eligible for this
    season / time-of-day / bait combination.
    """
    ceiling = BAIT_RARITY_CEILING.get(bait_key, list(CATEGORY_RARITY_WEIGHT.keys()))
    bait_preferred = BAIT.get(bait_key, {}).get("preferred_cats", [])

    result: dict[str, list] = {c: [] for c in ceiling}
    for key, fish in FISH.items():
        if fish["category"] not in ceiling:
            continue
        if season not in fish["seasons"]:
            continue
        if time_of_day not in fish["time_of_day"]:
            continue
        result[fish["category"]].append((key, fish))

    # Fallback: if a category is empty, pull all fish of that category (season/time ignored)
    for cat in ceiling:
        if not result[cat]:
            result[cat] = [(k, v) for k, v in FISH.items() if v["category"] == cat]

    return result


def get_time_of_day(hour: int) -> str:
    """Convert 24h hour to time_of_day string."""
    if 5 <= hour < 9:
        return "dawn"
    elif 9 <= hour < 12:
        return "morning"
    elif 12 <= hour < 15:
        return "midday"
    elif 15 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 21:
        return "evening"
    else:
        return "night"
