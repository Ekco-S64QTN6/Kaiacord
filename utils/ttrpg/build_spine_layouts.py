#!/usr/bin/env python3
"""Generate spine_layouts.json — 77 Spine of the World dungeon floors.

Each floor uses one of 5 hand-crafted room templates, but monster_key values
are randomized per-room from the zone's encounter pool in ENCOUNTER_TABLES.
This ensures every floor has a unique set of creatures.
"""
import json, os, sys, secrets

GRID = 24

# ── Zone encounter pools (floor_num → zone_key mapping) ───────────────────────
FLOOR_ZONE_MAP = {
    range(1, 16):  "working_tunnels",
    range(16, 31): "bone_warrens",
    range(31, 46): "sunken_forge",
    range(46, 61): "deep_dark",
    range(61, 78): "heart_of_mountain",
}

def _get_zone_key(floor_num: int) -> str:
    for rng, zone in FLOOR_ZONE_MAP.items():
        if floor_num in rng:
            return zone
    return "working_tunnels"

def _generate_floor_pool(floor_num: int) -> list:
    """Generate a unique encounter pool for a specific floor.
    Combines the zone's thematic pool with 15 random monsters from the
    ENTIRE registry that match the floor's difficulty tier.
    Returns list of (monster_key, weight) tuples."""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        exec_globals = {}
        registry_path = os.path.join(project_root, 'utils', 'ttrpg', 'monster_registry.py')
        exec(open(registry_path).read(), exec_globals)
        monsters = exec_globals.get('MONSTERS', {})
        tables = exec_globals.get('ENCOUNTER_TABLES', {})

        # Determine allowed tiers for this floor depth
        if floor_num <= 10: allowed_tiers = ["easy", "medium"]
        elif floor_num <= 30: allowed_tiers = ["medium", "hard"]
        elif floor_num <= 50: allowed_tiers = ["hard", "deadly"]
        else: allowed_tiers = ["deadly"]

        # Get all valid non-boss monsters from the entire registry matching tier
        valid_monsters = []
        for mk, m_data in monsters.items():
            if m_data.get("tier") in allowed_tiers and not m_data.get("is_boss"):
                valid_monsters.append(mk)

        # Include the zone's thematic pool to ensure flavor
        zone_key = _get_zone_key(floor_num)
        zone_pool = [k for k, w in tables.get('spine_of_the_world', {}).get(zone_key, [])]

        import random
        random.shuffle(valid_monsters)
        # Combine the zone pool with 15 random tier-appropriate monsters from anywhere
        floor_pool_keys = list(set(valid_monsters[:15] + zone_pool))

        # Assign equal weights to all
        return [(k, 10) for k in floor_pool_keys]
    except Exception as e:
        print(f"WARNING: Could not generate floor pool: {e}")
        return [("goblin", 10)]

def _pick_from_pool(pool: list) -> str:
    """Weighted random pick from a [(key, weight), ...] pool."""
    if not pool:
        return "goblin"  # fallback
    total = sum(w for _, w in pool)
    r = secrets.randbelow(total)
    cum = 0
    for key, w in pool:
        cum += w
        if r < cum:
            return key
    return pool[0][0]

def _transform_layout(rooms_list, corrs_list, flip_x, flip_y, transpose, size=GRID):
    """Apply geometric transformations to create layout variations."""
    new_rooms = []
    new_corrs = []
    for label, rx, ry, rw, rh in rooms_list:
        if transpose:
            rx, ry, rw, rh = ry, rx, rh, rw
        if flip_x:
            rx = size - rx - rw
        if flip_y:
            ry = size - ry - rh
        new_rooms.append((label, rx, ry, rw, rh))
        
    for x1, y1, x2, y2 in corrs_list:
        if transpose:
            x1, y1, x2, y2 = y1, x1, y2, x2
        if flip_x:
            x1, x2 = size - 1 - x1, size - 1 - x2
        if flip_y:
            y1, y2 = size - 1 - y1, size - 1 - y2
        new_corrs.append((x1, y1, x2, y2))
        
    return new_rooms, new_corrs

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

