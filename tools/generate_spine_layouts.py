#!/usr/bin/env python3
import json
import random
import os

GRID_SIZE = 24
OUTPUT_FILE = "utils/ttrpg/spine_layouts.json"

R_START       = "start"
R_EMPTY       = "empty"
R_GUARD       = "guard"
R_MONSTER     = "monster"
R_TREASURE    = "treasure"
R_SHRINE      = "shrine"
R_TRAP        = "trap"
R_BOSS        = "boss"
R_ANTECHAMBER = "antechamber"
R_STAIRS_UP   = "stairs_up"
R_STAIRS_DOWN = "stairs_down"

DIRECTIONS = [("N", 0, -1), ("S", 0, 1), ("W", -1, 0), ("E", 1, 0)]
OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}

FLOOR_THEMES = {
    1: {
        "name": "The Working Tunnels",
        "flavor": "Active mine workings. Lanterns burn. The Guild doesn't want visitors.",
        "boss": "foreman_kregg",
        "pools": ["bat", "soldier", "road_bandit"],
        "guards": ["soldier", "mercenary"],
    },
    2: {
        "name": "The Abandoned Section",
        "flavor": "Old workings. Rotten timber. The miners who died here didn't all stay dead.",
        "boss": "the_unburied",
        "pools": ["skeleton", "ghoul", "zombie"],
        "guards": ["revenant", "wight"],
    },
    3: {
        "name": "The Resonance Vein",
        "flavor": "Crystal formations that absorb light. The air hums at a frequency felt in bone. Constructs still guard what Aeridor left behind.",
        "boss": "resonance_warden",
        "pools": ["crystelle", "gargoyle"],
        "guards": ["golem", "aeridorian_soldier"],
    },
    4: {
        "name": "The Sealed Vault",
        "flavor": "Ancient Aeridorian infrastructure. New ironwork over old stone. The missing mining party's equipment is here. They are not.",
        "boss": "the_last_of_the_party",
        "pools": ["iron_golem", "mind_flayer", "beholder"],
        "guards": ["dark_knight", "spectral_knight"],
    },
    5: {
        "name": "The Deep Resonance",
        "flavor": "Raw resonance. The stone moves. Something ancient waits at the center — not dormant, patient.",
        "boss": "the_bound_architect",
        "pools": ["iron_golem", "death_tyrant", "mind_flayer"],
        "guards": ["aeridorian_guardian", "shadow_lich", "vampire_lord"],
    }
}

ROOM_DESC = {
    R_EMPTY: ["Bare stone.", "A collapsed side tunnel.", "Old pickaxes lay rusted.", "The air is stale.", "Water drips from the ceiling."],
    R_MONSTER: ["Something moves in the dark.", "You hear feeding sounds.", "A shadow detaches from the wall.", "It has been waiting."],
    R_GUARD: ["A heavy barricade blocks the way.", "A sentry stands motionless until you approach."],
    R_TREASURE: ["A forgotten supply cache.", "A heavy chest tucked in an alcove.", "Something glints in the dust."],
    R_SHRINE: ["An ancient Aeridorian prayer stone.", "A three-flame seal pulses softly in the dark."],
    R_TRAP: ["The floor looks wrong. Too smooth.", "A pressure plate clicks under your boot.", "A tripwire reflects the light."],
}

