"""
Aethelgard Dungeon System
Room-first generation with MST connectivity + loop corridors.

Design philosophy:
  - Rooms are placed first as discrete 1×1 cells across the grid
  - A Minimum Spanning Tree guarantees every room is reachable
  - Extra "loop" edges are added between nearby rooms to create
    alternative paths and eliminate forced backtracking
  - Room roles (boss, shrine, treasure, trap, guard) are assigned
    based on graph topology: distance from start, node degree,
    dead-end status
  - The boss always sits at the room farthest from the start
  - An antechamber sits immediately before the boss
  - Dead ends (degree-1 nodes) become reward rooms: treasure/shrine
  - Hub nodes (high degree) become guard checkpoints
"""
import secrets
import json
import os
from typing import Dict, List, Optional, Tuple, Set

GRID_SIZE = 9          # 9×9 grid gives good spacing
START_POS = (0, 0)

# ── Room type constants ───────────────────────────────────────────────────────
R_START       = "start"
R_EMPTY       = "empty"
R_GUARD       = "guard"
R_MONSTER     = "monster"
R_TREASURE    = "treasure"
R_SHRINE      = "shrine"
R_TRAP        = "trap"
R_BOSS        = "boss"
R_ANTECHAMBER = "antechamber"

ROOM_EMOJIS = {
    R_START:       "🏠",
    R_EMPTY:       "⬛",
    R_GUARD:       "🛡️",
    R_MONSTER:     "⚔️",
    R_TREASURE:    "💰",
    R_SHRINE:      "✨",
    R_TRAP:        "⚡",
    R_BOSS:        "💀",
    R_ANTECHAMBER: "🌑",
    "player":      "🔴",
    "unknown":     "░░",
}

DIRECTIONS    = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_OPPOSITE  = {"N": "S", "S": "N", "E": "W", "W": "E"}

DUNGEON_DIR   = os.path.join("memory", "ttrpg", "dungeons")


def _key(x, y):         return f"{x},{y}"
def _xy(k):             return tuple(int(v) for v in k.split(","))
def _in_bounds(x, y):   return 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE
def _manhattan(a, b):   return abs(a[0]-b[0]) + abs(a[1]-b[1])


# ── Boss name generator ───────────────────────────────────────────────────────
_BOSS_PREFIXES = [
    "Rotting","Hollow","Ancient","Ashen","Sunken","Cursed",
    "Broken","Pale","Silent","Festering","Forgotten","Bleeding",
    "Shattered","Withered","Voided","Bound","Seething",
]
_BOSS_TITLES = [
    "Warden","Remnant","Sentinel","Walker","Keeper","Revenant",
    "Hollow","Sovereign","Exile","Aberration","Thrall","Witness",
    "Architect","Inheritor","Executioner","Hunger","Vigil",
]
_BOSS_SUFFIXES = [
    "of the Deep","of Aeridor","of the Ruin","of the Whisperwood",
    "of the Forgotten Age","of the Third Vault","of Broken Stone",
    "of the Silent Ones","","","","",
]

def generate_boss_name() -> str:
    p = _BOSS_PREFIXES[secrets.randbelow(len(_BOSS_PREFIXES))]
    t = _BOSS_TITLES[secrets.randbelow(len(_BOSS_TITLES))]
    s = _BOSS_SUFFIXES[secrets.randbelow(len(_BOSS_SUFFIXES))]
    return f"{p} {t}{(' ' + s) if s else ''}"


