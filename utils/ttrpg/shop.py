from utils.ttrpg.equipment_registry import WEAPONS, ARMOR, CONSUMABLES, HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR

def get_shop_inventory() -> tuple[dict, dict, dict]:
    """Returns available weapons, armor, and consumables for Hemlock."""
    from utils.ttrpg.calendar import get_season, SEASONAL_SHOP
    from utils.ttrpg.equipment_registry import HEMLOCK_STOCK_CONSUMABLES
    
    season = get_season()
    seasonal = SEASONAL_SHOP.get(season, {})
    
    # Base stock
    weapons_keys = HEMLOCK_STOCK_WEAPONS.copy()
    armor_keys = HEMLOCK_STOCK_ARMOR.copy()
    consumables_keys = HEMLOCK_STOCK_CONSUMABLES.copy()
    
    # Add seasonal additions
    weapons_keys.extend(seasonal.get("weapons", []))
    armor_keys.extend(seasonal.get("armor", []))
    consumables_keys.extend(seasonal.get("consumables", []))
    
    weapons = {k: WEAPONS[k] for k in weapons_keys if k in WEAPONS}
    armor = {k: ARMOR[k] for k in armor_keys if k in ARMOR}
    consumables = {k: CONSUMABLES[k] for k in consumables_keys if k in CONSUMABLES}
    
    return weapons, armor, consumables

def find_item(item_key: str) -> dict | None:
    """Finds an item across all registries."""
    from utils.ttrpg.equipment_registry import ALIASES
    
    item_key = ALIASES.get(item_key, item_key)
    
    if item_key in WEAPONS:
        return {"category": "weapon", "key": item_key, **WEAPONS[item_key]}
    if item_key in ARMOR:
        return {"category": "armor", "key": item_key, **ARMOR[item_key]}
    if item_key in CONSUMABLES:
        return {"category": "consumable", "key": item_key, **CONSUMABLES[item_key]}
    return None

def process_purchase(sheet: dict, item_key: str, quantity: int = 1, reputation: int = 0) -> tuple[bool, str, dict]:
    """Processes a purchase. Returns (Success, Message, Updated Sheet)"""
    if reputation < -50:
        return False, "Hemlock glares at you. 'I don't trade with outlaws. Get out.'", sheet
    
    item = find_item(item_key)
    if not item:
        return False, f"Item `{item_key}` not found.", sheet
    
    real_key = item["key"]
    
    # Reputation modifier
    price_mult = 1.0
    if reputation >= 100: price_mult = 0.8  # 20% discount
    elif reputation >= 50:  price_mult = 0.9  # 10% discount
    elif reputation < -20:  price_mult = 1.1  # 10% markup
    
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

def process_sell(sheet: dict, item_key: str, reputation: int = 0) -> tuple[bool, str, dict]:
    """Processes a sale. Sells at 50% base value + reputation bonus."""
    if reputation < -50:
        return False, "Hemlock spits on the floor. 'I'm not buying your stolen goods.'", sheet
    
    from utils.ttrpg.equipment_registry import ALIASES
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
    
    val = max(1, int(item["value"] * sell_mult))
    sheet["inventory"].remove(item_key)
    sheet["gil"] = sheet.get("gil", 0) + val
    
    return True, f"Sold **{item['name']}** for {val}g. Total gil: {sheet['gil']}g.", sheet
