from utils.ttrpg.equipment_registry import WEAPONS, ARMOR, CONSUMABLES, HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR

def get_shop_inventory() -> tuple[dict, dict, dict]:
    """Returns available weapons, armor, and consumables for Hemlock."""
    weapons = {k: WEAPONS[k] for k in HEMLOCK_STOCK_WEAPONS if k in WEAPONS}
    armor = {k: ARMOR[k] for k in HEMLOCK_STOCK_ARMOR if k in ARMOR}
    return weapons, armor, CONSUMABLES

def find_item(item_key: str) -> dict | None:
    """Finds an item across all registries."""
    if item_key in WEAPONS:
        return {"category": "weapon", "key": item_key, **WEAPONS[item_key]}
    if item_key in ARMOR:
        return {"category": "armor", "key": item_key, **ARMOR[item_key]}
    if item_key in CONSUMABLES:
        return {"category": "consumable", "key": item_key, **CONSUMABLES[item_key]}
    return None

def process_purchase(sheet: dict, item_key: str) -> tuple[bool, str, dict]:
    """Processes a purchase. Returns (Success, Message, Updated Sheet)"""
    item = find_item(item_key)
    if not item:
        return False, f"Item `{item_key}` not found.", sheet
    
    val = item["value"]
    gil = sheet.get("gil", 0)
    
    if gil < val:
        return False, f"Not enough gil. {item['name']} costs {val}g. You have {gil}g.", sheet
        
    sheet["gil"] -= val
    
    if "inventory" not in sheet:
        sheet["inventory"] = []
        
    sheet["inventory"].append(item_key)
    
    return True, f"Purchased **{item['name']}** for {val}g. Remaining gil: {sheet['gil']}g.", sheet

def process_sell(sheet: dict, item_key: str) -> tuple[bool, str, dict]:
    """Processes a sale. Sells at 50% value."""
    if "inventory" not in sheet or item_key not in sheet["inventory"]:
        return False, f"You don't have `{item_key}` in your inventory.", sheet
        
    item = find_item(item_key)
    if not item:
        return False, f"Unknown item `{item_key}`.", sheet
        
    val = max(1, item["value"] // 2)
    sheet["inventory"].remove(item_key)
    sheet["gil"] = sheet.get("gil", 0) + val
    
    return True, f"Sold **{item['name']}** for {val}g. Total gil: {sheet['gil']}g.", sheet