# ── Dungeon themes (unchanged) ────────────────────────────────────────────────
DUNGEON_THEMES = {
    "undead": {
        "name": "Undead Crypts",
        "emoji": "💀",
        "flavor": "The air reeks of old death. Something was interred here and refused to stay down.",
        "pools": {
            1: ["decaying_skeleton","zombie","ghoul","ghost","blood_slime"],
            2: ["skeleton","ghoul","ghost","wight","revenant"],
            3: ["skull_knight","wight","spectral_knight","dullahan","lich"],
            4: ["shadow_lich","vampire_lord","dark_rider","death_knight_dd","bone_devil"],
            5: ["lich","shadow_lich","death_tyrant","nicol_bolas_echo","vecna_lich_god"],
        },
        "boss_pools": {
            1: ["dullahan","revenant","ghoul"],
            2: ["skull_knight","dark_knight","wight"],
            3: ["lich","shadow_lich","tonberry_king"],
            4: ["death_tyrant","vampire_lord","death_knight_dd"],
            5: ["vecna_lich_god","acererak","lord_soth"],
        },
    },
    "constructs": {
        "name": "Aeridorian Vault",
        "emoji": "💎",
        "flavor": "Crystal formations absorb light. The constructs still remember their orders.",
        "pools": {
            1: ["crew_dust","gargoyle","soldier","flan"],
            2: ["gargoyle","soldier","golem","crystelle","dark_wizard"],
            3: ["soldier","crystelle","iron_giant","clay_golem","skull_knight"],
            4: ["iron_golem","iron_giant_ff","beholder","mind_flayer","crystelle"],
            5: ["omega","adamantoise","tiamat_avatar","bahamut_ff","iron_golem"],
        },
        "boss_pools": {
            1: ["gargoyle","dark_wizard"],
            2: ["golem","crystelle","dark_knight"],
            3: ["iron_giant","crystelle"],
            4: ["iron_giant_ff","beholder","mind_flayer"],
            5: ["omega_ff5","aeridorian_guardian","shinryu_ff5"],
        },
    },
    "beasts": {
        "name": "Hunting Grounds",
        "emoji": "🐺",
        "flavor": "Something territorial has nested here. Claw marks on every stone.",
        "pools": {
            1: ["wolf","bat","large_bat","spiderling","forest_boar"],
            2: ["wolf","werewolf","basilisk","coeurl","harpy"],
            3: ["manticore","werewolf","wyvern","earth_bear","jura_aevis"],
            4: ["behemoth","great_behemoth","dragon","hydra","red_dragon"],
            5: ["king_behemoth","shinryu","ancient_red_dragon","frost_dragon","shivan_dragon"],
        },
        "boss_pools": {
            1: ["cockatrice","wolf"],
            2: ["manticore","wyvern","griffon"],
            3: ["behemoth","jura_aevis","magic_dragon"],
            4: ["great_behemoth","dragon","hydra"],
            5: ["king_behemoth","shinryu_ff5","bahamut_ff"],
        },
    },
    "deepwood": {
        "name": "Living Depths",
        "emoji": "🌑",
        "flavor": "The roots have grown through the walls. The Whisperwood consumed this place long ago.",
        "pools": {
            1: ["myconid","grat","ochu","vegepygmy","leg_eater"],
            2: ["ochu","lamia","cray_claw","wind_serpent","treant"],
            3: ["treant","malboro","lamia","earth_bear","killer_mantis"],
            4: ["elder_treant","exdeath_tree","apocalypse","great_behemoth","craw_wurm"],
            5: ["whisperwood_heart","atomos","shinryu","king_behemoth","exdeath_tree"],
        },
        "boss_pools": {
            1: ["ochu","grat"],
            2: ["treant","lamia"],
            3: ["elder_treant","malboro"],
            4: ["exdeath_tree","great_behemoth","apocalypse"],
            5: ["whisperwood_heart","elder_treant","exdeath_ff5"],
        },
    },
    "demons": {
        "name": "Infernal Breach",
        "emoji": "🔥",
        "flavor": "The walls are scorched. Something forced its way through here — from below.",
        "pools": {
            1: ["imp","bomb","black_flan","blood_slime"],
            2: ["grenade","mini_satana","dark_wizard","nachtmahr"],
            3: ["dark_knight","nachtmahr","shadow_dancer","dullahan"],
            4: ["balor_dd","marilith","glabrezu","bone_devil","hezrou"],
            5: ["demogorgon_echo","orcus_aspect","grazzt_avatar","kefka_ascended","balor_dd"],
        },
        "boss_pools": {
            1: ["dark_wizard","mini_satana"],
            2: ["dark_knight","nachtmahr"],
            3: ["gilgamesh","apocalypse"],
            4: ["balor_dd","marilith","storm_giant"],
            5: ["chaos_ff1","kefka_ascended","demogorgon_echo"],
        },
    },
}

