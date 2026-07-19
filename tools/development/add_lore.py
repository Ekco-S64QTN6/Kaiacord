import json

def get_lore_injection():
    return '''
def get_dynamic_lore(floor_num, base_meta, base_flav):
    import copy
    meta = copy.deepcopy(base_meta)
    
    # Let's inject progressive Elara lore into the 'empty' or 'shrine' rooms (usually F, A, J, O)
    flav = base_flav
    
    if 1 <= floor_num <= 10:
        flav += " A faint scent of Oakhaven herbs lingers where it shouldn't."
        if "F" in meta:
            meta["F"]["desc"] = "A scrap of paper is pinned to the timber: 'Shipment 4 from H. Store received. The Elder paid in full.' Hemlock is supplying the deep."
    elif 11 <= floor_num <= 20:
        flav += " The lanterns here burn with a familiar, unsettling blue tint."
        if "O" in meta:
            meta["O"]["desc"] = "A makeshift camp. A journal lies open: 'She said the blue flame meant danger. She lied. It means the mountain is hungry, and she is ringing the dinner bell.'"
    elif 21 <= floor_num <= 30:
        if "F" in meta:
            meta["F"]["desc"] = "An old ledger is carved into the bone wall. It lists names. Two missing scouts from Oakhaven are at the bottom, marked as 'Tithe'."
    elif 31 <= floor_num <= 40:
        if "J" in meta:
            meta["J"]["desc"] = "A shrine identical to the one in Oakhaven, but the flame here is black. A silver hair—just like Elara's—is caught in the stone basin."
    elif 41 <= floor_num <= 50:
        flav += " The heat doesn't warm you; it feels like it's trying to digest you."
        if "F" in meta:
            meta["F"]["desc"] = "A rusted plaque bears an Aeridorian inscription: 'The Vessel must be stationed above. The Vessel must maintain the illusion of sanctuary.'"
    elif 51 <= floor_num <= 60:
        if "O" in meta:
            meta["O"]["desc"] = "A perfectly preserved room. On the desk is a letter in Elara's handwriting: 'The adventurers suspect nothing. The offering will be sufficient for the Solstice.'"
    elif 61 <= floor_num <= 70:
        flav += " The mountain breathes, and it smells like Oakhaven's well."
        if "F" in meta:
            meta["F"]["desc"] = "A crystalline terminal is active. It shows a map of Oakhaven. Lines of resonance don't flow out from the town; they flow down. Oakhaven is a farm. The town is the crop."
    elif 71 <= floor_num <= 77:
        if "A" in meta:
            meta["A"]["desc"] = "The stairs descend into a fleshy, pulsing abyss. The walls whisper in Elara's voice: 'Thank you for bringing yourselves to the harvest.'"

    return meta, flav

def main():
    floors = {}
    base_configs = [
        (F1R, F1C, F1M, "The Working Tunnels", "Abandoned mine shafts. Timber supports creak. The lanterns are still lit."),
        (F2R, F2C, F2M, "The Bone Warrens", "Catacombs carved before the mine. The dead did not stay placed."),
        (F3R, F3C, F3M, "The Sunken Forge", "An Aeridorian forge buried by time. The fires still burn."),
        (F4R, F4C, F4M, "The Deep Dark", "Beyond the mine. Beyond the forge. Something older."),
        (F5R, F5C, F5M, "The Heart of the Mountain", "The deepest point. The mountain has a heartbeat."),
    ]
    
    for n in range(1, 78):
        if n <= 15:
            rms, corrs, base_m, name, base_f = base_configs[0]
        elif n <= 30:
            rms, corrs, base_m, name, base_f = base_configs[1]
        elif n <= 45:
            rms, corrs, base_m, name, base_f = base_configs[2]
        elif n <= 60:
            rms, corrs, base_m, name, base_f = base_configs[3]
        else:
            rms, corrs, base_m, name, base_f = base_configs[4]
            
        meta, flav = get_dynamic_lore(n, base_m, base_f)
        
        # Now update the boss encounters to the exact stair guardian for this floor
        from utils.ttrpg.spine_dungeon import STAIR_GUARDIANS
        guardian = STAIR_GUARDIANS.get(n)
        
        # Find which room key holds the stairs_down (usually the boss room precedes it, or the stairs down itself is the boss)
        # Actually, let's just let the engine handle the guardian combat on descend click as implemented earlier. 
        # But we can update the 'boss' room in the meta to show the correct monster key if we want.
        
        lines = place(rms, corrs)
        floor = build(lines, meta, name, flav)
        
        floor["floor_num"] = n
        
        # Override stairs down on floor 77
        if n == 77:
            floor["stairs_down_key"] = None
            
        floors[str(n)] = floor

    with open("utils/ttrpg/spine_layouts.json", "w") as f:
        json.dump(floors, f, indent=2)
    print("Wrote spine_layouts.json for 77 floors")
'''

with open("utils/ttrpg/build_spine_layouts.py", "r") as f:
    content = f.read()

import re
content = re.sub(r'def main\(\):.*', get_lore_injection(), content, flags=re.DOTALL)

with open("utils/ttrpg/build_spine_layouts.py", "w") as f:
    f.write(content)
