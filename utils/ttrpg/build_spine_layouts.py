#!/usr/bin/env python3
"""
Hand-crafted Spine of the World mega-dungeon layout builder.
Generates spine_layouts.json with 5 D&D-style dungeon floors.

Run: python3 utils/ttrpg/build_spine_layouts.py
"""
import json, os, sys

GRID = 15

def place_rooms_and_corridors(room_placements, corridor_segments, size=GRID):
    grid = [['.' for _ in range(size)] for _ in range(size)]
    for label, rx, ry, rw, rh in room_placements:
        for dy in range(rh):
            for dx in range(rw):
                grid[ry+dy][rx+dx] = label
    for x1, y1, x2, y2 in corridor_segments:
        if x1 == x2:
            for y in range(min(y1,y2), max(y1,y2)+1):
                if grid[y][x1] == '.': grid[y][x1] = '+'
        elif y1 == y2:
            for x in range(min(x1,x2), max(x1,x2)+1):
                if grid[y1][x] == '.': grid[y1][x] = '+'
    return [''.join(row) for row in grid]

def build_floor(ascii_lines, room_meta, floor_name, floor_flavor):
    rooms = {}
    for y, line in enumerate(ascii_lines):
        for x, ch in enumerate(line):
            if ch == '.': continue
            key = f"{x},{y}"
            if ch == '+':
                rooms[key] = {"type":"empty","cleared":True,"monster_key":None,
                    "boss_name":None,"description":"A narrow passage.",
                    "is_room":False,"label":None,"room_name":None}
            else:
                m = room_meta[ch]
                rooms[key] = {"type":m["type"],
                    "cleared":m["type"] in ("empty","stairs_up","stairs_down"),
                    "monster_key":m.get("monster_key"),"boss_name":m.get("boss_name"),
                    "description":m.get("desc",""),"is_room":True,
                    "label":ch,"room_name":m.get("name","")}
    conns = {}
    dirs = {"N":(0,-1),"S":(0,1),"E":(1,0),"W":(-1,0)}
    for key in rooms:
        x,y = (int(v) for v in key.split(","))
        conns[key] = [d for d,(dx,dy) in dirs.items() if f"{x+dx},{y+dy}" in rooms]
    stairs_up = stairs_down = boss_key = None
    for y, line in enumerate(ascii_lines):
        for x, ch in enumerate(line):
            if ch in room_meta:
                t = room_meta[ch]["type"]
                if t == "stairs_up" and not stairs_up: stairs_up = f"{x},{y}"
                elif t == "stairs_down" and not stairs_down: stairs_down = f"{x},{y}"
                elif t == "boss" and not boss_key: boss_key = f"{x},{y}"
    # Connectivity check
    if stairs_up:
        visited = set(); queue = [stairs_up]
        while queue:
            node = queue.pop(0)
            if node in visited: continue
            visited.add(node)
            x,y = (int(v) for v in node.split(","))
            for dx,dy in [(0,-1),(0,1),(1,0),(-1,0)]:
                nb = f"{x+dx},{y+dy}"
                if nb in rooms and nb not in visited: queue.append(nb)
        unr = set(rooms.keys()) - visited
        if unr:
            print(f"ERROR: {len(unr)} unreachable tiles in {floor_name}")
            sys.exit(1)
    return {"rooms":rooms,"connections":conns,"stairs_up_key":stairs_up,
        "stairs_down_key":stairs_down,"boss_key":boss_key,
        "grid_size":GRID,"floor_name":floor_name,"floor_flavor":floor_flavor}