LOCATION_THEME_WEIGHTS = {
    "whisperwood_edge": [("beasts",45),("deepwood",30),("undead",25)],
    "whisperwood_deep": [("deepwood",40),("undead",30),("beasts",20),("demons",10)],
    "aeridor_ruins":    [("constructs",45),("undead",30),("demons",25)],
    "trade_road":       [("undead",35),("beasts",35),("demons",30)],
}

LOCATION_DIFFICULTY_BONUS = {
    "whisperwood_edge": 0,
    "whisperwood_deep": 0,
    "trade_road":       0,
    "aeridor_ruins":    2,
}


def _roll_theme(location: str) -> str:
    weights = LOCATION_THEME_WEIGHTS.get(location, [
        ("undead",25),("constructs",25),("beasts",25),("deepwood",15),("demons",10)
    ])
    total = sum(w for _, w in weights)
    r = secrets.randbelow(total)
    cum = 0
    for theme_key, w in weights:
        cum += w
        if r < cum:
            return theme_key
    return weights[0][0]


# ── Phase 1: Room placement ───────────────────────────────────────────────────

def _place_rooms(num_rooms: int) -> List[Tuple[int,int]]:
    """
    Scatter num_rooms cells across the grid, ensuring:
    - (0,0) is always included (entrance)
    - No two rooms share a cell
    - Rooms are spread across the grid (not all clustered)
    - Minimum spacing of 1 cell between rooms (so corridors have room to exist)
    """
    occupied: Set[Tuple[int,int]] = set()
    rooms: List[Tuple[int,int]] = []

    # Always start at (0,0)
    rooms.append(START_POS)
    occupied.add(START_POS)

    attempts = 0
    max_attempts = num_rooms * 40

    while len(rooms) < num_rooms and attempts < max_attempts:
        attempts += 1
        x = secrets.randbelow(GRID_SIZE)
        y = secrets.randbelow(GRID_SIZE)
        pos = (x, y)

        if pos in occupied:
            continue

        # Enforce minimum spacing of 1 cell (rooms can't be directly adjacent —
        # that space is used for corridor indication in connections dict)
        too_close = False
        for rx, ry in rooms:
            if abs(x - rx) <= 1 and abs(y - ry) <= 1:
                too_close = True
                break
        if too_close:
            continue

        rooms.append(pos)
        occupied.add(pos)

    return rooms


# ── Phase 2: MST connectivity (Prim's algorithm) ─────────────────────────────

def _build_mst(rooms: List[Tuple[int,int]]) -> List[Tuple[Tuple[int,int], Tuple[int,int]]]:
    """
    Build a Minimum Spanning Tree connecting all rooms.
    Returns list of (room_a, room_b) edges representing corridors.
    Uses Manhattan distance as edge weight.
    """
    if len(rooms) <= 1:
        return []

    in_tree: Set[Tuple[int,int]] = {rooms[0]}
    edges: List[Tuple[Tuple[int,int], Tuple[int,int]]] = []

    while len(in_tree) < len(rooms):
        best_dist = float('inf')
        best_edge = None

        for a in in_tree:
            for b in rooms:
                if b in in_tree:
                    continue
                d = _manhattan(a, b)
                if d < best_dist:
                    best_dist = d
                    best_edge = (a, b)

        if best_edge is None:
            break
        edges.append(best_edge)
        in_tree.add(best_edge[1])

    return edges


# ── Phase 3: Add loop corridors ───────────────────────────────────────────────

def _add_loops(
    rooms: List[Tuple[int,int]],
    mst_edges: List[Tuple[Tuple[int,int], Tuple[int,int]]],
    num_loops: int,
) -> List[Tuple[Tuple[int,int], Tuple[int,int]]]:
    """
    Add extra connections between nearby rooms that aren't already connected.
    This creates loops so players don't have to fully backtrack.
    Candidates are pairs within Manhattan distance of ~4 that aren't in MST.
    """
    mst_set: Set[frozenset] = {frozenset(e) for e in mst_edges}
    candidates: List[Tuple[int, Tuple[int,int], Tuple[int,int]]] = []

    for i, a in enumerate(rooms):
        for b in rooms[i+1:]:
            if frozenset((a, b)) in mst_set:
                continue
            d = _manhattan(a, b)
            if 2 <= d <= 5:   # nearby but not trivially adjacent
                candidates.append((d, a, b))

    # Sort by distance (prefer shorter extra corridors)
    candidates.sort(key=lambda x: x[0])

    added = []
    for _, a, b in candidates:
        if len(added) >= num_loops:
            break
        added.append((a, b))

    return added


