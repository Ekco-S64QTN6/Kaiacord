#!/usr/bin/env python3
"""Generate spine_layouts.json — 5 hand-crafted dungeon floors.
Large rooms (4x3), 2-wide corridors, unique layout per floor."""
import json, os, sys

GRID = 15

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
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch == '.': continue
            k = f"{x},{y}"
            if ch == '+':
                rooms[k] = {"type":"empty","cleared":True,"monster_key":None,
                    "boss_name":None,"description":"A narrow passage.",
                    "is_room":False,"label":None,"room_name":None}
            else:
                m = meta[ch]
                rooms[k] = {"type":m["type"],
                    "cleared":m["type"] in ("empty","stairs_up","stairs_down"),
                    "monster_key":m.get("monster_key"),"boss_name":m.get("boss_name"),
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
            if ch in meta:
                t = meta[ch]["type"]
                if t == "stairs_up" and not su: su = f"{x},{y}"
                elif t == "stairs_down" and not sd: sd = f"{x},{y}"
                elif t == "boss" and not bk: bk = f"{x},{y}"
    visited = set(); q = [su]
    while q:
        n = q.pop(0)
        if n in visited: continue
        visited.add(n)
        x,y = (int(v) for v in n.split(","))
        for dx,dy in [(0,-1),(0,1),(1,0),(-1,0)]:
            nb = f"{x+dx},{y+dy}"
            if nb in rooms and nb not in visited: q.append(nb)
    if set(rooms) - visited:
        print(f"FAIL {name}: {len(set(rooms)-visited)} unreachable"); sys.exit(1)
    return {"rooms":rooms,"connections":conns,"stairs_up_key":su,
        "stairs_down_key":sd,"boss_key":bk,"grid_size":GRID,
        "floor_name":name,"floor_flavor":flavor}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 1 — THE WORKING TUNNELS
# Entry top-left, winding path right then down, boss bottom-right.
#
#   AAAA--BBBB
#     |      |
#   CCCC  DDDD
#     |      |
#   EEEE--FFFF--GG
# ═══════════════════════════════════════════════════════════════════
F1R = [
    ('A', 1,1, 4,3),   ('B', 8,1, 4,3),
    ('C', 1,7, 4,3),   ('D', 8,7, 4,3),
    ('E', 1,13,4,1),   ('F', 8,13,4,1),
    ('G', 13,13,2,1),
]
F1C = [
    (5,2, 7,2), (5,3, 7,3),       # A─B horizontal
    (3,4, 3,6), (4,4, 4,6),       # A─C vertical
    (10,4, 10,6), (11,4, 11,6),   # B─D vertical
    (5,8, 7,8), (5,9, 7,9),       # C─D horizontal
    (3,10, 3,12), (4,10, 4,12),   # C─E vertical
    (10,10, 10,12), (11,10, 11,12), # D─F vertical
    (5,13, 7,13),                  # E─F horizontal
    (12,13, 12,13),                # F─G
]
F1M = {
    "A":{"type":"stairs_up","name":"Entry Hall","desc":"Daylight filters down the stairwell. The air smells of rust and old timber."},
    "B":{"type":"guard","name":"Guard Barracks","desc":"Overturned bunks. Someone fortified this recently.","monster_key":"bandit"},
    "C":{"type":"monster","name":"Ore Shaft","desc":"Pick marks line the walls. Something skitters in the dark.","monster_key":"bat"},
    "D":{"type":"shrine","name":"Mushroom Grotto","desc":"Bioluminescent fungi cast a faint blue glow. The air is warm."},
    "E":{"type":"stairs_down","name":"The Descent","desc":"A shaft drops into darkness. Cold air rises from below."},
    "F":{"type":"antechamber","name":"Foreman's Anteroom","desc":"A heavy iron door. Scratch marks on the inside."},
    "G":{"type":"boss","name":"Foreman's Office","desc":"Kregg is here. He didn't leave with the others.","monster_key":"foreman_kregg","boss_name":"Foreman Kregg"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 2 — THE BONE WARRENS
# Stairs top-right, L-shaped path, boss bottom-left.
#
#   BBBB--AAAA
#     |
#   CCCC--DDDD
#             |
#   GG--FFFF--EEEE
# ═══════════════════════════════════════════════════════════════════
F2R = [
    ('A', 8,1, 4,3),   ('B', 1,1, 4,3),
    ('C', 1,7, 4,3),   ('D', 8,7, 4,3),
    ('E', 8,13,4,1),   ('F', 4,13,3,1),
    ('G', 1,13,2,1),
]
F2C = [
    (5,2, 7,2), (5,3, 7,3),
    (3,4, 3,6), (4,4, 4,6),
    (5,8, 7,8), (5,9, 7,9),
    (10,10, 10,12), (11,10, 11,12),
    (7,13, 7,13),  # F─E
    (3,13, 3,13),  # G─F
]
F2M = {
    "A":{"type":"stairs_up","name":"Upper Landing","desc":"The shaft from the tunnels above. Wind moans through the gap."},
    "B":{"type":"monster","name":"Ossuary","desc":"Bones stacked floor to ceiling. Not all of them are staying put.","monster_key":"skeleton"},
    "C":{"type":"guard","name":"Crypt Gate","desc":"Iron bars across the passage. Something is locked in.","monster_key":"wight"},
    "D":{"type":"treasure","name":"Burial Offerings","desc":"Grave goods piled in alcoves. Gold dulled by centuries."},
    "E":{"type":"stairs_down","name":"The Deep Stair","desc":"Carved steps descend. The air tastes of copper and ozone."},
    "F":{"type":"antechamber","name":"Sealed Door","desc":"The door is warm. The carvings move when you look away."},
    "G":{"type":"boss","name":"The Unburied's Tomb","desc":"It was buried here. It dug itself out. It has been waiting.","monster_key":"the_unburied","boss_name":"The Unburied"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 3 — THE SUNKEN FORGE
# Stairs top-center, branching left/right, boss at bottom.
#
#       AAAA
#       |  |
#   BBBB  CCCC
#     |      |
#   DDDD  EEEE
#       |  |
#       FFFF
#         |
#        GG
# ═══════════════════════════════════════════════════════════════════
F3R = [
    ('A', 5,0, 4,2),
    ('B', 1,4, 4,3),  ('C', 9,4, 4,3),
    ('D', 1,9, 4,3),  ('E', 9,9, 4,3),
    ('F', 5,13,4,1),
    ('G', 6,14,2,1),
]
F3C = [
    (6,2, 6,3), (7,2, 7,3),     # A down-left to B area
    (8,2, 8,3), (8,4, 8,4),     # A down-right... need to connect
    # Actually let me connect A to both B and C
    (5,2, 5,3), (5,4, 5,4),     # A─B: col 5 rows 2-3, meets B at row 4
    (8,2, 8,3),                  # A─C: col 8 rows 2-3
    (9,3, 9,3),                  # connect to C
    (3,7, 3,8), (4,7, 4,8),     # B─D vertical
    (11,7, 11,8), (12,7, 12,8), # C─E vertical
    (5,12, 5,12), (6,12, 6,12), # D─F: need to bridge
    (8,12, 8,12), (9,12, 9,12), # E─F: need to bridge
]
# Hmm floor 3 is getting messy. Let me use the same proven 2-column grid
# but shift where stairs and boss go.
F3R = [
    ('A', 5,0, 4,2),   # stairs up — top center
    ('B', 1,3, 4,3),    ('C', 9,3, 4,3),
    ('D', 1,9, 4,3),    ('E', 9,9, 4,3),
    ('F', 5,13, 4,1),   # stairs down — bottom center
    ('G', 5,14, 2,1),   # boss — below stairs
]
F3C = [
    # A connects down to corridor that branches left and right
    (6,2, 6,2), (7,2, 7,2),       # A down
    (3,2, 5,2), (4,2, 4,2),       # branch left to B
    (8,2, 10,2), (9,2, 9,2),      # branch right to C
    (3,6, 3,8), (4,6, 4,8),       # B─D vertical
    (11,6, 11,8), (12,6, 12,8),   # C─E vertical
    (5,9, 8,9),                    # D─E horizontal bridge via F area
    (6,10, 6,12), (7,10, 7,12),   # center corridor down to F
]
F3M = {
    "A":{"type":"stairs_up","name":"Forge Entrance","desc":"Heat rises from below. The stone walls are warm to the touch."},
    "B":{"type":"monster","name":"Sentry Post","desc":"Two pedestals. The constructs on them are not decorative.","monster_key":"gargoyle"},
    "C":{"type":"monster","name":"Golem Bay","desc":"Storage alcoves for finished constructs. Not all are empty.","monster_key":"golem"},
    "D":{"type":"shrine","name":"Maker's Altar","desc":"An altar to whoever built this place. Offerings of metal and gem."},
    "E":{"type":"trap","name":"Steam Vents","desc":"Pipes run through the walls. Some of them burst on a timer."},
    "F":{"type":"stairs_down","name":"Thermal Shaft","desc":"A shaft descending along a magma channel. The heat is brutal."},
    "G":{"type":"boss","name":"Warden's Chamber","desc":"It was built to guard this forge. It has never stopped.","monster_key":"resonance_warden","boss_name":"Resonance Warden"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 4 — THE DEEP DARK
# Stairs bottom-left, boss top-right. Reverse direction.
#
#   DDDD--EEEE--GG
#     |      |
#   CCCC  FFFF
#     |
#   AAAA--BBBB
# ═══════════════════════════════════════════════════════════════════
F4R = [
    ('A', 1,11, 4,3),  ('B', 8,11, 4,3),
    ('C', 1,5, 4,3),   ('F', 8,5, 4,3),
    ('D', 1,1, 4,3),   ('E', 8,1, 4,3),
    ('G', 13,1, 2,2),
]
F4C = [
    (5,12, 7,12), (5,13, 7,13),   # A─B horizontal
    (3,8, 3,10), (4,8, 4,10),     # C─A vertical
    (5,6, 7,6), (5,7, 7,7),       # C─F horizontal
    (3,4, 3,4), (4,4, 4,4),       # C─D vertical
    (10,4, 10,4), (11,4, 11,4),   # F─E vertical
    (5,2, 7,2), (5,3, 7,3),       # D─E horizontal
    (12,1, 12,1), (12,2, 12,2),   # E─G
]
F4M = {
    "A":{"type":"stairs_up","name":"Breach Point","desc":"The mine wall was broken through. Whatever is beyond was not meant to be found."},
    "B":{"type":"monster","name":"Thought Eater Den","desc":"Your memories itch. Something is browsing them.","monster_key":"mind_flayer"},
    "C":{"type":"monster","name":"Echo Chamber","desc":"Sound behaves wrong here. Your voice comes back different.","monster_key":"dark_knight"},
    "D":{"type":"treasure","name":"Crystal Geode","desc":"A natural geode cracked open. Gems spill from the wound."},
    "E":{"type":"antechamber","name":"The Last Camp","desc":"Bedrolls. Cold rations. The last journal entry is just the word 'watching.'"},
    "F":{"type":"shrine","name":"Void Shrine","desc":"An altar to nothing. The space above it is empty in a way space should not be."},
    "G":{"type":"boss","name":"The Last of the Party","desc":"It used to be an adventurer. Now it remembers being one.","monster_key":"the_last_of_the_party","boss_name":"The Last of the Party"},
}

# ═══════════════════════════════════════════════════════════════════
# FLOOR 5 — THE HEART OF THE MOUNTAIN
# Same structure as F1 but no stairs_down (final floor).
# ═══════════════════════════════════════════════════════════════════
F5R = [
    ('A', 1,1, 4,3),   ('B', 8,1, 4,3),
    ('C', 1,7, 4,3),   ('D', 8,7, 4,3),
    ('E', 1,12, 4,2),  ('F', 8,12, 4,2),
    ('G', 13,12, 2,2),
]
F5C = [
    (5,2, 7,2), (5,3, 7,3),
    (3,4, 3,6), (4,4, 4,6),
    (10,4, 10,6), (11,4, 11,6),
    (5,8, 7,8), (5,9, 7,9),
    (3,10, 3,11), (4,10, 4,11),
    (10,10, 10,11), (11,10, 11,11),
    (5,12, 7,12), (5,13, 7,13),
    (12,12, 12,12), (12,13, 12,13),
]
F5M = {
    "A":{"type":"stairs_up","name":"The Threshold","desc":"The stairs end. The walls are not rock anymore. They breathe."},
    "B":{"type":"monster","name":"Memory Chamber","desc":"The walls show scenes. Your scenes. Things you have not done yet.","monster_key":"shadow_lich"},
    "C":{"type":"guard","name":"Sealed Gallery","desc":"Crystal barriers. The constructs are pristine. And angry.","monster_key":"aeridorian_guardian"},
    "D":{"type":"trap","name":"The Maze of Glass","desc":"Transparent walls. You can see everything. You can reach nothing."},
    "E":{"type":"monster","name":"Construct Graveyard","desc":"Failed experiments. Some of them are not entirely failed.","monster_key":"iron_golem"},
    "F":{"type":"antechamber","name":"The Anteroom","desc":"The door ahead has no handle. It opens when it decides to."},
    "G":{"type":"boss","name":"The Architect's Prison","desc":"It built the mountain. They buried it inside its own work.","monster_key":"the_bound_architect","boss_name":"The Bound Architect"},
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
