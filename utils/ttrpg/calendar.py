"""
calendar.py — Aethelgard World Calendar
========================================

The Aethelgard calendar maps to real-world dates.
No separate game clock. The world advances with actual time.

  Spring  → March, April, May
  Summer  → June, July, August
  Autumn  → September, October, November
  Winter  → December, January, February

Season day (1-~91) is derived from position within the 3-month block.
Special days are fixed dates in the real calendar.
"""

from datetime import date
from typing import Optional


SEASONS = {
    "spring": (3, 4, 5),
    "summer": (6, 7, 8),
    "autumn": (9, 10, 11),
    "winter": (12, 1, 2),
}

SEASON_NAMES = {
    "spring": "Spring",
    "summer": "Summer",
    "autumn": "Autumn",
    "winter": "Winter",
}

SEASON_FLAVOR = {
    "spring": "The Whisperwood is waking up. Mud clings to everything. The birds are too loud.",
    "summer": "The air is heavy and green. Oakhaven smells of sawdust and warm stone.",
    "autumn": "The canopy is turning. Mornings carry frost. The forest feels like it's preparing for something.",
    "winter": "The Trade Road is ice. The Whisperwood is silent in a way that feels deliberate.",
}

SEASON_EMOJI = {
    "spring": "🌱",
    "summer": "☀️",
    "autumn": "🍂",
    "winter": "❄️",
}


def get_season(today: Optional[date] = None) -> str:
    """Return current season key based on real-world month."""
    if today is None:
        today = date.today()
    m = today.month
    for season, months in SEASONS.items():
        if m in months:
            return season
    return "spring"


def get_season_day(today: Optional[date] = None) -> int:
    """Return approximate day within the current season (1-91).
    Handles year-wrap for winter (Dec, Jan, Feb)."""
    if today is None:
        today = date.today()
    season = get_season(today)
    months = SEASONS[season]
    import calendar as cal
    day = 0
    for m in months:
        # Determine the actual year for this month in the season
        if season == "winter" and m == 12:
            year = today.year - 1 if today.month <= 2 else today.year
        else:
            year = today.year
        # Build a date for the first of this month in the correct year
        m_year = year
        if m == today.month and m_year == today.year:
            # We've reached the current month — add partial days and stop
            break
        day += cal.monthrange(m_year, m)[1]
    day += today.day
    return day


def get_special_day(today: Optional[date] = None) -> Optional[dict]:
    """
    Return special day data if today is a holiday or notable date.
    Returns None on ordinary days.
    """
    if today is None:
        today = date.today()
    m, d = today.month, today.day
    return SPECIAL_DAYS.get((m, d))


# ══════════════════════════════════════════════════════════
# SPECIAL DAYS — fixed real-world dates
# Format: (month, day): {name, description, buff, buff_value, type}
# ══════════════════════════════════════════════════════════