# ── Phase 4: Build connections dict from edges ────────────────────────────────

def _edges_to_connections(
    rooms: List[Tuple[int,int]],
    all_edges: List[Tuple[Tuple[int,int], Tuple[int,int]]],
) -> Dict[str, List[str]]:
    """
    Convert room-pair edges into the connections dict format:
    { "x,y": ["N","E",...], ... }
    
    For each edge (a, b), we need to find the cardinal direction from a→b.
    Since rooms aren't necessarily adjacent, we route the corridor through
    intermediate cells and record which direction to travel.
    
    Strategy: for each edge, we carve an L-shaped or straight path through
    intermediate corridor cells, adding those as EMPTY connector nodes,
    and record the entry/exit directions for each cell along the path.
    """
    connections: Dict[str, List[str]] = {_key(*r): [] for r in rooms}
    corridor_cells: Set[Tuple[int,int]] = set()

    def _add_conn(cx, cy, direction):
        k = _key(cx, cy)
        if k not in connections:
            connections[k] = []
        if direction not in connections[k]:
            connections[k].append(direction)

    for (ax, ay), (bx, by) in all_edges:
        # Route an L-shaped corridor: first horizontal, then vertical
        # (or straight if same row/column)
        path_cells = []

        if ax == bx:
            # Straight vertical
            step = 1 if by > ay else -1
            for cy in range(ay, by + step, step):
                path_cells.append((ax, cy))
        elif ay == by:
            # Straight horizontal
            step = 1 if bx > ax else -1
            for cx in range(ax, bx + step, step):
                path_cells.append((cx, ay))
        else:
            # L-shaped: go horizontal first, then vertical
            # Randomly pick which bend to use for variety
            if secrets.randbelow(2) == 0:
                # Horizontal first
                step_x = 1 if bx > ax else -1
                for cx in range(ax, bx + step_x, step_x):
                    path_cells.append((cx, ay))
                step_y = 1 if by > ay else -1
                for cy in range(ay + step_y, by + step_y, step_y):
                    path_cells.append((bx, cy))
            else:
                # Vertical first
                step_y = 1 if by > ay else -1
                for cy in range(ay, by + step_y, step_y):
                    path_cells.append((ax, cy))
                step_x = 1 if bx > ax else -1
                for cx in range(ax + step_x, bx + step_x, step_x):
                    path_cells.append((cx, by))

        # Deduplicate while preserving order
        seen = set()
        clean_path = []
        for c in path_cells:
            if c not in seen:
                seen.add(c)
                clean_path.append(c)

        # Register corridor cells (intermediate cells not already rooms)
        room_set = set(rooms)
        for cell in clean_path:
            if cell not in room_set and _in_bounds(*cell):
                corridor_cells.add(cell)

        # Wire up connections along the path
        for i in range(len(clean_path) - 1):
            cx, cy = clean_path[i]
            nx, ny = clean_path[i + 1]
            if not _in_bounds(cx, cy) or not _in_bounds(nx, ny):
                continue
            dx, dy = nx - cx, ny - cy
            for d, (ddx, ddy) in DIRECTIONS.items():
                if ddx == dx and ddy == dy:
                    _add_conn(cx, cy, d)
                    _add_conn(nx, ny, DIR_OPPOSITE[d])
                    break

    return connections, corridor_cells


# ── Phase 5: Graph analysis ───────────────────────────────────────────────────