def build(lines, meta, name, flavor, zone_pool=None):
    """Build a floor dict from grid lines and room metadata.
    If zone_pool is provided, combat rooms get a random monster_key from
    the pool instead of the hardcoded template value."""
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
                    bn = m.get("boss_name")
                    cl = rt in ("empty","stairs_up","stairs_down")
                    # Randomize monster_key from zone pool for combat rooms
                    if rt in ("monster", "guard") and zone_pool:
                        mk = _pick_from_pool(zone_pool)
                    else:
                        mk = m.get("monster_key")
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
# FLOOR 1
F1R = [
    ('A', 8, 20, 2, 2),
    ('B', 8, 16, 3, 3),
    ('C', 4, 16, 3, 3),
    ('D', 12, 16, 2, 3),
    ('E', 8, 12, 3, 3),
    ('F', 8, 8, 3, 3),
    ('G', 4, 8, 3, 3),
    ('H', 12, 8, 3, 3),
    ('I', 8, 4, 3, 3),
    ('J', 4, 4, 3, 2),
    ('K', 12, 4, 2, 3),
    ('L', 8, 0, 3, 3),
    ('M', 4, 0, 3, 3),
    ('N', 0, 8, 2, 3),
    ('O', 16, 8, 3, 3)
]
F1C = [
    (8, 19, 8, 19),
    (7, 17, 7, 17),
    (11, 17, 11, 17),
    (9, 15, 9, 15),
    (9, 11, 9, 11),
    (7, 9, 7, 9),
    (11, 9, 11, 9),
    (9, 7, 9, 7),
    (7, 4, 7, 4),
    (11, 5, 11, 5),
    (9, 3, 9, 3),
    (7, 1, 7, 1),
    (2, 9, 3, 9),
    (15, 9, 15, 9)
]

F2R = [
    ('A', 16, 0, 2, 2),
    ('B', 16, 4, 3, 3),
    ('C', 12, 4, 3, 3),
    ('D', 12, 8, 3, 3),
    ('E', 8, 8, 3, 3),
    ('F', 8, 12, 3, 3),
    ('G', 4, 12, 3, 3),
    ('H', 4, 8, 3, 2),
    ('I', 4, 16, 3, 3),
    ('J', 0, 16, 2, 3),
    ('K', 8, 16, 3, 3),
    ('L', 8, 20, 3, 2),
    ('M', 12, 12, 2, 3),
    ('N', 16, 8, 3, 3),
    ('O', 20, 4, 2, 3),
    ('P', 0, 12, 2, 2),
    ('Q', 12, 20, 3, 3),
    ('R', 0, 20, 3, 3)
]
F2C = [
    (16, 2, 16, 3),
    (15, 5, 15, 5),
    (13, 7, 13, 7),
    (11, 9, 11, 9),
    (9, 11, 9, 11),
    (7, 13, 7, 13),
    (5, 10, 5, 11),
    (5, 15, 5, 15),
    (2, 17, 3, 17),
    (9, 15, 9, 15),
    (9, 19, 9, 19),
    (12, 11, 12, 11),
    (15, 9, 15, 9),
    (19, 5, 19, 5),
    (2, 12, 3, 12),
    (11, 20, 11, 20),
    (0, 19, 0, 19)
]

