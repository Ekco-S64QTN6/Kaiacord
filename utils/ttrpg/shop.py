from utils.ttrpg.equipment_registry import (
    WEAPONS, ARMOR, CONSUMABLES, HEADGEAR, BOOTS, ACCESSORIES,
    HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR,
    HEMLOCK_STOCK_HEADGEAR, HEMLOCK_STOCK_BOOTS, HEMLOCK_STOCK_ACCESSORIES,
)

def get_shop_inventory(location: str = "hemlocks_store") -> tuple[dict, dict, dict, dict, dict, dict]:
    """Returns available weapons, armor, headgear, boots, accessories, and consumables for a location."""
    from utils.ttrpg.calendar import get_season, SEASONAL_SHOP
    from utils.ttrpg.equipment_registry import (
        HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR,
        HEMLOCK_STOCK_HEADGEAR, HEMLOCK_STOCK_BOOTS, HEMLOCK_STOCK_ACCESSORIES,
        HEMLOCK_STOCK_CONSUMABLES, get_caravan_stock
    )

    if location == "caravan":
        gear_keys, consumable_keys = get_caravan_stock()
        weapons     = {k: WEAPONS[k]     for k in gear_keys if k in WEAPONS}
        armor       = {k: ARMOR[k]       for k in gear_keys if k in ARMOR}
        headgear    = {k: HEADGEAR[k]    for k in gear_keys if k in HEADGEAR}
        boots       = {k: BOOTS[k]       for k in gear_keys if k in BOOTS}
        accessories = {k: ACCESSORIES[k] for k in gear_keys if k in ACCESSORIES}
        consumables = {k: CONSUMABLES[k] for k in consumable_keys if k in CONSUMABLES}
        return weapons, armor, headgear, boots, accessories, consumables

    # Default: Hemlock's Store
    season = get_season()
    seasonal = SEASONAL_SHOP.get(season, {})

    weapons_keys     = HEMLOCK_STOCK_WEAPONS.copy()
    armor_keys       = HEMLOCK_STOCK_ARMOR.copy()
    headgear_keys    = HEMLOCK_STOCK_HEADGEAR.copy()
    boots_keys       = HEMLOCK_STOCK_BOOTS.copy()
    accessory_keys   = HEMLOCK_STOCK_ACCESSORIES.copy()
    consumables_keys = HEMLOCK_STOCK_CONSUMABLES.copy()

    weapons_keys.extend(seasonal.get("weapons", []))
    armor_keys.extend(seasonal.get("armor", []))
    headgear_keys.extend(seasonal.get("headgear", []))
    boots_keys.extend(seasonal.get("boots", []))
    accessory_keys.extend(seasonal.get("accessories", []))
    consumables_keys.extend(seasonal.get("consumables", []))

    weapons     = {k: WEAPONS[k]     for k in weapons_keys     if k in WEAPONS}
    armor       = {k: ARMOR[k]       for k in armor_keys       if k in ARMOR}
    headgear    = {k: HEADGEAR[k]    for k in headgear_keys    if k in HEADGEAR}
    boots       = {k: BOOTS[k]       for k in boots_keys       if k in BOOTS}
    accessories = {k: ACCESSORIES[k] for k in accessory_keys   if k in ACCESSORIES}
    consumables = {k: CONSUMABLES[k] for k in consumables_keys if k in CONSUMABLES}

    return weapons, armor, headgear, boots, accessories, consumables

def find_item(item_key: str) -> dict | None:
    """Finds an item across all registries. Supports underscored keys,
    space-separated names, and ALIASES."""
    from utils.ttrpg.equipment_registry import ALIASES

    item_key = item_key.strip().lower()
    # Normalize: "rusty dagger" → "rusty_dagger"
    normalized = item_key.replace(" ", "_")
    item_key = ALIASES.get(item_key, ALIASES.get(normalized, normalized))

    ALL = [
        ("weapon",    WEAPONS),
        ("armor",     ARMOR),
        ("head",      HEADGEAR),
        ("boots",     BOOTS),
        ("accessory", ACCESSORIES),
        ("consumable", CONSUMABLES),
    ]

    # Direct key match
    for cat, reg in ALL:
        if item_key in reg:
            return {"category": cat, "key": item_key, **reg[item_key]}

    # Fallback: match by item name (e.g. "Rusty Dagger")
    for cat, reg in ALL:
        for k, v in reg.items():
            if v.get("name", "").lower() == item_key.replace("_", " "):
                return {"category": cat, "key": k, **v}

    return None

