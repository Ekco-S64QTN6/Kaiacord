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
    
    # Add XP
    sheet["xp"] += recipe["xp"]
    
    return True, f"Successfully brewed **{recipe['name']}**! (+{recipe['xp']} XP)"