F3R = [
    ('A', 20, 20, 2, 2),
    ('B', 16, 20, 3, 3),
    ('C', 12, 20, 3, 3),
    ('D', 8, 20, 3, 3),
    ('E', 4, 20, 3, 3),
    ('F', 4, 16, 3, 3),
    ('G', 4, 12, 3, 3),
    ('H', 4, 8, 3, 3),
    ('I', 8, 8, 3, 3),
    ('J', 12, 8, 3, 3),
    ('K', 16, 8, 3, 3),
    ('L', 16, 12, 3, 3),
    ('M', 12, 12, 2, 3),
    ('N', 4, 4, 3, 2),
    ('O', 8, 4, 3, 3),
    ('P', 12, 4, 3, 3),
    ('Q', 0, 12, 2, 2)
]
F3C = [
    (19, 20, 19, 20),
    (15, 21, 15, 21),
    (11, 21, 11, 21),
    (7, 21, 7, 21),
    (5, 19, 5, 19),
    (5, 15, 5, 15),
    (5, 11, 5, 11),
    (7, 9, 7, 9),
    (11, 9, 11, 9),
    (15, 9, 15, 9),
    (17, 11, 17, 11),
    (12, 11, 12, 11),
    (5, 6, 5, 7),
    (9, 7, 9, 7),
    (11, 5, 11, 5),
    (2, 12, 3, 12)
]

F4R = [
    ('A', 8, 0, 2, 2),
    ('B', 8, 4, 3, 3),
    ('C', 4, 4, 3, 3),
    ('D', 12, 4, 3, 3),
    ('E', 8, 8, 3, 3),
    ('F', 4, 8, 3, 3),
    ('G', 0, 8, 2, 3),
    ('H', 12, 8, 3, 3),
    ('I', 16, 8, 3, 3),
    ('J', 8, 12, 3, 3),
    ('K', 4, 12, 3, 3),
    ('L', 12, 12, 3, 3),
    ('M', 8, 16, 3, 3),
    ('N', 4, 16, 3, 2),
    ('O', 12, 16, 2, 3),
    ('P', 16, 12, 3, 3),
    ('Q', 0, 12, 3, 3),
    ('R', 8, 20, 3, 3),
    ('S', 16, 16, 3, 3)
]
F4C = [
    (8, 2, 8, 3),
    (7, 5, 7, 5),
    (11, 5, 11, 5),
    (9, 7, 9, 7),
    (7, 9, 7, 9),
    (2, 9, 3, 9),
    (11, 9, 11, 9),
    (15, 9, 15, 9),
    (9, 11, 9, 11),
    (7, 13, 7, 13),
    (11, 13, 11, 13),
    (9, 15, 9, 15),
    (7, 16, 7, 16),
    (11, 17, 11, 17),
    (15, 13, 15, 13),
    (3, 13, 3, 13),
    (9, 19, 9, 19),
    (14, 17, 15, 17)
]

F5R = [
    ('A', 8, 20, 2, 2),
    ('B', 8, 16, 3, 3),
    ('C', 4, 16, 3, 3),
    ('D', 12, 16, 3, 3),
    ('E', 8, 12, 3, 3),
    ('F', 4, 12, 3, 2),
    ('G', 12, 12, 3, 3),
    ('H', 8, 8, 3, 3),
    ('I', 4, 8, 3, 3),
    ('J', 12, 8, 2, 3),
    ('K', 8, 4, 3, 3),
    ('L', 4, 4, 3, 3),
    ('M', 12, 4, 3, 3),
    ('N', 8, 0, 3, 3),
    ('O', 4, 0, 2, 3),
    ('P', 12, 0, 3, 3)
]
F5C = [
    (8, 19, 8, 19),
    (7, 17, 7, 17),
    (11, 17, 11, 17),
    (9, 15, 9, 15),
    (7, 12, 7, 12),
    (11, 13, 11, 13),
    (9, 11, 9, 11),
    (7, 9, 7, 9),
    (11, 9, 11, 9),
    (9, 7, 9, 7),
    (7, 5, 7, 5),
    (11, 5, 11, 5),
    (9, 3, 9, 3),
    (6, 1, 7, 1),
    (11, 1, 11, 1)
]