def _analyze_graph(
    rooms: List[Tuple[int,int]],
    connections: Dict[str, List[str]],
) -> Dict[str, dict]:
    """
    BFS from start through ALL connected cells (rooms AND corridor connectors).
    This is the critical fix: the old BFS only enqueued room cells, which meant
    it couldn't traverse multi-cell corridors and returned dist=999 for almost
    every room, causing the boss to spawn near the entrance.
    """
    from collections import deque
    room_set = set(rooms)

    # Walk the full connection graph — corridor cells included
    dist_all: Dict[Tuple[int,int], int] = {START_POS: 0}
    queue: deque = deque([START_POS])
    while queue:
        pos = queue.popleft()
        k = _key(*pos)
        for d in connections.get(k, []):
            dx, dy = DIRECTIONS[d]
            nb = (pos[0] + dx, pos[1] + dy)
            if nb not in dist_all:
                dist_all[nb] = dist_all[pos] + 1
                queue.append(nb)

    meta: Dict[str, dict] = {}
    for room in rooms:
        k = _key(*room)
        direct_dirs = connections.get(k, [])
        degree = len(direct_dirs)
        meta[k] = {
            "dist_from_start": dist_all.get(room, 999),
            "degree": degree,
            "is_dead_end": degree <= 1 and room != START_POS,
        }
    return meta


# ── Phase 6: Assign room types ────────────────────────────────────────────────

def _assign_room_types(
    rooms: List[Tuple[int,int]],
    meta: Dict[str, dict],
    corridor_cells: Set[Tuple[int,int]],
    difficulty: int,
) -> Tuple[Dict[str, str], Tuple[int,int]]:
    """
    Assign room types based on topology.

    Rules (in priority order):
    1. (0,0) → start
    2. Farthest room → boss
    3. Room before boss (on shortest path) → antechamber  
    4. Dead ends (degree 1) → alternate between treasure/shrine/trap
       (these are the "worth exploring" dead ends)
    5. High-degree hubs → guard (checkpoints)
    6. Remaining rooms → monster/empty/trap weighted by distance
    """
    room_set = set(rooms)

    # Find boss: farthest DEAD-END room from start.
    # A dead-end guarantees no rooms exist "beyond" the boss — without this,
    # rooms connected only through the boss room become permanently inaccessible.
    dead_ends = [r for r in rooms if meta[_key(*r)]["is_dead_end"]]
    if dead_ends:
        boss_pos = max(dead_ends, key=lambda r: meta[_key(*r)]["dist_from_start"])
    else:
        # Fallback if somehow no dead-ends exist (shouldn't happen with MST)
        boss_pos = max(
            [r for r in rooms if r != START_POS],
            key=lambda r: meta[_key(*r)]["dist_from_start"]
        )
    boss_key = _key(*boss_pos)

    # Find antechamber: room one step before boss in BFS tree
    # (the room with dist = boss_dist - 1 that has a connection to boss)
    boss_dist = meta[boss_key]["dist_from_start"]
    antechamber_pos = None
    boss_k = _key(*boss_pos)
    for d in ["N","S","E","W"]:
        dx, dy = DIRECTIONS[d]
        nx, ny = boss_pos[0]+dx, boss_pos[1]+dy
        nb = (nx, ny)
        nb_k = _key(*nb)
        if nb in room_set and nb_k in meta:
            if meta[nb_k]["dist_from_start"] == boss_dist - 1:
                antechamber_pos = nb
                break
    # Fallback: nearest room to boss that isn't boss
    if not antechamber_pos:
        candidates = [r for r in rooms if r != boss_pos]
        if candidates:
            antechamber_pos = min(
                candidates,
                key=lambda r: (_manhattan(r, boss_pos), -meta[_key(*r)]["dist_from_start"])
            )

    types: Dict[str, str] = {}
    dead_end_idx = 0
    dead_end_cycle = [R_TREASURE, R_SHRINE, R_TREASURE, R_TRAP]

    has_secret_shrine = False

    for room in rooms:
        k = _key(*room)
        m = meta[k]

        # Fixed
        if room == START_POS:
            types[k] = R_START
            continue
        if room == boss_pos:
            types[k] = R_BOSS
            continue
        if room == antechamber_pos:
            types[k] = R_ANTECHAMBER
            continue

        dist = m["dist_from_start"]

        # Entry buffer — first 2 hops are always safe
        if dist <= 1:
            types[k] = R_EMPTY
            continue
        if dist == 2:
            types[k] = R_GUARD if secrets.randbelow(2) == 0 else R_EMPTY
            continue

        # Dead ends → reward rooms
        if m["is_dead_end"]:
            t = dead_end_cycle[dead_end_idx % len(dead_end_cycle)]
            dead_end_idx += 1
            types[k] = t
            continue

        # High-degree hubs → guard checkpoints
        if m["degree"] >= 4:
            types[k] = R_GUARD
            continue

        # Distance-weighted regular rooms
        danger_pct = dist / max(boss_dist, 1)
        if danger_pct < 0.35:
            table = [(R_EMPTY,40),(R_MONSTER,35),(R_TRAP,15),(R_SHRINE,10)]
        elif danger_pct < 0.65:
            table = [(R_MONSTER,45),(R_GUARD,20),(R_TRAP,25),(R_EMPTY,10)]
        else:
            table = [(R_MONSTER,50),(R_GUARD,25),(R_TRAP,20),(R_SHRINE,5)]

        total = sum(w for _,w in table)
        r = secrets.randbelow(total)
        cum = 0
        for rt, w in table:
            cum += w
            if r < cum:
                types[k] = rt
                break

    # Ensure at least 1 shrine exists
    shrine_exists = any(t == R_SHRINE for t in types.values())
    if not shrine_exists:
        # Convert the last dead-end treasure to shrine, or a mid-distance empty room
        for room in rooms:
            k = _key(*room)
            if types.get(k) == R_TREASURE and meta[k]["is_dead_end"]:
                types[k] = R_SHRINE
                shrine_exists = True
                break
        if not shrine_exists:
            for room in rooms:
                k = _key(*room)
                if types.get(k) == R_EMPTY and meta[k]["dist_from_start"] > 2:
                    types[k] = R_SHRINE
                    break

    return types, boss_pos


