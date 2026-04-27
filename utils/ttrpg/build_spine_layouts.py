#!/usr/bin/env python3
"""Generate spine_layouts.json — 5 hand-crafted dungeon floors."""
import json, os, sys

GRID = 24

def place(room_list, corridor_list, size=GRID):
    grid = [['.' for _ in range(size)] for _ in range(size)]
    for label, rx, ry, rw, rh in room_list:
        for dy in range(rh):
            for dx in range(rw):
                grid[ry+dy][rx+dx] = label
    for x1, y1, x2, y2 in corridor_list:
        if x1 == x2:
            for y in range(min(y1,y2), max(y1,y2)+1):
                if grid[y][x1] == '.': grid[y][x1] = '+'
        elif y1 == y2:
            for x in range(min(x1,x2), max(x1,x2)+1):
                if grid[y1][x] == '.': grid[y1][x] = '+'
    return [''.join(row) for row in grid]

def build(lines, meta, name, flavor):
    rooms, conns = {}, {}
    room_centers = {}
    for ch, m in meta.items():
        coords = []
        for y, line in enumerate(lines):
            for x, c in enumerate(line):
                if c == ch:
                    coords.append((x,y))
        if coords:
            cx = sum(x for x,y in coords) // len(coords)
            cy = sum(y for x,y in coords) // len(coords)
            best = min(coords, key=lambda p: abs(p[0]-cx) + abs(p[1]-cy))
            room_centers[ch] = best

    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch == '.': continue
            k = f"{x},{y}"
            if ch == '+':
                import secrets
                if secrets.randbelow(100) < 5:
                    rooms[k] = {"type":"trap","cleared":False,"monster_key":None,
                        "boss_name":None,"description":"You stepped on a loose stone. A trap mechanism clicks in the dark!",
                        "is_room":False,"label":None,"room_name":"Trapped Passage"}
                else:
                    rooms[k] = {"type":"empty","cleared":True,"monster_key":None,
                        "boss_name":None,"description":"A narrow, winding passage.",
                        "is_room":False,"label":None,"room_name":None}
            else:
                m = meta[ch]
                is_center = (x,y) == room_centers.get(ch)
                if is_center:
                    rt = m["type"]
                    mk = m.get("monster_key")
                    bn = m.get("boss_name")
                    cl = rt in ("empty","stairs_up","stairs_down")
                else:
                    rt = "empty"
                    mk = None
                    bn = None
                    cl = True
                rooms[k] = {"type":rt,
                    "cleared":cl,
                    "monster_key":mk,"boss_name":bn,
                    "description":m.get("desc",""),"is_room":True,
                    "label":ch,"room_name":m.get("name","")}
                    
    for k in rooms:
        x,y = (int(v) for v in k.split(","))
        conns[k] = [d for d,(dx,dy) in
            {"N":(0,-1),"S":(0,1),"E":(1,0),"W":(-1,0)}.items()
            if f"{x+dx},{y+dy}" in rooms]
            
    su = sd = bk = None
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch in meta and (x,y) == room_centers.get(ch):
                t = meta[ch]["type"]
                if t == "stairs_up" and not su: su = f"{x},{y}"
                elif t == "stairs_down" and not sd: sd = f"{x},{y}"
                elif t == "boss" and not bk: bk = f"{x},{y}"
                
    visited = set(); q = [su] if su else []
    while q:
        n = q.pop(0)
        if n in visited: continue
        visited.add(n)
        x,y = (int(v) for v in n.split(","))
        for dx,dy in [(0,-1),(0,1),(1,0),(-1,0)]:
            nb = f"{x+dx},{y+dy}"
            if nb in rooms and nb not in visited: q.append(nb)
            
    if set(rooms) - visited:
        print(f"FAIL {name}: {len(set(rooms)-visited)} unreachable")
        print(f"Rooms total: {len(rooms)}, Visited: {len(visited)}")
        sys.exit(1)
        
    return {"rooms":rooms,"connections":conns,"stairs_up_key":su,
        "stairs_down_key":sd,"boss_key":bk,"grid_size":GRID,
        "floor_name":name,"floor_flavor":flavor}