F1M = {
    "A":{"type":"stairs_up","name":"Entry Hall","desc":"A cool draft blows from the stairs leading up toward the surface. The air smells of rust and old timber."},
    "B":{"type":"empty","name":"Wide Chamber","desc":"A junction of old mine tunnels."},
    "C":{"type":"monster","name":"Ore Shaft","desc":"Pick marks line the walls. Something skitters in the dark.","monster_key":"manticore"},
    "D":{"type":"empty","name":"Collapsed Tunnel","desc":"The ceiling has caved in here. Dust still settles."},
    "E":{"type":"guard","name":"Central Hub","desc":"Rusted minecarts tipped over as barricades.","monster_key":"iron_golem"},
    "F":{"type":"monster","name":"Flooded Chamber","desc":"Water drips from the ceiling. A dark pool covers the floor.","monster_key":"hydra"},
    "G":{"type":"treasure","name":"Foreman's Stash","desc":"A locked strongbox hidden under rotted planks."},
    "H":{"type":"monster","name":"Guard Barracks","desc":"Overturned bunks. Someone fortified this recently.","monster_key":"dark_rider"},
    "I":{"type":"stairs_down","name":"The Descent","desc":"A shaft drops into darkness. Cold air rises from below."},
    "J":{"type":"empty","name":"Tool Closet","desc":"Rusted pickaxes and frayed rope."},
    "K":{"type":"shrine","name":"Mushroom Grotto","desc":"Bioluminescent fungi cast a faint blue glow."},
    "L":{"type":"monster","name":"Rest Area","desc":"A makeshift camp. Something took up residence.","monster_key":"bone_devil"},
    "M":{"type":"monster","name":"Side Cavern","desc":"Bones line the floor.","monster_key":"dark_rider"},
    "N":{"type":"monster","name":"Side Cavern","desc":"Dripping water. Claw marks.","monster_key":"iron_golem"},
    "O":{"type":"guard","name":"Foreman's Office","desc":"Kregg's old office. Smashed furniture and dried blood.","monster_key":"dark_rider"}
}

F2M = {
    "A":{"type":"stairs_up","name":"Upper Landing","desc":"The shaft from the tunnels above. Wind moans through the gap."},
    "B":{"type":"empty","name":"Dusty Hall","desc":"Urns line the walls. Most are smashed."},
    "C":{"type":"guard","name":"Crypt Gate","desc":"Iron bars across the passage. Something is locked in.","monster_key":"death_tyrant"},
    "D":{"type":"monster","name":"Ossuary","desc":"Bones stacked floor to ceiling. Not all staying put.","monster_key":"bone_devil"},
    "E":{"type":"treasure","name":"Burial Offerings","desc":"Grave goods in alcoves. Gold dulled by centuries."},
    "F":{"type":"monster","name":"Embalming Room","desc":"Stone slabs stained with old chemicals.","monster_key":"shadow_lich"},
    "G":{"type":"guard","name":"The Grand Hall","desc":"A massive pillared chamber. Shadows stretch too far.","monster_key":"dark_rider"},
    "H":{"type":"trap","name":"Collapsing Floor","desc":"The stonework is loose. A dark pit yawns below."},
    "I":{"type":"monster","name":"Noble Tombs","desc":"Sarcophagi of the elite. Some are open.","monster_key":"death_tyrant"},
    "J":{"type":"empty","name":"Sealed Alcove","desc":"The door was bricked shut from the outside."},
    "K":{"type":"empty","name":"Servant's Crypt","desc":"The unmourned rest here."},
    "L":{"type":"stairs_down","name":"The Deep Stair","desc":"Carved steps descend. The air tastes of copper."},
    "M":{"type":"monster","name":"Defaced Shrine","desc":"Statues with faces chipped away.","monster_key":"bone_devil"},
    "N":{"type":"empty","name":"Echo Chamber","desc":"The walls reflect sound perfectly."},
    "O":{"type":"monster","name":"Side Crypt","desc":"Something stirs in the dark.","monster_key":"shadow_lich"},
    "P":{"type":"antechamber","name":"Sealed Door","desc":"The door is warm. Carvings move when you look away."},
    "Q":{"type":"empty","name":"Dusty Hall","desc":"Urns line the walls."},
    "R":{"type":"monster","name":"The Unburied's Tomb","desc":"It was buried here. It dug itself out.","monster_key":"bone_devil"}
}

