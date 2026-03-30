"""
Farming System — Aethelgard
Seeds purchased from Sister Maren. Crops grown in housing plots.
Harvest yields alchemy ingredients.
"""

from datetime import date

CROPS = {
    "blood_thistle_seed": {
        "name": "Blood Thistle Seed",
        "seed_cost": 15,              # Gil cost at Maren's
        "seller": "maren",
        "growth_days": 2,             # Days from planting to harvest
        "yield_item": "blood_thistle",
        "yield_amount": (2, 4),       # Random range
        "desc": "A prickly red seed. Grows fast in poor soil.",
        "emoji": "🌱",
        "season_bonus": "spring",     # +1 yield in this season
    },
    "honey_sap_seed": {
        "name": "Honey Sap Cutting",
        "seed_cost": 12,
        "seller": "maren",
        "growth_days": 3,
        "yield_item": "honey_sap",
        "yield_amount": (2, 3),
        "desc": "A sticky cutting from a sap-heavy tree. Needs watering every day.",
        "emoji": "🌿",
        "season_bonus": "summer",
    },
    "silver_moss_spore": {
        "name": "Silvermoss Spore",
        "seed_cost": 20,
        "seller": "maren",
        "growth_days": 3,
        "yield_item": "silver_moss",
        "yield_amount": (2, 4),
        "desc": "Glows faintly at night. Grows best near water.",
        "emoji": "✨",
        "season_bonus": "autumn",
    },
    "dire_root_bulb": {
        "name": "Dire Root Bulb",
        "seed_cost": 25,
        "seller": "maren",
        "growth_days": 4,
        "yield_item": "dire_root",
        "yield_amount": (1, 3),
        "desc": "Slow-growing and stubborn. Yields the best in winter.",
        "emoji": "🌾",
        "season_bonus": "winter",
    },
    "gilded_mushroom_spore": {
        "name": "Gilded Spore",
        "seed_cost": 60,
        "seller": "maren",
        "growth_days": 5,
        "yield_item": "gilded_mushroom",
        "yield_amount": (1, 2),
        "desc": "Rare. Grows in darkness. Don't water it — it drowns.",
        "emoji": "🍄",
        "season_bonus": None,
        "no_water": True,             # Special: watering kills it
    },
}

CROP_STAGES = ["🌱 Seedling", "🌿 Growing", "🌾 Almost Ready", "✅ Ready to Harvest"]

def get_crop_stage(crop: dict) -> str:
    planted = date.fromisoformat(crop["planted_date"])
    days_grown = (date.today() - planted).days
    watered_days = crop.get("watered_count", 0)
    growth_days = CROPS[crop["crop_key"]]["growth_days"]

    # Unwatered crops (except gilded mushroom) don't progress
    crop_data = CROPS[crop["crop_key"]]
    if not crop_data.get("no_water") and not crop.get("watered_today") and days_grown > 0:
        if watered_days < days_grown:
            return "🥀 Wilting — needs water"

    pct = min(days_grown / growth_days, 1.0)
    idx = min(int(pct * (len(CROP_STAGES) - 1)), len(CROP_STAGES) - 1)
    return CROP_STAGES[idx]

def is_harvestable(crop: dict) -> bool:
    planted = date.fromisoformat(crop["planted_date"])
    days_grown = (date.today() - planted).days
    crop_data = CROPS[crop["crop_key"]]
    growth_days = crop_data["growth_days"]
    
    if days_grown < growth_days:
        return False
    
    # Watered check (not for no_water crops)
    if not crop_data.get("no_water"):
        if crop.get("watered_count", 0) < growth_days - 1:
            return False
    
    return True

def harvest_crop(crop: dict, season: str) -> tuple[str, int]:
    """Returns (item_key, quantity)."""
    import secrets
    crop_data = CROPS[crop["crop_key"]]
    min_yield, max_yield = crop_data["yield_amount"]
    qty = secrets.randbelow(max_yield - min_yield + 1) + min_yield
    
    # Season bonus
    if crop_data.get("season_bonus") == season:
        qty += 1
    
    return crop_data["yield_item"], qty

def reset_daily_farm(housing: dict) -> dict:
    """Call on daily reset — clear watered_today flags."""
    today = date.today().isoformat()
    for plot in housing.get("farming", {}).get("plots", []):
        plot["watered_today"] = False
    housing["last_farm_reset"] = today
    return housing