# ═══════════ FLOOR 1 — THE WORKING TUNNELS ═══════════
F1_ROOMS = [
    ('A',1,0,3,2),('B',9,0,2,2),('C',1,4,2,2),('D',5,4,2,2),
    ('E',9,4,2,2),('F',1,8,2,2),('G',5,8,2,2),('H',9,8,2,2),
    ('I',1,12,2,2),('K',5,12,2,2),('L',9,11,2,2),('N',12,11,2,1),
    ('M',9,13,2,1),('J',12,13,1,2),
]
F1_CORR = [
    (4,0,8,0),(2,2,2,3),(10,2,10,3),(3,4,4,4),(7,4,8,4),
    (2,6,2,7),(6,6,6,7),(10,6,10,7),(3,8,4,8),(7,8,8,8),
    (2,10,2,11),(6,10,6,11),(10,10,10,10),(3,12,4,12),
    (7,12,8,12),(11,12,12,12),(11,13,12,13),
]
F1_META = {
    "A":{"type":"stairs_up","name":"Entry Hall","desc":"Daylight filters down the stairwell. The air smells of rust and old timber."},
    "B":{"type":"guard","name":"Guard Barracks","desc":"Overturned bunks. Someone fortified this recently.","monster_key":"bandit"},
    "C":{"type":"monster","name":"Ore Shaft","desc":"Pick marks line the walls. Something skitters in the dark.","monster_key":"bat"},
    "D":{"type":"treasure","name":"Tool Cache","desc":"Rusted tools hang from pegs. A locked chest sits in the corner."},
    "E":{"type":"shrine","name":"Mushroom Grotto","desc":"Bioluminescent fungi cast a faint blue glow. The air is warm."},
    "F":{"type":"monster","name":"Mine Office","desc":"A desk, a chair, a lantern. The chair is still warm.","monster_key":"bandit"},
    "G":{"type":"trap","name":"Unstable Chamber","desc":"The ceiling sags. Timber supports are cracked and bowing."},
    "H":{"type":"monster","name":"Water Cave","desc":"Groundwater pools on the floor. Echoes distort everything.","monster_key":"bat"},
    "I":{"type":"guard","name":"Chokepoint","desc":"A barricade of mine carts and planks blocks the way.","monster_key":"soldier"},
    "J":{"type":"stairs_down","name":"The Descent","desc":"A shaft drops into darkness. Cold air rises from below."},
    "K":{"type":"monster","name":"Lantern Alcove","desc":"Whale-oil lanterns still burn. Who is filling them?","monster_key":"bandit"},
    "L":{"type":"treasure","name":"Collapsed Seam","desc":"A cave-in exposed a vein of raw crystal. Fragments litter the floor."},
    "M":{"type":"antechamber","name":"Foreman's Anteroom","desc":"A heavy iron door. Scratch marks on the inside."},
    "N":{"type":"boss","name":"Foreman's Office","desc":"Kregg is here. He didn't leave with the others.","monster_key":"foreman_kregg","boss_name":"Foreman Kregg"},
}

