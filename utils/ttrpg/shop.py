from utils.ttrpg.equipment_registry import (
    WEAPONS, ARMOR, CONSUMABLES, HEADGEAR, BOOTS, ACCESSORIES,
    HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR,
    HEMLOCK_STOCK_HEADGEAR, HEMLOCK_STOCK_BOOTS, HEMLOCK_STOCK_ACCESSORIES,
    ALIASES,
)

_REVERSE_ALIASES = {v: k for k, v in ALIASES.items()}

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

    from utils.ttrpg.calendar import get_special_day
    special = get_special_day()
    if special and "shop_special" in special:
        ex = special["shop_special"].get("extra_stock", [])
        itemk = special["shop_special"].get("item")
        for k in ex + ([itemk] if itemk else []):
            if k in WEAPONS and k not in weapons_keys: weapons_keys.append(k)
            elif k in ARMOR and k not in armor_keys: armor_keys.append(k)
            elif k in HEADGEAR and k not in headgear_keys: headgear_keys.append(k)
            elif k in BOOTS and k not in boots_keys: boots_keys.append(k)
            elif k in ACCESSORIES and k not in accessory_keys: accessory_keys.append(k)
            elif k in CONSUMABLES and k not in consumables_keys: consumables_keys.append(k)

    from utils.ttrpg.world_state import load_world_state
    wstate = load_world_state()
    special_sale = wstate.get("special_item_sale")
    if special_sale and isinstance(special_sale, dict):
        itemk = special_sale.get("item")
        if itemk:
            from utils.infrastructure.logging.kaia_logger import log_info
            log_info(f"[shop] special_item_sale active: injecting '{itemk}' into shop inventory")
            if itemk in WEAPONS and itemk not in weapons_keys: weapons_keys.append(itemk)
            elif itemk in ARMOR and itemk not in armor_keys: armor_keys.append(itemk)
            elif itemk in HEADGEAR and itemk not in headgear_keys: headgear_keys.append(itemk)
            elif itemk in BOOTS and itemk not in boots_keys: boots_keys.append(itemk)
            elif itemk in ACCESSORIES and itemk not in accessory_keys: accessory_keys.append(itemk)
            elif itemk in CONSUMABLES and itemk not in consumables_keys: consumables_keys.append(itemk)


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

    # Overlay special discounts non-destructively
    if special and "shop_special" in special:
        itemk = special["shop_special"].get("item")
        if itemk:
            for d in (weapons, armor, headgear, boots, accessories, consumables):
                if itemk in d:
                    d[itemk] = d[itemk].copy()
                    d[itemk]["value"] = special["shop_special"].get("price", d[itemk]["value"])

    # Overlay special item sale from world state
    if special_sale and isinstance(special_sale, dict):
        itemk = special_sale.get("item")
        price = special_sale.get("price")
        if itemk:
            for d in (weapons, armor, headgear, boots, accessories, consumables):
                if itemk in d:
                    d[itemk] = d[itemk].copy()
                    d[itemk]["value"] = price

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

    # ── NEW: reverse alias lookup (handles old inventory keys) ──
    alt_key = _REVERSE_ALIASES.get(item_key)
    if alt_key:
        for cat, reg in ALL:
            if alt_key in reg:
                return {"category": cat, "key": alt_key, **reg[alt_key]}

    # Fallback: match by item name (e.g. "Rusty Dagger")
    for cat, reg in ALL:
        for k, v in reg.items():
            if v.get("name", "").lower() == item_key.replace("_", " "):
                return {"category": cat, "key": k, **v}

    return None