SPECIAL_DAYS = {

    # ── SPRING FESTIVALS ────────────────────────────────────
    (3, 20): {
        "name": "First Day of Spring",
        "desc": "The Whisperwood stirs. Something that was dormant is not anymore.",
        "type": "seasonal_transition",
        "buff": "spring_awakening",
        "buff_desc": "+1 to all stat checks today",
        "buff_value": 1,
        "announcement": "🌱 *Spring has come to Aethelgard. The roads thaw. The forest remembers.*",
    },
    (4, 1): {
        "name": "Festival of Fools",
        "desc": "An old Aeridorian tradition. The Shrine of the Silent Ones is draped in ribbons. Nobody remembers why.",
        "type": "festival",
        "buff": "fools_luck",
        "buff_desc": "Gamble at the Stone Hearth today for 2x Gil on wins. Losses are also doubled.",
        "buff_value": 2,
        "shop_special": {"item": "lucky_charm", "price": 15, "desc": "A small carved token. +1 to next roll."},
        "announcement": "🎭 *The Festival of Fools. Mira hung something ridiculous over the bar. Hemlock refuses to acknowledge it.*",
    },
    (5, 1): {
        "name": "Beltane — The Long Fire",
        "desc": "A bonfire is lit in Oakhaven Town Square at dusk. People bring offerings. Elder Elara says words nobody quite hears.",
        "type": "festival",
        "buff": "long_fire",
        "buff_desc": "+3 HP restored after every successful hunt today",
        "buff_value": 3,
        "announcement": "🔥 *The Long Fire is lit in Oakhaven. The smoke carries west. Whatever it's calling, it's listening.*",
    },

    # ── SUMMER FESTIVALS ─────────────────────────────────────
    (6, 21): {
        "name": "Solstice of the Silent Ones",
        "desc": "The longest day. The Shrine is said to be active tonight. Offerings left here have... effects.",
        "type": "holy_day",
        "buff": "solstice_blessing",
        "buff_desc": "!rpg offer grants 3 XP per Gil today (instead of 1), cap raised to 60 XP",
        "buff_value": 3,
        "announcement": "☀️ *The Solstice. The Shrine of the Silent Ones is lit from within by something that isn't fire. Elara locked her door this morning.*",
    },
    (7, 15): {
        "name": "Grimstone Trade Fair",
        "desc": "Merchants from Grimstone arrive in Oakhaven for three days. Hemlock expands his stock temporarily.",
        "type": "merchant_event",
        "buff": None,
        "shop_special": {
            "extra_stock": ["longsword", "half_plate", "steel_blade"],
            "desc": "Grimstone traders have brought high-tier gear to Hemlock's for today only."
        },
        "announcement": "🛒 *Grimstone traders arrived before dawn. Hemlock's cramped. The prices are not lower just because there's more of it.*",
    },
    (8, 7): {
        "name": "The Amber Night",
        "desc": "A summer phenomenon — the sky over the Whisperwood turns amber at dusk. Creatures are restless.",
        "type": "world_event",
        "encounter_mod": {"tier_shift": 1, "desc": "All encounters today are one tier higher than normal"},
        "buff": "amber_sight",
        "buff_desc": "+2 to all attack rolls — the amber light sharpens something in the eye",
        "buff_value": 2,
        "announcement": "🌅 *The sky is amber over the Whisperwood tonight. Something in there is moving differently. The guards at the Watchtower tripled the watch.*",
    },

    # ── AUTUMN FESTIVALS ────────────────────────────────────
    (9, 22): {
        "name": "First Day of Autumn",
        "desc": "The canopy shifts overnight. Oakhaven wakes to orange and red.",
        "type": "seasonal_transition",
        "buff": "harvest_strength",
        "buff_desc": "+1 Gil from all monster kills today",
        "buff_value": 1,
        "announcement": "🍂 *Autumn has come to Aethelgard. The Whisperwood changed color overnight. Nobody saw it happen.*",
    },
    (10, 31): {
        "name": "Morvenna's Eve",
        "desc": "The night dedicated to Morvenna, goddess of death. The veil between living and returned is thin. Undead are more active. The Shrine is the safest place in Oakhaven tonight.",
        "type": "holy_day",
        "encounter_mod": {"undead_bonus": True, "desc": "Undead monsters appear in all locations today, including Oakhaven edge"},
        "buff": "morvennas_ward",
        "buff_desc": "Praying at the Shrine grants +5 HP (in addition to Blessed) on Morvenna's Eve",
        "buff_value": 5,
        "announcement": "💀 *Morvenna's Eve. Leave an offering at the Shrine. Don't go into the Whisperwood tonight. This is not a suggestion.*",
    },
    (11, 11): {
        "name": "The Remembrance",
        "desc": "A day of quiet. The Ironclad Guild rings a bell in Grimstone. Oakhaven leaves small stones at the Shrine. For who, exactly, nobody can say anymore.",
        "type": "solemn_day",
        "buff": "remembrance",
        "buff_desc": "All XP gains +50% today",
        "buff_value": 1.5,
        "announcement": "🕯️ *The Remembrance. Someone left stones at the Shrine before dawn. Mira opened the Stone Hearth early and isn't charging for the first ale.*",
    },

    # ── WINTER FESTIVALS ────────────────────────────────────
    (12, 1): {
        "name": "First Day of Winter",
        "desc": "The Trade Road freezes. The Whisperwood goes quiet. A different kind of quiet.",
        "type": "seasonal_transition",
        "buff": "winter_resolve",
        "buff_desc": "Max HP +5 today — the cold makes you careful",
        "buff_value": 5,
        "announcement": "❄️ *Winter has come to Aethelgard. The Trade Road is ice. The Whisperwood is silent in a way that feels deliberate.*",
    },
    (12, 21): {
        "name": "The Long Night — Winter Solstice",
        "desc": "The shortest day. The longest dark. The Hooded Figure is not in his corner at the Stone Hearth tonight.",
        "type": "holy_day",
        "buff": "long_night_vigil",
        "buff_desc": "+1 hunt today (6 total) — the long dark is long",
        "buff_value": 1,
        "announcement": "🌑 *The Long Night. The Hooded Figure's chair is empty. The fire at the Stone Hearth is burning blue tonight. Mira won't say why.*",
    },
    (12, 25): {
        "name": "Feast of the Silent Ones",
        "desc": "The one day no one hunts. Food is left at the Shrine threshold. By morning it is always gone.",
        "type": "festival",
        "buff": "silent_gift",
        "buff_desc": "The Silent Ones leave a gift. Visit the Shrine for a mystery item.",
        "buff_value": 0,
        "shrine_gift": True,
        "announcement": "🎁 *The Feast of the Silent Ones. By custom, the Whisperwood is left alone today. Something is always found at the Shrine threshold by dawn. Nobody saw it placed there.*",
    },
    (1, 1): {
        "name": "New Year — The Turning",
        "desc": "Oakhaven fires arrows into the sky at midnight. Nobody remembers starting this tradition. Nobody wants to stop.",
        "type": "festival",
        "buff": "new_year_resolve",
        "buff_desc": "Full HP restore at midnight. Start fresh.",
        "buff_value": 999,
        "announcement": "🎆 *The Turning. A new year in Aethelgard. The arrows went up at midnight. The Whisperwood lit up briefly when they did. Elara is choosing not to comment.*",
    },
    (2, 14): {
        "name": "Hearthday",
        "desc": "A Stone Hearth tradition. Mira makes something special. The regulars are insufferably cheerful.",
        "type": "social_day",
        "buff": "hearthday_warmth",
        "buff_desc": "Rest at the Stone Hearth is free today (Mira's treat)",
        "buff_value": 0,
        "announcement": "🍺 *Hearthday. Mira posted a sign: 'Rest is free today. Don't make it weird.' The Stone Hearth smells different. Better.*",
    },
}