# ═══════════ FLOOR 2 — THE BONE WARRENS ═══════════
F2_ROOMS = [
    ('A',1,0,2,2),('B',5,0,2,2),('C',9,0,2,2),('D',1,4,2,2),
    ('E',5,4,2,2),('F',9,4,2,2),('G',1,8,2,2),('H',5,8,2,2),
    ('I',9,8,2,2),('J',1,12,2,2),('K',5,12,2,2),('L',9,12,2,2),
    ('M',12,13,1,2),('N',13,13,1,2),
]
F2_CORR = [
    (3,0,4,0),(7,0,8,0),(3,4,4,4),(7,4,8,4),(3,8,4,8),(7,8,8,8),
    (3,12,4,12),(7,12,8,12),(11,13,12,13),
    (2,2,2,3),(6,2,6,3),(10,2,10,3),(2,6,2,7),(6,6,6,7),
    (10,6,10,7),(2,10,2,11),(6,10,6,11),(10,10,10,11),
]
F2_META = {
    "A":{"type":"stairs_up","name":"Upper Landing","desc":"The shaft from the tunnels above. Wind moans through the gap."},
    "B":{"type":"monster","name":"Ossuary","desc":"Bones stacked floor to ceiling. Not all of them are staying put.","monster_key":"skeleton"},
    "C":{"type":"monster","name":"Embalming Room","desc":"Stone tables. Drainage channels. The smell never left.","monster_key":"zombie"},
    "D":{"type":"guard","name":"Crypt Gate","desc":"Iron bars. Something is locked in. Or locked out.","monster_key":"wight"},
    "E":{"type":"treasure","name":"Burial Offerings","desc":"Grave goods piled in alcoves. Gold dulled by centuries."},
    "F":{"type":"monster","name":"Mass Grave","desc":"They ran out of individual plots. It did not matter.","monster_key":"ghoul"},
    "G":{"type":"trap","name":"Collapsing Crypt","desc":"The floor is thin. Something hollow is beneath."},
    "H":{"type":"shrine","name":"Mourner's Chapel","desc":"Candles that should not still be burning. A stone figure kneels."},
    "I":{"type":"monster","name":"Wight's Crossing","desc":"An intersection. The walls are clawed. Deeply.","monster_key":"wight"},
    "J":{"type":"monster","name":"Revenant's Walk","desc":"A long hall. Something paces at the far end.","monster_key":"revenant"},
    "K":{"type":"monster","name":"Bone Pit","desc":"A sunken chamber. The bones are arranged deliberately.","monster_key":"skeleton"},
    "L":{"type":"antechamber","name":"Sealed Door","desc":"The door is warm. The carvings move when you look away."},
    "M":{"type":"stairs_down","name":"The Deep Stair","desc":"Carved steps descend. The air tastes of copper and ozone."},
    "N":{"type":"boss","name":"The Unburied's Tomb","desc":"It was buried here. It dug itself out. It has been waiting.","monster_key":"the_unburied","boss_name":"The Unburied"},
}

# ═══════════ FLOOR 3 — THE SUNKEN FORGE ═══════════
F3_ROOMS = [
    ('A',1,0,2,2),('B',5,0,3,2),('C',11,0,2,2),('D',1,4,2,2),
    ('E',5,4,2,2),('F',1,8,2,2),('G',5,7,2,2),('H',9,7,2,2),
    ('I',1,12,2,2),('J',5,12,2,2),('K',9,11,2,2),('N',12,11,2,1),
    ('L',12,13,1,1),('M',13,13,1,1),
]
F3_CORR = [
    (3,0,4,0),(8,0,10,0),(3,4,4,4),(2,2,2,3),(6,2,6,3),
    (10,2,10,6),(2,6,2,7),(6,6,6,6),(7,7,8,7),(2,10,2,11),
    (6,9,6,11),(7,12,9,12),(11,11,11,12),(11,12,12,12),(12,12,12,13),
]
F3_META = {
    "A":{"type":"stairs_up","name":"Forge Entrance","desc":"Heat rises from below. The stone walls are warm to the touch."},
    "B":{"type":"monster","name":"Sentry Post","desc":"Two pedestals. The constructs on them are not decorative.","monster_key":"gargoyle"},
    "C":{"type":"treasure","name":"Ingot Vault","desc":"Metal bars stacked in racks. Some glow faintly."},
    "D":{"type":"monster","name":"Assembly Hall","desc":"Half-built constructs on workbenches. One of them twitches.","monster_key":"golem"},
    "E":{"type":"guard","name":"Crystal Ward","desc":"Crystals pulse with light. A guardian stands watch.","monster_key":"crystelle"},
    "F":{"type":"monster","name":"The Great Forge","desc":"An anvil the size of a cart. The forge fire still burns blue.","monster_key":"soldier"},
    "G":{"type":"trap","name":"Steam Vents","desc":"Pipes run through the walls. Some of them burst on a timer."},
    "H":{"type":"monster","name":"Golem Bay","desc":"Storage alcoves for finished constructs. Not all are empty.","monster_key":"golem"},
    "I":{"type":"shrine","name":"Maker's Altar","desc":"An altar to whoever built this place. Offerings of metal and gem."},
    "J":{"type":"monster","name":"Cooling Chamber","desc":"Water channels cut through stone. The constructs come here.","monster_key":"crystelle"},
    "K":{"type":"monster","name":"Control Room","desc":"Levers. Dials. Readouts in a language nobody speaks.","monster_key":"gargoyle"},
    "L":{"type":"stairs_down","name":"Thermal Shaft","desc":"A shaft descending along a magma channel. The heat is brutal."},
    "M":{"type":"boss","name":"Warden's Chamber","desc":"It was built to guard this forge. It has never stopped.","monster_key":"resonance_warden","boss_name":"Resonance Warden"},
    "N":{"type":"treasure","name":"Prototype Vault","desc":"Weapons and armor never shipped. Aeridorian craft at its finest."},
}