F3M = {
    "A":{"type":"stairs_up","name":"Forge Entrance","desc":"Heat rises from below. Stone walls warm to the touch."},
    "B":{"type":"monster","name":"Sentry Post","desc":"Constructs on pedestals. Not decorative.","monster_key":"iron_golem"},
    "C":{"type":"guard","name":"Golem Bay","desc":"Storage alcoves for constructs. Not all empty.","monster_key":"adamantoise"},
    "D":{"type":"empty","name":"Heat Vent","desc":"Massive iron grates blast hot air."},
    "E":{"type":"treasure","name":"Cooling Room","desc":"Racks of hardened weapons left to rust."},
    "F":{"type":"monster","name":"Scrap Pit","desc":"Failed experiments. Some still twitching.","monster_key":"dragon"},
    "G":{"type":"guard","name":"Central Gearbox","desc":"A massive mechanism grinds endlessly.","monster_key":"iron_giant_ff"},
    "H":{"type":"shrine","name":"Maker's Altar","desc":"An altar to whoever built this place."},
    "I":{"type":"monster","name":"Vent Room","desc":"A blast door glowing cherry red.","monster_key":"iron_golem"},
    "J":{"type":"monster","name":"Smelting Room","desc":"Vats of cooled slag.","monster_key":"dragon"},
    "K":{"type":"monster","name":"Smelting Room","desc":"Molten metal still glows.","monster_key":"dragon"},
    "L":{"type":"stairs_down","name":"Thermal Shaft","desc":"A shaft along a magma channel. Brutal heat."},
    "M":{"type":"empty","name":"Thermal Anteroom","desc":"A blast door glowing cherry red."},
    "N":{"type":"empty","name":"Storage Bay","desc":"Empty racks. Whatever was here has been deployed."},
    "O":{"type":"trap","name":"Pressure Plate","desc":"The floor clicks when you step forward."},
    "P":{"type":"monster","name":"Construct Hall","desc":"They march in formation. Still.","monster_key":"iron_golem"},
    "Q":{"type":"guard","name":"Warden's Chamber","desc":"It was built to guard this forge. It never stopped.","monster_key":"iron_golem"}
}

F4M = {
    "A":{"type":"stairs_up","name":"Breach Point","desc":"The mine wall was broken through. Whatever is beyond was not meant to be found."},
    "B":{"type":"empty","name":"Silent Cavern","desc":"Your footsteps die instantly. Something absorbs sound."},
    "C":{"type":"monster","name":"Thought Eater Den","desc":"Your memories itch. Something is browsing them.","monster_key":"mindflayer"},
    "D":{"type":"guard","name":"Chasm Bridge","desc":"A narrow rock bridge over a bottomless pit.","monster_key":"behemoth"},
    "E":{"type":"monster","name":"Eldritch Hive","desc":"Fleshy growths pulse on the walls.","monster_key":"beholder"},
    "F":{"type":"trap","name":"Void Pocket","desc":"Gravity feels lighter. Shadows move independently."},
    "G":{"type":"monster","name":"Side Tunnel","desc":"Wet breathing echoes.","monster_key":"mindflayer"},
    "H":{"type":"monster","name":"The Last Camp","desc":"Bedrolls. Cold rations. The journal says 'watching.'","monster_key":"mindflayer"},
    "I":{"type":"treasure","name":"Fossilized Hoard","desc":"Gold coins embedded in solid rock."},
    "J":{"type":"monster","name":"Echo Chamber","desc":"Your heartbeat is deafening.","monster_key":"wyvern"},
    "K":{"type":"empty","name":"Echo Chamber","desc":"The walls reflect sound perfectly."},
    "L":{"type":"monster","name":"Echo Chamber","desc":"Something moves in the echoes.","monster_key":"behemoth"},
    "M":{"type":"empty","name":"Junction","desc":"Three paths diverge in darkness."},
    "N":{"type":"empty","name":"Dead End","desc":"A collapsed wall. No way forward."},
    "O":{"type":"stairs_down","name":"Abyssal Drop","desc":"The floor ends. Stairs wind down into nothing."},
    "P":{"type":"monster","name":"Chasm Edge","desc":"The void stares back.","monster_key":"wyvern"},
    "Q":{"type":"antechamber","name":"Sealed Gate","desc":"Ancient wards flicker across the stone."},
    "R":{"type":"empty","name":"Hollow","desc":"Wind from nowhere."},
    "S":{"type":"monster","name":"The Last of the Party","desc":"It used to be an adventurer. Now it remembers being one.","monster_key":"shadow_lich"}
}