# ── Room descriptions ─────────────────────────────────────────────────────────

ROOM_DESCRIPTIONS = {
    R_START:       "The entry shaft. Torchlight from above. The way back is behind you.",
    R_EMPTY:       "Bare stone. Something was here once. The marks on the floor suggest it left in a hurry.",
    R_GUARD:       "A checkpoint room. Something was stationed here. Evidence of a long vigil — old bones, rusted fixtures.",
    R_MONSTER:     "The air changes the moment you step in. Something moves in the dark.",
    R_TREASURE:    "A battered chest, lock already sprung. Whatever got here first left the heavy stuff.",
    R_SHRINE:      "An alcove with a single candle. Ancient Aeridorian script. The flame doesn't waver in any draft.",
    R_TRAP:        "The floor looks wrong. Too smooth. The stones are too evenly placed.",
    R_BOSS:        "The chamber opens wider than any other. Something large has been waiting here for a long time.",
    R_ANTECHAMBER: "A still room before the final door. The air is cold and deliberate. Something ancient breathes on the other side.",
}

SHRINE_ROOM_SEALED    = "An alcove with a single candle. Ancient Aeridorian script. A circular seal in the stone — *three flames intertwined*. It feels like it's waiting for something."
SHRINE_ROOM_UNLOCKED  = "An alcove with a single candle. The seal glows faintly when you approach. Your hand finds the groove naturally. Something inside the stone shifts."
SHRINE_ROOM_COMPLETED = "An alcove with a single candle. The seal is dark now — whatever was stored here has been given."


def _pick_monster(room_type: str, difficulty: int, theme: dict) -> str:
    if room_type == R_BOSS:
        pool = theme["boss_pools"].get(difficulty, theme["boss_pools"].get(1, ["goblin"]))
    elif room_type == R_GUARD:
        low_diff = max(1, difficulty - 1)
        pool = theme["pools"].get(low_diff, theme["pools"].get(1, ["goblin"]))
    else:
        pool = theme["pools"].get(difficulty, theme["pools"].get(1, ["goblin"]))
    return pool[secrets.randbelow(len(pool))]


# ── Main generator ────────────────────────────────────────────────────────────