# ═══════════ FLOOR 4 — THE DEEP DARK ═══════════
F4_ROOMS = [
    ('A',6,0,2,2),('B',1,2,3,2),('C',10,2,2,2),('D',1,6,2,2),
    ('E',6,5,2,2),('F',10,5,2,2),('G',1,10,2,2),('H',6,9,2,2),
    ('I',10,9,2,2),('J',1,13,1,1),('K',2,13,1,1),
    ('L',6,13,2,1),('M',10,13,2,1),
]
F4_CORR = [
    (4,2,6,2),(7,2,9,2),(2,4,2,5),(7,2,7,4),(11,4,11,4),
    (2,8,2,9),(7,7,7,8),(11,7,11,8),(3,10,5,10),(8,10,9,10),
    (2,12,2,12),(7,11,7,12),(11,11,11,12),
]
F4_META = {
    "A":{"type":"stairs_up","name":"Breach Point","desc":"The mine wall was broken through. Whatever is beyond was not meant to be found."},
    "B":{"type":"monster","name":"Aberrant Gallery","desc":"The walls are covered in organic growth. It pulses.","monster_key":"mind_flayer"},
    "C":{"type":"guard","name":"Sentinel Arch","desc":"A stone archway. The carvings depict things watching.","monster_key":"spectral_knight"},
    "D":{"type":"monster","name":"Echo Chamber","desc":"Sound behaves wrong here. Your voice comes back different.","monster_key":"dark_knight"},
    "E":{"type":"treasure","name":"Crystal Geode","desc":"A natural geode cracked open. Gems spill from the wound."},
    "F":{"type":"trap","name":"Gravity Well","desc":"The floor slopes toward the center. Something pulls."},
    "G":{"type":"monster","name":"The Watching Room","desc":"Eyes. In the walls. They track you. They blink.","monster_key":"beholder"},
    "H":{"type":"monster","name":"Thought Eater Den","desc":"Your memories itch. Something is browsing them.","monster_key":"mind_flayer"},
    "I":{"type":"shrine","name":"Void Shrine","desc":"An altar to nothing. The space above it is empty in a way space should not be."},
    "J":{"type":"stairs_down","name":"The Final Descent","desc":"Below this, the stone stops being stone."},
    "K":{"type":"boss","name":"The Last of the Party","desc":"It used to be an adventurer. Now it remembers being one.","monster_key":"the_last_of_the_party","boss_name":"The Last of the Party"},
    "L":{"type":"antechamber","name":"The Last Camp","desc":"Bedrolls. Cold rations. A journal. The last entry is just the word 'watching' written smaller and smaller."},
    "M":{"type":"treasure","name":"Lost Expedition","desc":"Supplies from the last team. They did not need them anymore."},
}

