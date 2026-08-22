"""
Alchemy System - Recipes and brewing logic for Aethelgard
"""

ALCHEMY_RECIPES = {
    "potion": {
        "name": "Health Potion",
        "ingredients": ["blood_thistle", "honey_sap"],
        "result": "potion_standard",
        "description": "A standard restorative brew. Smells like copper and honey.",
    },
    "hi_potion_brew": {
        "name": "Hi-Potion",
        "ingredients": ["blood_thistle", "silver_moss"],
        "result": "hi_potion",
        "description": "A stronger restorative — the moss stabilizes the thistle's potency.",
    },
    "elixir_brew": {
        "name": "Elixir",
        "ingredients": ["silverleaf", "dire_root"],
        "result": "elixir",
        "description": "A deep green draught. The Silverleaf's shimmer fades as the root absorbs it.",
    },
    "xp_tonic": {
        "name": "Experience Tonic",
        "ingredients": ["silverleaf", "emerald"],
        "result": "xp_tonic",
        "description": "The emerald dissolves into a luminous green liquid. Sharpens the mind.",
    },
    "hunters_draught": {
        "name": "Hunter's Draught",
        "ingredients": ["dire_root", "topaz"],
        "result": "hunters_draught",
        "description": "A bitter amber tonic. The topaz dust settles into an oily film that smells like pine.",
    },
    "ironbark_tonic": {
        "name": "Ironbark Tonic",
        "ingredients": ["dire_root", "pearl"],
        "result": "ironbark_tonic",
        "description": "The root hardens as it absorbs the pearl's essence. Skin toughens on contact.",
    },
    "firebrew": {
        "name": "Firebrew",
        "ingredients": ["blood_thistle", "fire_opal"],
        "result": "firebrew",
        "description": "The opal cracks and bleeds fire into the brew. Handle with care.",
    },
    "phoenix_brew": {
        "name": "Phoenix Brew",
        "ingredients": ["silverleaf", "star_ruby"],
        "result": "phoenix_down",
        "description": "The star ruby ignites the silverleaf. It burns without consuming. Life from flames.",
    },
    "smoke_bomb": {
        "name": "Smoke Bomb",
        "ingredients": ["blood_thistle", "topaz"],
        "result": "smoke_bomb",
        "description": "A clay sphere filled with soot and ash. Throw to escape combat safely.",
    },
    "antidote": {
        "name": "Antidote",
        "ingredients": ["silver_moss", "honey_sap"],
        "result": "antidote",
        "description": "A sweet, herbal draught that neutralizes venoms.",
    },
    "warding_salve": {
        "name": "Warding Salve",
        "ingredients": ["silver_moss", "pearl"],
        "result": "warding_salve",
        "description": "A thick, grey paste that hardens skin against physical blows.",
    },
    "frenzy_draught": {
        "name": "Frenzy Draught",
        "ingredients": ["blood_thistle", "star_ruby"],
        "result": "frenzy_draught",
        "description": "A bubbling crimson liquid that induces combat frenzy.",
    },
    "moonwater": {
        "name": "Moonwater",
        "ingredients": ["silverleaf", "black_pearl"],
        "result": "moonwater",
        "description": "A shimmering water collected under full moonlight. Restores all HP.",
    },
    "trap_kit": {
        "name": "Trap Kit",
        "ingredients": ["dire_root", "fire_opal"],
        "result": "trap_kit",
        "description": "A bundle of springs and blades to lay down traps in dungeons.",
    },
}

def get_recipe(key):
    return ALCHEMY_RECIPES.get(key.lower())

def can_brew(sheet, recipe_key):
    recipe = get_recipe(recipe_key)
    if not recipe:
        return False, "Recipe not found."
    
    # Check if player has the recipe (learned)
    if recipe_key not in sheet.get("recipes", []):
        return False, f"You haven't learned how to brew {recipe['name']} yet."
    
    # Check ingredients
    ingredients = recipe.get("ingredients", [])
    if not isinstance(ingredients, list):
        ingredients = []
        
    inv = sheet.get("inventory", [])
    if not isinstance(inv, list):
        inv = []
    missing: list[str] = []
    inv_copy = list(inv)
    for item in ingredients:
        if item in inv_copy:
            inv_copy.remove(item)
        else:
            missing.append(item)
            
    if missing:
        return False, f"Missing ingredients: {', '.join(missing)}"
        
    return True, "Ready to brew."