def process_purchase(sheet: dict, item_key: str, quantity: int = 1, reputation: int = 0, cha_mod: int = 0) -> tuple[bool, str, dict]:
    """Processes a purchase. Returns (Success, Message, Updated Sheet)"""
    loc = sheet.get("location", "hemlocks_store")
    
    if loc == "hemlocks_store" and reputation < -50:
        return False, "Hemlock glares at you. 'I don't trade with outlaws. Get out.'", sheet
    
    item = find_item(item_key)
    if not item:
        return False, f"Item `{item_key}` not found.", sheet

    # Caravan specific logic: 1 gear item limit
    if loc == "caravan":
        if item["category"] in ("weapon", "armor", "head", "boots", "accessory"):
            if sheet.get("flags", {}).get("caravan_gear_bought"):
                return False, "*The merchant shakes his head.*\n\n\"One piece of gear, friend. I need stock for the next town.\"", sheet
            sheet.setdefault("flags", {})["caravan_gear_bought"] = True
    
    real_key = item["key"]
    
    # Reputation modifier
    price_mult = 1.0
    if reputation >= 100: price_mult = 0.8  # 20% discount
    elif reputation >= 50:  price_mult = 0.9  # 10% discount
    elif reputation < -20:  price_mult = 1.1  # 10% markup
    # CHA discount: each +1 CHA mod = 2% discount (max 10%)
    cha_discount = min(0.10, max(0.0, cha_mod * 0.02))
    price_mult -= cha_discount
    
    val = int(item["value"] * quantity * price_mult)
    gil = sheet.get("gil", 0)
    
    if gil < val:
        return False, f"Not enough gil. {quantity}x {item['name']} costs {val}g. You have {gil}g.", sheet
        
    sheet["gil"] -= val
    
    if "inventory" not in sheet:
        sheet["inventory"] = []
        
    sheet["inventory"].extend([real_key] * quantity)
    
    if quantity == 1:
        msg = f"Purchased **{item['name']}** for {val}g. Remaining gil: {sheet['gil']}g."
    else:
        msg = f"Purchased **{quantity}x {item['name']}** for {val}g. Remaining gil: {sheet['gil']}g."
        
    return True, msg, sheet

def process_sell(sheet: dict, item_key: str, reputation: int = 0, cha_mod: int = 0) -> tuple[bool, str, dict]:
    """Processes a sale. Sells at 50% base value + reputation bonus + CHA bonus."""
    loc = sheet.get("location", "hemlocks_store")
    if reputation < -50:
        merchant_name = "The merchant" if loc == "caravan" else "Hemlock"
        refusal_msg = "spits on the floor. 'I'm not buying your stolen goods.'" if loc != "caravan" else "shakes his head. 'I don't deal with your kind.'"
        return False, f"{merchant_name} {refusal_msg}", sheet
    
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = item_key.strip().lower().replace(" ", "_")
    item_key = ALIASES.get(item_key, item_key)
    
    if "inventory" not in sheet or item_key not in sheet["inventory"]:
        return False, f"You don't have `{item_key}` in your inventory.", sheet
        
    item = find_item(item_key)
    if not item:
        return False, f"Unknown item `{item_key}`.", sheet
        
    # Reputation modifier
    sell_mult = 0.5
    if reputation >= 100: sell_mult = 0.7  # 50% base + 20% bonus
    elif reputation >= 50:  sell_mult = 0.6  # 50% base + 10% bonus
    elif reputation < -20:  sell_mult = 0.4  # 10% penalty
    # CHA sell bonus: each +1 CHA mod = 2% better sell price (max 10%)
    cha_bonus = min(0.10, max(0.0, cha_mod * 0.02))
    sell_mult += cha_bonus
    
    val = max(1, int(item["value"] * sell_mult))
    sheet["inventory"].remove(item_key)
    sheet["gil"] = sheet.get("gil", 0) + val
    
    return True, f"Sold **{item['name']}** for {val}g. Total gil: {sheet['gil']}g.", sheet