def generate_floor(floor_num, seed):
    random.seed(seed)
    
    # 1. Generate Sparse Maze (Random Tunneling)
    GRID_SIZE = 24
    NUM_ROOMS = 160  # ~25% of the grid, ensuring plenty of empty void space for walls
    
    rooms_set = {}
    connections = {}
    
    def _key(x, y): return f"{x},{y}"
    def _xy(k): return tuple(int(v) for v in k.split(","))
    
    start_x, start_y = 12, 2
    rooms_set[_key(start_x, start_y)] = True
    connections[_key(start_x, start_y)] = []
    room_keys = [_key(start_x, start_y)]
    
    while len(room_keys) < NUM_ROOMS:
        rk = random.choice(room_keys)
        cx, cy = _xy(rk)
        
        d_name, dx, dy = random.choice(DIRECTIONS)
        tunnel_length = random.randint(3, 8)
        
        for _ in range(tunnel_length):
            nx, ny = cx + dx, cy + dy
            if 1 <= nx < GRID_SIZE - 1 and 1 <= ny < GRID_SIZE - 1:
                nk = _key(nx, ny)
                ck = _key(cx, cy)
                
                if nk not in rooms_set:
                    rooms_set[nk] = True
                    connections[nk] = []
                    room_keys.append(nk)
                    
                if d_name not in connections[ck]:
                    connections[ck].append(d_name)
                    if OPPOSITE[d_name] not in connections[nk]:
                        connections[nk].append(OPPOSITE[d_name])
                        
                cx, cy = nx, ny
                if len(room_keys) >= NUM_ROOMS:
                    break
            else:
                break

    # Find furthest point via BFS
    dist = {_key(start_x, start_y): 0}
    q = [(start_x, start_y)]
    parents = {_key(start_x, start_y): None}
    
    while q:
        cx, cy = q.pop(0)
        cd = dist[_key(cx, cy)]
        for d_name, dx, dy in DIRECTIONS:
            if d_name in connections[_key(cx, cy)]:
                nx, ny = cx + dx, cy + dy
                nk = _key(nx, ny)
                if nk not in dist:
                    dist[nk] = cd + 1
                    parents[nk] = _key(cx, cy)
                    q.append((nx, ny))
                    
    furthest_k = max(dist, key=dist.get)
    boss_k = parents[furthest_k]
    ante_k = parents[boss_k] if parents[boss_k] else None
    
    # Assign rooms
    rooms = {}
    theme = FLOOR_THEMES[floor_num]
    
    for k in rooms_set.keys():
        d_val = dist[k]
        
        rtype = R_EMPTY
        mkey = None
        boss_name = None
        
        if k == _key(start_x, start_y):
            rtype = R_STAIRS_UP
            desc = "The stairwell back up."
        elif k == furthest_k:
            rtype = R_STAIRS_DOWN if floor_num < 5 else R_EMPTY
            desc = "The stairwell leading deeper into the dark." if floor_num < 5 else "The absolute bottom. The Resonance Core."
        elif k == boss_k:
            rtype = R_BOSS
            mkey = theme["boss"]
            boss_name = theme["boss"].replace("_", " ").title()
            desc = "A massive chamber. The air is heavy here."
        elif k == ante_k:
            rtype = R_ANTECHAMBER
            desc = "A quiet room. The stillness before the storm."
        else:
            # Procedural population
            # 40% empty, 40% monster, 10% trap, 5% treasure, 5% shrine
            r = random.random()
            if d_val < 3:
                rtype = R_EMPTY # Safe zone near entrance
            elif r < 0.40:
                rtype = R_EMPTY
            elif r < 0.80:
                rtype = R_MONSTER
                mkey = random.choice(theme["pools"])
            elif r < 0.90:
                rtype = R_TRAP
            elif r < 0.95:
                rtype = R_TREASURE
            else:
                rtype = R_SHRINE
                
            # High degree nodes become guards
            if len(connections[k]) >= 3 and rtype in (R_EMPTY, R_MONSTER):
                if random.random() < 0.5:
                    rtype = R_GUARD
                    mkey = random.choice(theme["guards"])
                    
            desc = random.choice(ROOM_DESC.get(rtype, ["A stone room."]))
            
        rooms[k] = {
            "type": rtype,
            "cleared": rtype in (R_EMPTY, R_STAIRS_UP, R_STAIRS_DOWN, R_ANTECHAMBER),
            "monster_key": mkey,
            "boss_name": boss_name,
            "description": desc,
            "is_room": True
        }
        
    return {
        "floor_num": floor_num,
        "floor_name": theme["name"],
        "floor_flavor": theme["flavor"],
        "boss_key": boss_k,
        "stairs_up_key": _key(start_x, start_y),
        "stairs_down_key": furthest_k if floor_num < 5 else None,
        "rooms": rooms,
        "connections": connections,
        "grid_size": GRID_SIZE
    }

def main():
    floors = {}
    for i in range(1, 6):
        floors[str(i)] = generate_floor(i, f"spine_mega_dungeon_f{i}")
        
    with open(OUTPUT_FILE, "w") as f:
        json.dump(floors, f, indent=2)
        
    print(f"Generated {len(floors)} floors of {GRID_SIZE}x{GRID_SIZE} to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