# ═══════════════════════════════════════════════════════════════════
# FLOOR 1 — THE WORKING TUNNELS
# A sprawling, dense grid of abandoned mine shafts.
# ═══════════════════════════════════════════════════════════════════
F1R = [
    ('A', 1,1, 4,4),   ('B', 9,1, 5,4),   ('C', 18,1, 5,4),
    ('D', 1,8, 4,5),   ('E', 9,8, 5,5),   ('F', 18,8, 5,5),
    ('G', 1,16, 4,6),  ('H', 9,16, 5,6),  ('I', 18,16, 5,3),
    ('J', 18,21, 5,2), # Boss
    ('K', 6,3, 2,2),   # Side rooms
    ('L', 15,10, 2,2),
    ('M', 6,19, 2,2)
]
F1C = [
    (5,2, 8,2), (14,2, 17,2),     # Horizontals Row 1
    (3,5, 3,7), (11,5, 11,7), (20,5, 20,7), # Verticals to Row 2
    (5,10, 8,10), (14,10, 17,10), # Horizontals Row 2
    (3,13, 3,15), (11,13, 11,15), (20,13, 20,15), # Verticals to Row 3
    (5,18, 8,18), (14,18, 17,18), # Horizontals Row 3
    (20,19, 20,20), # Down to Boss
    (5,3, 5,3), (14,10, 14,10), (5,19, 5,19) # Doorways to side rooms
]
F1M = {
    "A":{"type":"stairs_up","name":"Entry Hall","desc":"Daylight filters down the stairwell. The air smells of rust and old timber."},
    "B":{"type":"guard","name":"Guard Barracks","desc":"Overturned bunks. Someone fortified this recently.","monster_key":"bandit"},
    "C":{"type":"monster","name":"Ore Shaft","desc":"Pick marks line the walls. Something skitters in the dark.","monster_key":"bat"},
    "D":{"type":"empty","name":"Collapsed Tunnel","desc":"The ceiling has caved in here. Dust still settles."},
    "E":{"type":"guard","name":"Central Hub","desc":"A large junction box. Rusted minecarts are tipped over as barricades.","monster_key":"bandit"},
    "F":{"type":"monster","name":"Flooded Chamber","desc":"Water drips from the ceiling. A dark pool covers the floor.","monster_key":"blood_slime"},
    "G":{"type":"treasure","name":"Foreman's Stash","desc":"A locked strongbox hidden under some rotted planks."},
    "H":{"type":"antechamber","name":"Foreman's Anteroom","desc":"A heavy iron door. Scratch marks on the inside."},
    "I":{"type":"stairs_down","name":"The Descent","desc":"A shaft drops into darkness. Cold air rises from below."},
    "J":{"type":"boss","name":"Foreman's Office","desc":"Kregg is here. He didn't leave with the others.","monster_key":"foreman_kregg","boss_name":"Foreman Kregg"},
    "K":{"type":"empty","name":"Tool Closet","desc":"Rusted pickaxes and frayed rope."},
    "L":{"type":"shrine","name":"Mushroom Grotto","desc":"Bioluminescent fungi cast a faint blue glow. The air is warm."},
    "M":{"type":"monster","name":"Rest Area","desc":"A makeshift camp. Something has taken up residence.","monster_key":"spiderling"}
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 2 — THE BONE WARRENS
# Serpentine catacombs with lots of dead ends and winding paths.
# ═══════════════════════════════════════════════════════════════════
F2R = [
    ('A', 19,1, 4,4),  # Stairs Up
    ('B', 12,1, 4,4),  ('C', 12,8, 4,4),  ('D', 19,8, 4,4),
    ('E', 5,8, 4,4),   ('F', 5,1, 4,4),   ('G', 1,1, 3,7),
    ('H', 1,10, 4,4),  ('I', 8,13, 5,5),  ('J', 16,13, 5,5),
    ('K', 16,20, 5,3), ('L', 8,20, 5,3),  ('M', 1,17, 4,6) # Boss
]
F2C = [
    (16,3, 18,3),      # A to B
    (13,5, 13,7),      # B to C
    (16,10, 18,10),    # C to D
    (9,10, 11,10),     # C to E
    (6,5, 6,7),        # E to F
    (4,3, 4,3),        # F to G
    (2,8, 2,9),        # G to H
    (5,13, 7,13),      # H to I
    (13,15, 15,15),    # I to J
    (18,18, 18,19),    # J to K
    (13,21, 15,21),    # K to L
    (5,21, 7,21),      # L to M
]
F2M = {
    "A":{"type":"stairs_up","name":"Upper Landing","desc":"The shaft from the tunnels above. Wind moans through the gap."},
    "B":{"type":"empty","name":"Dusty Hall","desc":"Urns line the walls. Most are smashed."},
    "C":{"type":"guard","name":"Crypt Gate","desc":"Iron bars across the passage. Something is locked in.","monster_key":"wight"},
    "D":{"type":"treasure","name":"Burial Offerings","desc":"Grave goods piled in alcoves. Gold dulled by centuries."},
    "E":{"type":"monster","name":"Ossuary","desc":"Bones stacked floor to ceiling. Not all of them are staying put.","monster_key":"skeleton"},
    "F":{"type":"empty","name":"Defaced Shrine","desc":"The statues here have had their faces chipped away."},
    "G":{"type":"trap","name":"Collapsing Floor","desc":"The stonework is loose. A dark pit yawns below."},
    "H":{"type":"monster","name":"Embalming Room","desc":"Stone slabs stained with old chemicals.","monster_key":"ghoul"},
    "I":{"type":"guard","name":"The Grand Hall","desc":"A massive pillared chamber. The shadows stretch too far.","monster_key":"dark_wizard"},
    "J":{"type":"monster","name":"Noble Tombs","desc":"Sarcophagi of the elite. Some are open.","monster_key":"wight"},
    "K":{"type":"stairs_down","name":"The Deep Stair","desc":"Carved steps descend. The air tastes of copper and ozone."},
    "L":{"type":"antechamber","name":"Sealed Door","desc":"The door is warm. The carvings move when you look away."},
    "M":{"type":"boss","name":"The Unburied's Tomb","desc":"It was buried here. It dug itself out. It has been waiting.","monster_key":"the_unburied","boss_name":"The Unburied"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 3 — THE SUNKEN FORGE
# Industrial layout, symmetrical wings branching from central shafts.
# ═══════════════════════════════════════════════════════════════════
F3R = [
    ('A', 10,1, 4,3),   
    ('B', 4,5, 5,4),    ('C', 15,5, 5,4), 
    ('D', 10,6, 4,3),   
    ('E', 1,5, 2,4),    ('F', 21,5, 2,4), 
    ('G', 10,11, 4,4),  
    ('H', 4,11, 5,4),   ('I', 15,11, 5,4),
    ('J', 10,17, 4,3),  
    ('K', 10,21, 4,2)   # Boss
]
F3C = [
    (11,4, 11,5),       # A down to D
    (9,7, 9,7),         # D left to B
    (14,7, 14,7),       # D right to C
    (3,6, 3,6),         # B left to E
    (20,6, 20,6),       # C right to F
    (11,9, 11,10),      # D down to G
    (9,12, 9,12),       # G left to H
    (14,12, 14,12),     # G right to I
    (11,15, 11,16),     # G down to J
    (11,20, 11,20)      # J down to K
]
F3M = {
    "A":{"type":"stairs_up","name":"Forge Entrance","desc":"Heat rises from below. The stone walls are warm to the touch."},
    "B":{"type":"monster","name":"Sentry Post","desc":"Two pedestals. The constructs on them are not decorative.","monster_key":"gargoyle"},
    "C":{"type":"guard","name":"Golem Bay","desc":"Storage alcoves for finished constructs. Not all are empty.","monster_key":"golem"},
    "D":{"type":"empty","name":"Heat Vent","desc":"Massive iron grates in the floor blast hot air."},
    "E":{"type":"treasure","name":"Cooling Room","desc":"Racks of hardened weapons left to rust."},
    "F":{"type":"stairs_down","name":"Thermal Shaft","desc":"A shaft descending along a magma channel. The heat is brutal."},
    "G":{"type":"guard","name":"Central Gearbox","desc":"A massive mechanism grinds endlessly here.","monster_key":"iron_golem"},
    "H":{"type":"shrine","name":"Maker's Altar","desc":"An altar to whoever built this place. Offerings of metal and gem."},
    "I":{"type":"monster","name":"Scrap Pit","desc":"Failed experiments tossed aside. Some are still twitching.","monster_key":"soldier"},
    "J":{"type":"antechamber","name":"Thermal Shaft","desc":"A heavy blast door glowing cherry red."},
    "K":{"type":"boss","name":"Warden's Chamber","desc":"It was built to guard this forge. It has never stopped.","monster_key":"resonance_warden","boss_name":"Resonance Warden"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 4 — THE DEEP DARK
# A massive open cavern feel, rooms are loose, connected by long paths.
# ═══════════════════════════════════════════════════════════════════
F4R = [
    ('A', 1,20, 4,3),   # Stairs Up (Bottom Left)
    ('B', 1,12, 5,5),   ('C', 9,18, 6,5),
    ('D', 8,9, 4,4),    ('E', 18,17, 5,6),
    ('F', 16,10, 4,4),  ('G', 2,2, 5,5),
    ('H', 10,2, 5,4),   ('I', 18,2, 5,5) # Boss
]
F4C = [
    (2,17, 2,19),       # A-B
    (5,21, 8,21),       # A-C
    (6,12, 7,12),       # B-D
    (12,11, 15,11),     # D-F
    (15,20, 17,20),     # C-E
    (17,14, 17,16),     # F-E
    (4,7, 4,11),        # B-G
    (7,4, 9,4),         # G-H
    (10,6, 10,8),       # H-D
    (15,4, 17,4),       # H-I
]
F4M = {
    "A":{"type":"stairs_up","name":"Breach Point","desc":"The mine wall was broken through. Whatever is beyond was not meant to be found."},
    "B":{"type":"empty","name":"Silent Cavern","desc":"The echo of your footsteps dies instantly. Something absorbs the sound."},
    "C":{"type":"monster","name":"Thought Eater Den","desc":"Your memories itch. Something is browsing them.","monster_key":"mind_flayer"},
    "D":{"type":"guard","name":"Chasm Bridge","desc":"A narrow rock bridge over a bottomless pit. Guarded.","monster_key":"dark_knight"},
    "E":{"type":"stairs_down","name":"Abyssal Drop","desc":"The floor ends. A jagged stairway winds down into nothing."},
    "F":{"type":"trap","name":"Void Pocket","desc":"Gravity feels lighter here. Shadows move independently."},
    "G":{"type":"monster","name":"Eldritch Hive","desc":"Fleshy growths pulse on the walls.","monster_key":"beholder"},
    "H":{"type":"antechamber","name":"The Last Camp","desc":"Bedrolls. Cold rations. The last journal entry is just the word 'watching.'"},
    "I":{"type":"boss","name":"The Last of the Party","desc":"It used to be an adventurer. Now it remembers being one.","monster_key":"the_last_of_the_party","boss_name":"The Last of the Party"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 5 — THE HEART OF THE MOUNTAIN
# A massive symmetrical labyrinth sealing the core.
# ═══════════════════════════════════════════════════════════════════
F5R = [
    ('A', 10,1, 4,4),   # Stairs Up
    ('B', 2,6, 5,5),    ('C', 17,6, 5,5),
    ('D', 10,8, 4,4),   # Center Gate 1
    ('E', 2,14, 5,5),   ('F', 17,14, 5,5),
    ('G', 10,15, 4,4),  # Center Gate 2
    ('H', 8,20, 8,3)    # Boss Room (Very Large)
]
F5C = [
    (11,5, 11,7),       # A to D
    (7,8, 9,8),         # D to B
    (14,8, 16,8),       # D to C
    (4,11, 4,13),       # B to E
    (19,11, 19,13),     # C to F
    (7,16, 9,16),       # E to G
    (14,16, 16,16),     # F to G
    (11,12, 11,14),     # D to G
    (11,19, 11,19),     # G to H
]
F5M = {
    "A":{"type":"stairs_up","name":"The Threshold","desc":"The stairs end. The walls are not rock anymore. They breathe."},
    "B":{"type":"monster","name":"Memory Chamber","desc":"The walls show scenes. Your scenes. Things you have not done yet.","monster_key":"shadow_lich"},
    "C":{"type":"guard","name":"Sealed Gallery","desc":"Crystal barriers. The constructs are pristine. And angry.","monster_key":"aeridorian_guardian"},
    "D":{"type":"trap","name":"The Maze of Glass","desc":"Transparent walls. You can see everything. You can reach nothing."},
    "E":{"type":"shrine","name":"Altar of the Core","desc":"A pedestal floating in anti-gravity."},
    "F":{"type":"monster","name":"Construct Graveyard","desc":"Failed experiments. Some of them are not entirely failed.","monster_key":"iron_golem"},
    "G":{"type":"antechamber","name":"The Anteroom","desc":"The door ahead has no handle. It opens when it decides to."},
    "H":{"type":"boss","name":"The Architect's Prison","desc":"It built the mountain. They buried it inside its own work.","monster_key":"the_bound_architect","boss_name":"The Bound Architect"},
}

def main():
    floors = {}
    configs = [
        (1,F1R,F1C,F1M,"The Working Tunnels",
         "Abandoned mine shafts. Timber supports creak. The lanterns are still lit."),
        (2,F2R,F2C,F2M,"The Bone Warrens",
         "Catacombs carved before the mine. The dead did not stay placed."),
        (3,F3R,F3C,F3M,"The Sunken Forge",
         "An Aeridorian forge buried by time. The fires still burn."),
        (4,F4R,F4C,F4M,"The Deep Dark",
         "Beyond the mine. Beyond the forge. Something older."),
        (5,F5R,F5C,F5M,"The Heart of the Mountain",
         "The deepest point. The mountain has a heartbeat."),
    ]
    for n,rms,corrs,meta,name,flav in configs:
        lines = place(rms, corrs)
        floor = build(lines, meta, name, flav)
        rm_count = len(set(r["label"] for r in floor["rooms"].values() if r.get("label")))
        print(f"Floor {n}: {rm_count} rooms, {len(floor['rooms'])} tiles")
        for i, line in enumerate(lines):
            print(f"  {i:2d} {line}")
        print()
        floors[str(n)] = floor
    with open("utils/ttrpg/spine_layouts.json", "w") as f:
        json.dump(floors, f, indent=2)
    print(f"Wrote spine_layouts.json")

if __name__ == "__main__":
    main()