def get_buy_price(item: dict, loc: str = "hemlocks_store", reputation: int = 0,
                  cha_mod: int = 0, quantity: int = 1) -> int:
    """The price a player will actually be charged for `item`.

    Extracted from process_purchase so the shop UI can label a dropdown with
    the same figure the checkout charges. The UI previously computed its own
    price that applied only the calendar and sale overrides — it ignored
    reputation, the CHA discount (up to 10%) and the market-glut multiplier, so
    the label disagreed with the charge for any character with a CHA modifier
    or during a glut event. Flagged in noon_events_mechanical_audit.md Phase A
    and unfixed until now; a single shared function is what stops it recurring.
    """
    from utils.ttrpg.world_state import load_world_state
    from utils.ttrpg.calendar import get_special_day

    real_key = item["key"]

    # Reputation modifier
    price_mult = 1.0
    if reputation >= 100: price_mult = 0.8  # 20% discount
    elif reputation >= 50:  price_mult = 0.9  # 10% discount
    elif reputation < -20:  price_mult = 1.1  # 10% markup
    # CHA discount: each +1 CHA mod = 2% discount (max 10%)
    cha_discount = min(0.10, max(0.0, cha_mod * 0.02))
    price_mult -= cha_discount

    # Temporary price multiplier (market glut event)
    wstate = load_world_state()
    if wstate.get("shop_price_mult", 1.0) != 1.0:
        price_mult *= wstate.get("shop_price_mult", 1.0)

    # Calendar shop_special override
    special = get_special_day()
    base_value = item["value"]
    if special and "shop_special" in special and loc == "hemlocks_store":
        if special["shop_special"].get("item") == real_key:
            base_value = special["shop_special"].get("price", base_value)

    # special_item_sale world_state override
    special_sale = wstate.get("special_item_sale")
    if special_sale and isinstance(special_sale, dict) and loc == "hemlocks_store":
        if special_sale.get("item") == real_key:
            base_value = special_sale.get("price", base_value)

    return int(base_value * quantity * price_mult)


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

    val = get_buy_price(item, loc, reputation=reputation, cha_mod=cha_mod, quantity=quantity)
    gil = sheet.get("gil", 0)
    
    if gil < val:
        return False, f"Not enough gil. {quantity}x {item['name']} costs {val}g. You have {gil}g.", sheet
        
    from utils.ttrpg.character_manager import INVENTORY_LIMIT
    current_unique = set(sheet.get("inventory", []))
    if len(current_unique | {real_key}) > INVENTORY_LIMIT:
        return False, f"Your inventory has too many unique item types. Cannot purchase {quantity}x {item['name']}. Cap: {INVENTORY_LIMIT} unique types (currently holding {len(current_unique)}).", sheet

    sheet["gil"] -= val
    
    if "inventory" not in sheet:
        sheet["inventory"] = []
        
    sheet["inventory"].extend([real_key] * quantity)
    
    if quantity == 1:
        msg = f"Purchased **{item['name']}** for {val}g. Remaining gil: {sheet['gil']}g."
    else:
        msg = f"Purchased **{quantity}x {item['name']}** for {val}g. Remaining gil: {sheet['gil']}g."
        
    return True, msg, sheet

def get_sell_price(item_value: int, reputation: int = 0, cha_mod: int = 0) -> int:
    """Calculates the actual sell price of an item based on reputation and CHA."""
    sell_mult = 0.25 # BASE NERF
    if reputation >= 100: sell_mult = 0.45  # 25% base + 20% bonus
    elif reputation >= 50:  sell_mult = 0.35  # 25% base + 10% bonus
    elif reputation < -20:  sell_mult = 0.15  # 10% penalty
    
    cha_bonus = min(0.10, max(0.0, cha_mod * 0.02))
    sell_mult += cha_bonus
    
    # Check world_state for temporary price multiplier (market glut event)
    from utils.ttrpg.world_state import load_world_state
    wstate = load_world_state()
    if wstate.get("shop_price_mult", 1.0) != 1.0:
        sell_mult *= wstate.get("shop_price_mult", 1.0)
    
    return max(1, int(item_value * sell_mult))

def process_sell(sheet: dict, item_key: str, reputation: int = 0, cha_mod: int = 0) -> tuple[bool, str, dict]:
    """Processes a sale. Sells at 50% base value + reputation bonus + CHA bonus."""
    loc = sheet.get("location", "hemlocks_store")
    if reputation < -50:
        merchant_name = "The merchant" if loc == "caravan" else "Hemlock"
        refusal_msg = "spits on the floor. 'I'm not buying your stolen goods.'" if loc != "caravan" else "shakes his head. 'I don't deal with your kind.'"
        return False, f"{merchant_name} {refusal_msg}", sheet
    
    item = find_item(item_key)
    if not item:
        return False, f"Unknown item `{item_key}`.", sheet
    
    # ── NEW: Resolve which key is actually in the inventory ──
    real_key = item["key"]
    found_key = None
    inventory = sheet.get("inventory", [])
    
    if real_key in inventory:
        found_key = real_key
    else:
        # Check if an older key (alias) is in the inventory instead
        # e.g. user has "spear" in inventory, but find_item resolved to "iron_spear"
        from utils.ttrpg.equipment_registry import ALIASES
        for alias, target in ALIASES.items():
            if target == real_key and alias in inventory:
                found_key = alias
                break
                
    if not found_key:
        return False, f"You don't have `{item_key}` in your inventory.", sheet
        
    # Reputation modifier
    val = get_sell_price(item["value"], reputation, cha_mod)
    sheet["inventory"].remove(found_key)
    sheet["gil"] = sheet.get("gil", 0) + val
    
    return True, f"Sold **{item['name']}** for {val}g. Total gil: {sheet['gil']}g.", sheet