# ══════════════════════════════════════════════════════════
# SEASONAL MONSTERS — additional spawns per season
# These are added to encounter tables during their season
# ══════════════════════════════════════════════════════════

SEASONAL_MONSTERS = {
    "spring": {
        "whisperwood_edge": [
            ("moldwynd", 15),     # spore creatures more active
            ("grat",     12),     # carnivorous plants bloom
        ],
        "whisperwood_deep": [
            ("ochu", 10),         # ochu blooms in spring
        ],
    },
    "summer": {
        "whisperwood_edge": [
            ("killer_bee", 20),   # summer swarms
            ("harpy",      8),    # harpy breeding season
        ],
        "trade_road": [
            ("bandit", 10),       # road travel peaks in summer
        ],
    },
    "autumn": {
        "whisperwood_edge": [
            ("ghost",      12),   # spirits more active as nights lengthen
            ("shadow_hound", 8),
        ],
        "whisperwood_deep": [
            ("werewolf",   10),   # full moons longer in autumn
            ("nachtmahr",  6),
        ],
    },
    "winter": {
        "whisperwood_edge": [
            ("snow_bunny",   20),  # NEW winter-only creature
            ("ice_wisp",     12),  # NEW winter-only creature
            ("steel_bat",    8),   # bats driven out of deep caves
        ],
        "whisperwood_deep": [
            ("frost_wolf",   15),  # NEW winter variant
            ("skeleton",     12),  # undead more active in cold
        ],
        "trade_road": [
            ("snow_bandit",  15),  # desperate in winter
        ],
    },
}

