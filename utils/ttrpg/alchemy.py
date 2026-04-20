"""
Alchemy System - Recipes and brewing logic for Aethelgard
"""

ALCHEMY_RECIPES = {
    "antidote": {
        "name": "Antidote",
        "ingredients": ["silver_moss", "dire_root"],
        "result": "antidote",
        "description": "A clear, bitter brew that neutralizes toxins.",
        "xp": 25,
    },
    "potion": {
        "name": "Health Potion",
        "ingredients": ["blood_thistle", "honey_sap"],
        "result": "potion_standard",
        "description": "A standard restorative brew. Smells like copper and honey.",
        "xp": 20,
    },
    "hi_potion_brew": {
        "name": "Hi-Potion",
        "ingredients": ["blood_thistle", "silver_moss"],
        "result": "hi_potion",
        "description": "A stronger restorative — the moss stabilizes the thistle's potency.",
        "xp": 30,
    },
    "elixir_brew": {
        "name": "Elixir",
        "ingredients": ["silverleaf", "dire_root"],
        "result": "elixir",
        "description": "A deep green draught. The Silverleaf's shimmer fades as the root absorbs it.",
        "xp": 40,
    },
    "xp_tonic": {
        "name": "Experience Tonic",
        "ingredients": ["silverleaf", "emerald"],
        "result": "xp_tonic",
        "description": "The emerald dissolves into a luminous green liquid. Sharpens the mind.",
        "xp": 35,
    },
    "hunters_draught": {
        "name": "Hunter's Draught",
        "ingredients": ["dire_root", "topaz"],
        "result": "hunters_draught",
        "description": "A bitter amber tonic. The topaz dust settles into an oily film that smells like pine.",
        "xp": 30,
    },
    "ironbark_tonic": {
        "name": "Ironbark Tonic",
        "ingredients": ["dire_root", "pearl"],
        "result": "ironbark_tonic",
        "description": "The root hardens as it absorbs the pearl's essence. Skin toughens on contact.",
        "xp": 30,
    },
    "firebrew": {
        "name": "Firebrew",
        "ingredients": ["blood_thistle", "fire_opal"],
        "result": "firebrew",
        "description": "The opal cracks and bleeds fire into the brew. Handle with care.",
        "xp": 35,
    },
    "greater_antidote": {
        "name": "Greater Antidote",
        "ingredients": ["silver_moss", "opal"],
        "result": "panacea",
        "description": "The opal refracts the moss's healing energy into every color. Cures anything.",
        "xp": 45,
    },
    "phoenix_brew": {
        "name": "Phoenix Brew",
        "ingredients": ["silverleaf", "star_ruby"],
        "result": "phoenix_down",
        "description": "The star ruby ignites the silverleaf. It burns without consuming. Life from flames.",
        "xp": 50,
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
    "silver_moss":   "antidote",
    "dire_root":     "antidote",
    # New recipes — herbs unlock them
    "silverleaf":    "elixir_brew",
    # Gems unlock their specific recipes
    "emerald":       "xp_tonic",
    "topaz":         "hunters_draught",
    "pearl":         "ironbark_tonic",
    "fire_opal":     "firebrew",
    "opal":          "greater_antidote",
    "star_ruby":     "phoenix_brew",
}

# Secondary discoveries — when you already know one recipe from an ingredient,
# picking up a second ingredient for a DIFFERENT recipe reveals that one too.
SECONDARY_DISCOVERS = {
    "blood_thistle": ["hi_potion_brew", "firebrew"],
    "silver_moss":   ["hi_potion_brew", "greater_antidote"],
    "dire_root":     ["elixir_brew", "hunters_draught", "ironbark_tonic"],
    "silverleaf":    ["xp_tonic", "phoenix_brew"],
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