F5M = {
    "A":{"type":"stairs_up","name":"The Threshold","desc":"The stairs end. The walls are not rock anymore. They breathe."},
    "B":{"type":"monster","name":"Memory Chamber","desc":"The walls show your scenes. Things you have not done yet.","monster_key":"great_behemoth"},
    "C":{"type":"guard","name":"Sealed Gallery","desc":"Crystal barriers. Constructs pristine. And angry.","monster_key":"storm_giant"},
    "D":{"type":"trap","name":"The Maze of Glass","desc":"Transparent walls. You can see everything. Reach nothing."},
    "E":{"type":"monster","name":"Construct Graveyard","desc":"Failed experiments. Not entirely failed.","monster_key":"iron_giant_ff"},
    "F":{"type":"empty","name":"Whisper Hall","desc":"The walls murmur in a dead language."},
    "G":{"type":"monster","name":"Living Corridor","desc":"The walls contract rhythmically.","monster_key":"great_behemoth"},
    "H":{"type":"guard","name":"The Anteroom","desc":"The door has no handle. It opens when it decides to.","monster_key":"storm_giant"},
    "I":{"type":"monster","name":"Core Fragment","desc":"Raw power pulsates.","monster_key":"great_behemoth"},
    "J":{"type":"shrine","name":"Altar of the Core","desc":"A pedestal floating in anti-gravity."},
    "K":{"type":"monster","name":"Heart Valve","desc":"The mountain's pulse is loudest here.","monster_key":"iron_giant_ff"},
    "L":{"type":"empty","name":"Resonance Node","desc":"Crystal formations hum at frequencies that hurt."},
    "M":{"type":"monster","name":"Perfect Specimen","desc":"Flawless. Pulsating. Aware.","monster_key":"iron_giant_ff"},
    "N":{"type":"antechamber","name":"Final Guardpost","desc":"The elite protectors who never left their station."},
    "O":{"type":"empty","name":"Side Chamber","desc":"Empty. Waiting."},
    "P":{"type":"guard","name":"The Architect's Prison","desc":"It built the mountain. They buried it inside its own work.","monster_key":"iron_giant_ff"}
}