SEASONAL_FARM_BONUSES = {
    "spring": {"blood_thistle_seed": 1, "honey_sap_seed": 0},
    "summer": {"honey_sap_seed": 1, "gilded_mushroom_spore": 0},
    "autumn": {"silver_moss_spore": 1, "dire_root_bulb": 0},
    "winter": {"dire_root_bulb": 1},
}


# ══════════════════════════════════════════════════════════
# SEASONAL SHOP STOCK — Hemlock's inventory changes per season
# Keys are added to HEMLOCK_STOCK_* for the season duration
# ══════════════════════════════════════════════════════════

SEASONAL_SHOP = {
    "spring": {
        "consumables": ["antidote"],           # poison more common, Hemlock stocks cures
    },
    "summer": {
        "consumables": ["tonic", "elixir"],    # travelers stocking up, supply is higher
    },
    "autumn": {
        "consumables": ["elixir"],
        "weapons": ["hand_axe"],               # harvest surplus weapons traded
    },
    "winter": {
        "consumables": ["bandage", "tonic"],   # cold makes wounds worse
        "armor": ["fur_cloak"],                # NEW winter-only armor
    },
}


# ══════════════════════════════════════════════════════════
# SEASONAL MONSTER STATS — REMOVED
# ══════════════════════════════════════════════════════════
# These stat blocks have been consolidated into monster_registry.py
# to prevent desync. Seasonal monsters are referenced by key only
# in SEASONAL_MONSTERS above; their stats live in MONSTERS dict.


# SEASONAL_ITEMS — REMOVED
# These items are defined in equipment_registry.py.
# Seasonal availability is handled by SEASONAL_SHOP above.


import hashlib


# ══════════════════════════════════════════════════════════
# WEATHER SYSTEM
# Deterministic per day — seeded from date ordinal.
# All players see the same weather. No persistence needed.
# ══════════════════════════════════════════════════════════