def brew(sheet, recipe_key):
    success, msg = can_brew(sheet, recipe_key)
    if not success:
        return success, msg
    
    recipe = ALCHEMY_RECIPES[recipe_key.lower()]
    
    # Remove ingredients
    ingredients = recipe.get("ingredients", [])
    if not isinstance(ingredients, list):
        ingredients = []
        
    inv = sheet.get("inventory", [])
    if not isinstance(inv, list):
        inv = []
        sheet["inventory"] = inv
        
    # Net change in inventory: we remove ingredients, then append result
    inv_copy = list(inv)
    for item in ingredients:
        if item in inv_copy:
            inv_copy.remove(item)
    inv_copy.append(recipe["result"])
    
    from utils.ttrpg.character_manager import INVENTORY_LIMIT
    current_unique = set(inv_copy)
    if len(current_unique) > INVENTORY_LIMIT:
        return False, f"Your inventory has too many unique item types. Cap: {INVENTORY_LIMIT} unique types (brewing this would make it {len(current_unique)})."

    for item in ingredients:
        if item in inv:
            inv.remove(item)
        
    # Add result
    sheet.setdefault("inventory", []).append(recipe["result"])
    
    msg = f"Successfully brewed **{recipe['name']}**!"
    return True, msg

# ─── Recipe Discovery ─────────────────────────────────────────────────────────
# Maps ingredient keys → recipe keys they unlock on first pickup
INGREDIENT_DISCOVERS = {
    # Original herb recipes
    "blood_thistle": "potion",
    "honey_sap":     "potion",
    "silver_moss":   "hi_potion_brew",
    "dire_root":     "elixir_brew",
    # New recipes — herbs unlock them
    "silverleaf":    "elixir_brew",
    # Gems unlock their specific recipes
    "emerald":       "xp_tonic",
    "topaz":         "hunters_draught",
    "pearl":         "ironbark_tonic",
    "fire_opal":     "firebrew",
    "star_ruby":     "phoenix_brew",
    "black_pearl":   "moonwater",
}

# Secondary discoveries — when you already know one recipe from an ingredient,
# picking up a second ingredient for a DIFFERENT recipe reveals that one too.
SECONDARY_DISCOVERS = {
    "blood_thistle": ["hi_potion_brew", "firebrew", "smoke_bomb", "frenzy_draught"],
    "honey_sap":     ["potion", "antidote"],
    "silver_moss":   ["hi_potion_brew", "antidote", "warding_salve"],
    "dire_root":     ["elixir_brew", "hunters_draught", "ironbark_tonic", "trap_kit"],
    "silverleaf":    ["xp_tonic", "phoenix_brew", "moonwater"],
    "pearl":         ["ironbark_tonic", "warding_salve"],
    "topaz":         ["hunters_draught", "smoke_bomb"],
    "fire_opal":     ["firebrew", "trap_kit"],
    "star_ruby":     ["phoenix_brew", "frenzy_draught"],
    "black_pearl":   ["moonwater"],
}

def check_and_discover_recipes(sheet: dict, item_key: str) -> list[str]:
    """
    Call whenever an item enters the player's inventory.
    If the item is a crafting ingredient, reveals the associated recipe.
    Returns list of newly discovered recipe keys (empty if nothing new).
    """
    discovered = []
    known = sheet.get("recipes", [])

    # Primary discovery
    recipe_key = INGREDIENT_DISCOVERS.get(item_key)
    if recipe_key and recipe_key not in known:
        sheet.setdefault("recipes", []).append(recipe_key)
        known = sheet["recipes"]
        discovered.append(recipe_key)

    # Secondary discoveries
    for rk in SECONDARY_DISCOVERS.get(item_key, []):
        if rk not in known:
            sheet.setdefault("recipes", []).append(rk)
            known = sheet["recipes"]
            discovered.append(rk)

    return discovered