def generate_dungeon(
    difficulty: int = 1,
    player_level: int = 1,
    location: str = "whisperwood_edge",
) -> dict:
    """
    Generate a room-first dungeon with MST connectivity and loop corridors.
    Returns the full dungeon state dict ready for save/play.
    """
    theme_key = _roll_theme(location)
    theme     = DUNGEON_THEMES.get(theme_key, DUNGEON_THEMES["undead"])

    # Scale room count and loop count with difficulty
    # D1: 10–13 rooms, 1–2 loops
    # D2: 13–17 rooms, 2–3 loops
    # D3: 17–22 rooms, 3–4 loops
    # D4: 20–25 rooms, 4–5 loops
    # D5: 23–28 rooms, 5–6 loops
    base_rooms = {1: 11, 2: 15, 3: 19, 4: 21, 5: 24}
    variance   = {1: 3,  2: 4,  3: 4,  4: 5,  5: 5}
    num_rooms  = base_rooms.get(difficulty, 24) + secrets.randbelow(variance.get(difficulty, 5))
    num_loops  = difficulty + secrets.randbelow(2)   # 1–2, 2–3, 3–4, 4–5, 5–6

    # Phase 1: Place rooms
    rooms = _place_rooms(num_rooms)

    # Phase 2: MST
    mst_edges = _build_mst(rooms)

    # Phase 3: Add loops
    loop_edges = _add_loops(rooms, mst_edges, num_loops)

    all_edges = mst_edges + loop_edges

    # Phase 4: Build connections + corridor cells
    connections, corridor_cells = _edges_to_connections(rooms, all_edges)

    # Phase 5: Graph analysis
    meta = _analyze_graph(rooms, connections)

    # Phase 6: Assign room types
    room_types, boss_pos = _assign_room_types(rooms, meta, corridor_cells, difficulty)
    boss_key = _key(*boss_pos)

    # Phase 7: Build final rooms dict (rooms + corridor connectors)
    all_cells = list(rooms) + [c for c in corridor_cells if _in_bounds(*c)]
    rooms_dict: Dict[str, dict] = {}
    has_secret_shrine = False

    for cell in all_cells:
        k = _key(*cell)
        is_room = cell in set(rooms)
        rt = room_types.get(k, R_EMPTY)  # corridor cells are always empty

        boss_name = generate_boss_name() if rt == R_BOSS else None

        # Secret shrine logic
        is_secret_shrine = False
        if rt == R_SHRINE and is_room and not has_secret_shrine:
            if secrets.randbelow(100) < (25 + difficulty * 20):
                is_secret_shrine = True
                has_secret_shrine = True

        monster_key = None
        if rt in (R_MONSTER, R_BOSS, R_GUARD) and is_room:
            monster_key = _pick_monster(rt, difficulty, theme)

        desc = ROOM_DESCRIPTIONS.get(rt, "A stone passage.")

        rooms_dict[k] = {
            "type":          rt,
            "cleared":       rt in (R_START, R_EMPTY, R_ANTECHAMBER) or not is_room,
            "monster_key":   monster_key,
            "boss_name":     boss_name,
            "description":   desc,
            "secret_shrine": is_secret_shrine,
            "is_room":       is_room,   # rooms vs corridor connectors
        }

    # Ensure at least 5 combat rooms among true rooms
    combat_count = sum(
        1 for k, r in rooms_dict.items()
        if r["type"] in (R_MONSTER, R_GUARD) and r["is_room"] and k != boss_key
    )
    if combat_count < 5:
        shortfall = 5 - combat_count
        candidates = [
            k for k, r in rooms_dict.items()
            if r["type"] == R_EMPTY and r["is_room"]
            and k != _key(*START_POS) and k != boss_key
            and meta.get(k, {}).get("dist_from_start", 0) > 1
        ]
        # Shuffle candidates
        for i in range(len(candidates)-1, 0, -1):
            j = secrets.randbelow(i+1)
            candidates[i], candidates[j] = candidates[j], candidates[i]
        for k in candidates[:shortfall]:
            rooms_dict[k]["type"] = R_MONSTER
            rooms_dict[k]["cleared"] = False
            rooms_dict[k]["monster_key"] = _pick_monster(R_MONSTER, difficulty, theme)

    # ── Post-generation reachability prune ────────────────────────────────────
    # Remove any rooms or corridors not reachable from START_POS.
    # Defensive against edge cases in corridor routing; also ensures the map
    # displayed to the player never contains cells they can't reach.
    from collections import deque as _deque
    reachable: set = {_key(*START_POS)}
    _q: _deque = _deque([START_POS])
    while _q:
        _pos = _q.popleft()
        _pk = _key(*_pos)
        for _d in connections.get(_pk, []):
            _dx, _dy = DIRECTIONS[_d]
            _nb = (_pos[0] + _dx, _pos[1] + _dy)
            _nk = _key(*_nb)
            if _nk not in reachable:
                reachable.add(_nk)
                _q.append(_nb)

    # Prune rooms_dict to only reachable cells
    rooms_dict = {k: v for k, v in rooms_dict.items() if k in reachable}

    # Prune connections: drop unreachable cells, and trim directions that
    # point into unreachable cells
    connections = {
        k: [
            d for d in dirs
            if _key(
                _xy(k)[0] + DIRECTIONS[d][0],
                _xy(k)[1] + DIRECTIONS[d][1]
            ) in reachable
        ]
        for k, dirs in connections.items()
        if k in reachable
    }

    return {
        "player_pos":    list(START_POS),
        "connections":   connections,
        "rooms":         rooms_dict,
        "visited":       [_key(*START_POS)],
        "grid_size":     GRID_SIZE,
        "active":        True,
        "xp_gained":     0,
        "gil_gained":    0,
        "loot_gained":   [],
        "player_level":  player_level,
        "difficulty":    difficulty,
        "location":      location,
        "theme_key":     theme_key,
        "theme_name":    theme["name"],
        "theme_emoji":   theme["emoji"],
        "theme_flavor":  theme["flavor"],
        "layout_name":   "room_mst",
        "boss_key":      boss_key,
    }