# ═══════════ FLOOR 5 — THE HEART OF THE MOUNTAIN ═══════════
F5_ROOMS = [
    ('A',6,0,2,2),('B',1,2,2,2),('C',11,2,2,2),('D',1,6,2,2),
    ('E',5,6,3,2),('F',11,6,2,2),('G',1,10,2,2),('H',5,10,2,2),
    ('I',9,10,2,2),('J',5,13,2,1),('K',9,13,2,1),
    ('L',12,14,1,1),('M',13,14,1,1),
]
F5_CORR = [
    (3,2,5,2),(8,2,10,2),(2,4,2,5),(7,2,7,5),(12,4,12,5),
    (3,6,4,6),(8,6,10,6),(2,8,2,9),(6,8,6,9),(10,8,10,9),
    (3,10,4,10),(7,10,8,10),(6,12,6,12),(10,12,10,12),
    (7,13,8,13),(11,13,12,13),(12,13,12,14),
]
F5_META = {
    "A":{"type":"stairs_up","name":"The Threshold","desc":"The stairs end. The walls are not rock anymore. They breathe."},
    "B":{"type":"monster","name":"Warden's Post","desc":"Something was posted here to keep people out. It failed upward.","monster_key":"iron_golem"},
    "C":{"type":"monster","name":"Memory Chamber","desc":"The walls show scenes. Your scenes. Things you have not done yet.","monster_key":"shadow_lich"},
    "D":{"type":"guard","name":"Sealed Gallery","desc":"Crystal barriers. The constructs behind them are pristine. And angry.","monster_key":"aeridorian_guardian"},
    "E":{"type":"monster","name":"The Crucible","desc":"A vast chamber. The floor is glass over magma. Something moves beneath.","monster_key":"death_tyrant"},
    "F":{"type":"treasure","name":"Architect's Study","desc":"Blueprints for things that should not exist. Tools made of light."},
    "G":{"type":"monster","name":"Binding Chamber","desc":"Chains made of crystal. Most of them are broken.","monster_key":"vampire_lord"},
    "H":{"type":"trap","name":"The Maze of Glass","desc":"Transparent walls. You can see everything. You can reach nothing."},
    "I":{"type":"shrine","name":"The Quiet Place","desc":"The only room where the mountain does not hum. It feels wrong."},
    "J":{"type":"monster","name":"Construct Graveyard","desc":"Failed experiments. Some of them are not entirely failed.","monster_key":"iron_golem"},
    "K":{"type":"antechamber","name":"The Anteroom","desc":"The door ahead has no handle. It opens when it decides to."},
    "L":{"type":"boss","name":"The Architect's Prison","desc":"It built the mountain. They buried it inside its own work. It wants out.","monster_key":"the_bound_architect","boss_name":"The Bound Architect"},
    "M":{"type":"empty","name":"The Core","desc":"Behind the Architect. The mountain's heart. Pulsing. Alive. Grateful."},
}

def main():
    floors = {}
    configs = [
        (1, F1_ROOMS, F1_CORR, F1_META, "The Working Tunnels",
         "Abandoned mine shafts. Timber supports creak. Someone was here recently — the lanterns are still lit."),
        (2, F2_ROOMS, F2_CORR, F2_META, "The Bone Warrens",
         "Catacombs carved before the mine. The dead were placed carefully. They did not stay placed."),
        (3, F3_ROOMS, F3_CORR, F3_META, "The Sunken Forge",
         "An Aeridorian forge buried by time. The fires still burn. The constructs still follow orders."),
        (4, F4_ROOMS, F4_CORR, F4_META, "The Deep Dark",
         "Beyond the mine. Beyond the forge. Something older. Something that was always here."),
        (5, F5_ROOMS, F5_CORR, F5_META, "The Heart of the Mountain",
         "The deepest point. The mountain has a heartbeat. The Architect is waiting."),
    ]
    for fnum, rms, corrs, meta, name, flavor in configs:
        lines = place_rooms_and_corridors(rms, corrs)
        floor = build_floor(lines, meta, name, flavor)
        named = sum(1 for r in floor["rooms"].values() if r.get("is_room"))
        corridors = sum(1 for r in floor["rooms"].values() if not r.get("is_room"))
        labels = set(r["label"] for r in floor["rooms"].values() if r.get("label"))
        print(f"Floor {fnum}: {len(labels)} rooms, {named} room tiles, {corridors} corridors, {len(floor['rooms'])} total")
        floors[str(fnum)] = floor

    out_path = "utils/ttrpg/spine_layouts.json"
    with open(out_path, "w") as f:
        json.dump(floors, f, indent=2)
    print(f"\nWrote {out_path} ({os.path.getsize(out_path)} bytes)")

if __name__ == "__main__":
    main()