def get_dynamic_lore(floor_num, base_meta, base_flav):
    import copy
    meta = copy.deepcopy(base_meta)
    
    # Let's inject progressive lore into the 'empty' or 'shrine' rooms (usually F, A, J, O)
    flav = base_flav
    
    if 1 <= floor_num <= 10:
        flav += " A faint scent of dried herbs lingers where it shouldn't."
        if "F" in meta:
            meta["F"]["desc"] = "A scrap of paper is pinned to the timber: 'Shipment 4 received. The payment was sufficient.'"
    elif 11 <= floor_num <= 20:
        flav += " The lanterns here burn with a familiar, unsettling blue tint."
        if "O" in meta:
            meta["O"]["desc"] = "A makeshift camp. A torn journal page reads: 'The blue flame isn't keeping them away. It's drawing them in. Who lit these?'"
    elif 21 <= floor_num <= 30:
        if "F" in meta:
            meta["F"]["desc"] = "An old ledger is carved into the bone wall. It lists inventory. At the bottom, a disturbing note: 'Two more arrived from the surface. The Tithe is paid.'"
    elif 31 <= floor_num <= 40:
        if "J" in meta:
            meta["J"]["desc"] = "A small stone basin rests in the corner, identical to the ones used for prayers above. The ash inside is fresh."
    elif 41 <= floor_num <= 50:
        flav += " The heat doesn't warm you; it feels like it's trying to digest you."
        if "F" in meta:
            meta["F"]["desc"] = "A rusted plaque bears an Aeridorian inscription: 'The Vessel must remain blind. The sanctuary must be maintained to fatten the flock.'"
    elif 51 <= floor_num <= 60:
        if "O" in meta:
            meta["O"]["desc"] = "A perfectly preserved room. On the desk is a ledger detailing supplies purchased from 'H. Store'. A note in elegant handwriting reads: 'The offering will be sufficient for the Solstice.'"
    elif 61 <= floor_num <= 70:
        flav += " The mountain breathes, and it smells like Oakhaven's well."
        if "F" in meta:
            meta["F"]["desc"] = "A massive mural. It depicts a village that looks exactly like Oakhaven. Underneath the village, roots of bone drag the townsfolk into a gaping maw. A familiar elder figure stands at the center."
    elif 71 <= floor_num <= 77:
        flav += " The air is heavy with Resonance. The truth is here."
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

    # Track creature variety stats
    zone_creature_counts = {}

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

        import random

        # ── SCRAMBLE THE LAYOUT GEOMETRY ──
        # Apply random mirroring and rotation to the room coordinates and corridors
        # 5 templates * 8 symmetries = 40 unique maze shapes!
        flip_x = random.choice([True, False])
        flip_y = random.choice([True, False])
        transpose = random.choice([True, False])
        t_rms, t_corrs = _transform_layout(rms, corrs, flip_x, flip_y, transpose)

        # ── SCRAMBLE THE ROOM ASSIGNMENTS ──
        # By shuffling the values assigned to the layout keys (A, B, C...),
        # the stairs up, stairs down, and boss rooms will spawn in completely
        # different geographic locations within the scrambled maze geometry!
        meta_keys = list(meta.keys())
        meta_values = list(meta.values())
        random.shuffle(meta_values)
        scrambled_meta = {k: v for k, v in zip(meta_keys, meta_values)}

        # Get a dynamically generated pool of monsters for THIS specific floor
        pool = _generate_floor_pool(n)
        zone_key = _get_zone_key(n)

        lines = place(t_rms, t_corrs)
        floor = build(lines, scrambled_meta, name, flav, zone_pool=pool)

        floor["floor_num"] = n

        # Override stairs down on floor 77
        if n == 77:
            floor["stairs_down_key"] = None

        floors[str(n)] = floor

        # Track variety stats
        monsters_on_floor = set()
        for k, r in floor["rooms"].items():
            mk = r.get("monster_key")
            if mk and r.get("type") in ("monster", "guard"):
                monsters_on_floor.add(mk)
        zone_creature_counts.setdefault(zone_key, set()).update(monsters_on_floor)

    # Print variety report
    print("\n── Creature Variety Report ──")
    for zone, creatures in zone_creature_counts.items():
        print(f"  {zone}: {len(creatures)} unique creatures across its floors")

    with open("utils/ttrpg/spine_layouts.json", "w") as f:
        json.dump(floors, f, indent=2)
    print(f"\nWrote spine_layouts.json for 77 floors")


if __name__ == "__main__":
    main()