WEATHER_TABLES = {
    "spring": [
        # (weight, key, name, desc, emoji, effect)
        (30, "overcast",     "Overcast",       "Low cloud sits on the Whisperwood. The treeline is grey.",              "☁️",  None),
        (25, "rain",         "Raining",        "Steady rain. The Tricklebrook is swollen. The mud is worse.",           "🌧️",  {"type": "encounter_mod", "desc": "+10% chance of forest events (creatures seek shelter, paths change)", "value": 10}),
        (20, "clear",        "Clear",          "Bright spring morning. The forest smells like wet earth and new growth.","🌤️",  None),
        (15, "fog",          "Foggy",          "Thick fog off the Whisperwood. The Watchtower can see nothing.",        "🌫️",  {"type": "scout_blocked", "desc": "!rpg scout unavailable — fog obscures the canopy", "value": 0}),
        (10, "storm",        "Storming",       "Thunder from the Spine of the World. The Trade Road is dangerous.",     "⛈️",  {"type": "encounter_mod", "desc": "Trade Road encounters +1 tier today", "value": 1}),
    ],
    "summer": [
        (35, "clear",        "Clear",          "Bright and dry. The Whisperwood hums. Good day for a hunt.",           "☀️",  None),
        (25, "hot",          "Sweltering",     "Heavy heat. Moving in plate armor today would be a mistake.",          "🌡️",  {"type": "armor_penalty", "desc": "Heavy armor (chainmail+) reduces max HP by 2 today", "value": -2}),
        (20, "overcast",     "Overcast",       "High cloud, no shade. Warm and grey.",                                "⛅",  None),
        (15, "rain",         "Rain",           "Brief summer rain. The dust settles. Paths are muddier.",              "🌦️",  None),
        (5,  "drought_wind", "Dry Wind",       "Hot wind from the west. The Whisperwood is restless. Fire risk.",      "💨",  {"type": "encounter_mod", "desc": "Fire-adjacent monsters more aggressive — +2 ATK for Salamanders and similar", "value": 2}),
    ],
    "autumn": [
        (30, "overcast",     "Overcast",       "Heavy cloud. The light is flat. The forest looks older.",              "☁️",  None),
        (25, "fog",          "Foggy",          "Morning fog that doesn't lift. The Shrine is invisible from the square.","🌫️", {"type": "scout_blocked", "desc": "!rpg scout unavailable — fog obscures the canopy", "value": 0}),
        (20, "clear",        "Clear",          "Crisp autumn day. Good visibility. The canopy is red and gold.",        "🍂",  {"type": "xp_bonus", "desc": "+5 XP per monster kill — clear sight, clean work", "value": 5}),
        (15, "rain",         "Rain",           "Cold autumn rain. The Trade Road is treacherous. Hemlock lit a fire.",  "🌧️",  None),
        (10, "wind",         "High Wind",      "Wind off the Spine. The Watchtower crew came down. Smart.",            "🌬️",  {"type": "scout_blocked", "desc": "!rpg scout unavailable — tower is unsafe", "value": 0}),
    ],
    "winter": [
        (30, "snow",         "Snowing",        "Fresh snow on Oakhaven. The Trade Road is passable but slow.",         "❄️",  {"type": "encounter_mod", "desc": "+15% chance of winter seasonal creatures", "value": 15}),
        (25, "blizzard",     "Blizzard",       "White-out conditions. The Whisperwood is impassable above level 4.",   "🌨️",  {"type": "level_gate", "desc": "Whisperwood Deep requires level 6 today — the storm turns back weaker hunters", "value": 6, "locations": ["whisperwood_deep"]}),
        (20, "clear",        "Clear",          "Cold and bright. The snow reflects everything. Quiet.",                "🌨️✨", None),
        (15, "overcast",     "Overcast",       "Flat winter light. Grey sky, grey town. Hemlock's fire is welcome.",   "☁️",  None),
        (10, "frost",        "Hard Frost",     "Everything is ice. The Tricklebrook is frozen solid.",                 "🧊",  {"type": "gil_bonus", "desc": "+3 Gil per monster kill — pelts are worth more in hard frost", "value": 3}),
    ],
}


def get_weather(today=None) -> dict:
    """
    Return today's weather deterministically.
    Seeded from date ordinal — same result for every player all day.
    """
    if today is None:
        today = date.today()

    season = get_season(today)
    table = WEATHER_TABLES[season]

    # Deterministic seed from date
    seed = int(hashlib.md5(str(today.toordinal()).encode()).hexdigest(), 16) % 10000
    total = sum(w for w, *_ in table)
    r = seed % total
    cumulative = 0
    for weight, key, name, desc, emoji, effect in table:
        cumulative += weight
        if r < cumulative:
            return {
                "key": key,
                "name": name,
                "desc": desc,
                "emoji": emoji,
                "effect": effect,
                "season": season,
            }
    # Fallback
    weight, key, name, desc, emoji, effect = table[0]
    return {"key": key, "name": name, "desc": desc,
            "emoji": emoji, "effect": effect, "season": season}


def get_seasonal_encounter_table(location: str, base_table: list) -> list:
    """
    Merge seasonal monsters into the base encounter table for a location.
    Called from encounter_tables.random_encounter().
    """
    season = get_season()
    seasonal = SEASONAL_MONSTERS.get(season, {}).get(location, [])
    if not seasonal:
        return base_table
    return base_table + seasonal


def get_today_summary() -> dict:
    """
    Return a full summary of today's calendar state.
    Used by !rpg calendar and the dawn task.
    """
    today = date.today()
    season = get_season(today)
    special = get_special_day(today)

    return {
        "date": today.strftime("%B %d"),
        "season": season,
        "season_name": SEASON_NAMES[season],
        "season_emoji": SEASON_EMOJI[season],
        "season_flavor": SEASON_FLAVOR[season],
        "season_day": get_season_day(today),
        "special_day": special,
    }