# ── Map renderer ─────────────────────────────────────────────────────────────

def render_map(state: dict) -> str:
    """
    Render the dungeon as a grid of emoji.
    Rooms show their type emoji. Corridor connectors show as ⬛.
    Unknown cells show as ░░.
    """
    size = state["grid_size"]
    visited = set(state["visited"])
    rooms   = state["rooms"]

    lines = []
    for y in range(size):
        row = ""
        for x in range(size):
            k = _key(x, y)
            if [x, y] == state["player_pos"]:
                row += "🔴"
            elif k in visited:
                rt = rooms.get(k, {}).get("type", R_EMPTY)
                row += ROOM_EMOJIS.get(rt, "⬛")
            elif k in rooms:
                row += "░░"
            else:
                row += "　　"   # full-width space for empty grid cells
        lines.append(row)
    return "\n".join(lines)


# ── Persistence ───────────────────────────────────────────────────────────────

def save_dungeon(user_id: str, state: dict):
    os.makedirs(DUNGEON_DIR, exist_ok=True)
    path = os.path.join(DUNGEON_DIR, f"{user_id}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def load_dungeon(user_id: str) -> Optional[dict]:
    path = os.path.join(DUNGEON_DIR, f"{user_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def clear_dungeon(user_id: str):
    path = os.path.join(DUNGEON_DIR, f"{user_id}.json")
    if os.path.exists(path):
        os.remove(path)


# ── Scale boss to level (called by rpg_handler) ───────────────────────────────

def _scale_boss_to_level(monster: dict, player_level: int) -> dict:
    """Scale dungeon boss stats to player level with hard caps."""
    scale = max(0.30, min(1.0, 0.30 + (player_level - 1) * 0.08))
    m = dict(monster)
    m["hp"]     = max(15, int(monster["hp"] * scale))
    m["attack"] = max(3,  int(monster["attack"] * scale))
    m["defense"]= max(8,  monster["defense"] - max(0, 5 - player_level))

    BOSS_HP_CAPS  = {1:35,2:45,3:55,4:65,5:80,6:110,7:140,8:180,9:220,10:270,11:330,12:400,13:480,14:570,15:680}
    BOSS_ATK_CAPS = {1:6, 2:8, 3:10,4:12,5:14,6:16, 7:18, 8:20, 9:22, 10:24, 11:26, 12:28, 13:30, 14:32, 15:35}

    hp_cap  = BOSS_HP_CAPS.get(player_level)
    atk_cap = BOSS_ATK_CAPS.get(player_level)
    if hp_cap:  m["hp"]     = min(m["hp"],     hp_cap)
    if atk_cap: m["attack"] = min(m["attack"],  atk_cap)
    return m
