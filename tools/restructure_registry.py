import re
import random
import os
import shutil

def restructure(filepath):
    random.seed(42) # Deterministic modifications for droppable flags
    
    with open(filepath, 'r') as f:
        lines = f.readlines()

    out_lines = []
    
    in_get_caravan_stock = False
    aliases_idx = -1
    current_category = None
    
    for i, line in enumerate(lines):
        if line.startswith("def get_caravan_stock():"):
            in_get_caravan_stock = True
            continue # We will inject the new function later
            
        if line.startswith("WEAPONS = {"):
            current_category = "WEAPONS"
        elif line.startswith("ARMOR = {"):
            current_category = "ARMOR"
        elif line.startswith("HEADGEAR = {"):
            current_category = "HEADGEAR"
        elif line.startswith("BOOTS = {"):
            current_category = "BOOTS"
        elif line.startswith("ACCESSORIES = {"):
            current_category = "ACCESSORIES"
        elif line.startswith("CONSUMABLES = {"):
            current_category = "CONSUMABLES"

        if in_get_caravan_stock:
            # Consume lines until we find ALIASES = {
            if line.startswith("ALIASES = {"):
                in_get_caravan_stock = False
                aliases_idx = len(out_lines) # The index where ALIASES starts in our out_lines
                out_lines.append(line)
            continue

        # Look for "value": <number> and "tier": <number> on the same line
        val_match = re.search(r'"value":\s*(\d+)', line)
        tier_match = re.search(r'"tier":\s*(\d+)', line)
        
        if val_match and tier_match and current_category:
            old_value = int(val_match.group(1))
            tier = int(tier_match.group(1))
            
            # Determine new value based on tier and category
            if current_category == "WEAPONS":
                price_map = {0: 50, 1: 50, 2: 300, 3: 1200, 4: 3000, 5: 8000}
            elif current_category == "ARMOR":
                price_map = {0: 40, 1: 40, 2: 250, 3: 1000, 4: 2500, 5: 7000}
            elif current_category in ("HEADGEAR", "BOOTS"):
                price_map = {0: 25, 1: 25, 2: 150, 3: 600, 4: 1500, 5: 4000}
            elif current_category == "ACCESSORIES":
                price_map = {0: 30, 1: 30, 2: 200, 3: 800, 4: 2000, 5: 5000}
            else: # CONSUMABLES
                price_map = {0: 0, 1: 15, 2: 40, 3: 100, 4: 250, 5: 600}
            
            new_value = price_map.get(tier, old_value)
                
            # Replace value
            line = line[:val_match.start(1)] + str(new_value) + line[val_match.end(1):]
            
            # Recalculate tier_match because string length might have changed
            tier_match = re.search(r'"tier":\s*(\d+)', line)
            
            # Optionally add "droppable_only": True for Tier 2+ gear
            # Avoid doing this for consumables
            if current_category != "CONSUMABLES" and tier >= 2 and random.random() < 0.35:
                # find the end of the tier value
                end_idx = tier_match.end(1)
                line = line[:end_idx] + ', "droppable_only": True' + line[end_idx:]
                
        out_lines.append(line)

    caravan_func = """def get_caravan_stock():
    \"\"\"Return strictly tier-2 and tier-3 item keys split into gear and consumables for the traveling caravan.\"\"\"
    gear = []
    consumable_keys = []
    for k, v in WEAPONS.items():
        if v.get("tier") in (2, 3) and not v.get("droppable_only"):
            gear.append(k)
    for k, v in ARMOR.items():
        if v.get("tier") in (2, 3) and not v.get("droppable_only"):
            gear.append(k)
    for k, v in HEADGEAR.items():
        if v.get("tier") in (2, 3) and not v.get("droppable_only"):
            gear.append(k)
    for k, v in BOOTS.items():
        if v.get("tier") in (2, 3) and not v.get("droppable_only"):
            gear.append(k)
    for k, v in ACCESSORIES.items():
        if v.get("tier") in (2, 3) and not v.get("droppable_only"):
            gear.append(k)
    for k, v in CONSUMABLES.items():
        if v.get("tier") in (2, 3) and not v.get("droppable_only"):
            consumable_keys.append(k)
    return gear, consumable_keys

"""
    # Insert the caravan function right before ALIASES
    if aliases_idx != -1:
        out_lines.insert(aliases_idx, caravan_func)
    else:
        out_lines.append(caravan_func)

    out_path = "/tmp/equipment_registry.py.tmp"
    with open(out_path, 'w') as f:
        f.writelines(out_lines)

    print(f"Restructure complete! Saved to {out_path}")

if __name__ == "__main__":
    file_path = "/home/ekco/github/Kaiacord/utils/ttrpg/equipment_registry.py"
    restructure(file_path)
