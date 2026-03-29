"""
Aethelgard Dungeon System
Procedural dungeon generation using structural layout templates.

Design philosophy:
  - Dungeons follow D&D-style structural archetypes: a defined entry zone,
    branching wings with purpose, a spine connecting areas, and a boss sanctum
    at the farthest meaningful point.
  - Room types are not rolled randomly — they are placed according to their
    position in the layout (entry buffer, wing body, dead end, spine, sanctum).
  - Each wing can have a local theme (guard post, ritual space, vault, barracks)
    that influences room sequencing within it.
  - The result feels like a place someone built, not a random maze.
"""
import secrets
import json
import os
from typing import Dict, List, Optional, Tuple

GRID_SIZE = 7          # Larger grid gives layouts more breathing room
START_POS = (0, 0)     # Always bottom-left; entrance is always here

# ── Room type constants ───────────────────────────────────────────────────────
R_START    = "start"
R_EMPTY    = "empty"      # corridor / transitional space
R_GUARD    = "guard"      # guarded checkpoint — always a monster
R_MONSTER  = "monster"    # standard combat room
R_TREASURE = "treasure"
R_SHRINE   = "shrine"
R_TRAP     = "trap"
R_BOSS     = "boss"
R_ANTECHAMBER = "antechamber"  # room immediately before boss — always empty/atmospheric

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

DIRECTIONS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}

DUNGEON_DIR = os.path.join("memory", "ttrpg", "dungeons")


def _key(x, y):    return f"{x},{y}"
def _in_bounds(x, y): return 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE


# ── Boss name generator ───────────────────────────────────────────────────────
_BOSS_PREFIXES = [
    "Rotting", "Hollow", "Ancient", "Ashen", "Sunken", "Cursed",
    "Broken", "Pale", "Silent", "Festering", "Forgotten", "Bleeding",
    "Shattered", "Withered", "Voided",
]
_BOSS_TITLES = [
    "Warden", "Remnant", "Sentinel", "Walker", "Keeper", "Revenant",
    "Hollow", "Sovereign", "Exile", "Aberration", "Thrall", "Witness",
    "Architect", "Inheritor", "Executioner",
]
_BOSS_SUFFIXES = [
    "of the Deep", "of Aeridor", "of the Ruin", "of the Whisperwood",
    "of the Forgotten Age", "of the Third Vault", "of Broken Stone",
    "of the Silent Ones", "", "", "",
]

def generate_boss_name() -> str:
    prefix = _BOSS_PREFIXES[secrets.randbelow(len(_BOSS_PREFIXES))]
    title  = _BOSS_TITLES[secrets.randbelow(len(_BOSS_TITLES))]
    suffix = _BOSS_SUFFIXES[secrets.randbelow(len(_BOSS_SUFFIXES))]
    return f"{prefix} {title}{(' ' + suffix) if suffix else ''}"


# ── Wing purpose themes ───────────────────────────────────────────────────────
# Each wing gets a purpose. The purpose determines the room sequence within it.
# Format: list of (room_type, weight) for non-terminal rooms in the wing.
# The terminal room (dead end) of each wing always gets a special placement.

WING_PURPOSES = {
    "guard_post": {
        "desc": "A military checkpoint. Guards, then a reward for clearing them.",
        "body_rooms":    [(R_GUARD, 50), (R_MONSTER, 30), (R_EMPTY, 20)],
        "terminal_room": [(R_TREASURE, 55), (R_TRAP, 30), (R_SHRINE, 15)],
    },
    "ritual_space": {
        "desc": "Aeridorian resonance workings. Unstable and watched.",
        "body_rooms":    [(R_TRAP, 40), (R_EMPTY, 35), (R_MONSTER, 25)],
        "terminal_room": [(R_SHRINE, 60), (R_TREASURE, 25), (R_TRAP, 15)],
    },
    "barracks": {
        "desc": "Sleeping quarters for whatever lived here. Now overrun.",
        "body_rooms":    [(R_MONSTER, 55), (R_GUARD, 30), (R_EMPTY, 15)],
        "terminal_room": [(R_TREASURE, 45), (R_MONSTER, 35), (R_TRAP, 20)],
    },
    "vault_approach": {
        "desc": "Locked passage toward something valuable. Heavily trapped.",
        "body_rooms":    [(R_TRAP, 45), (R_GUARD, 35), (R_EMPTY, 20)],
        "terminal_room": [(R_TREASURE, 70), (R_SHRINE, 30)],
    },
    "collapsed_wing": {
        "desc": "A damaged section. Mostly rubble, occasional survivor.",
        "body_rooms":    [(R_EMPTY, 50), (R_TRAP, 30), (R_MONSTER, 20)],
        "terminal_room": [(R_TREASURE, 40), (R_EMPTY, 40), (R_TRAP, 20)],
    },
    "sanctum_approach": {
        "desc": "The path toward something ancient. The air changes here.",
        "body_rooms":    [(R_MONSTER, 40), (R_TRAP, 30), (R_SHRINE, 30)],
        "terminal_room": [(R_SHRINE, 55), (R_TREASURE, 25), (R_EMPTY, 20)],
    },
}

WING_PURPOSE_KEYS = list(WING_PURPOSES.keys())


# ── Layout templates ──────────────────────────────────────────────────────────
# A layout template defines the structural skeleton of the dungeon.
# It is a list of "segments" — each segment is a sequence of (dx, dy) steps
# from the previous segment's starting point.
#
# The generator:
#   1. Picks a template based on difficulty
#   2. Walks each segment to place rooms
#   3. Assigns wing purposes to branching segments
#   4. Places the boss at the end of the longest path from start
#   5. Places an antechamber one step before the boss
#
# Template coordinate system: (dx, dy) steps in grid space.
# Each step creates one room and connects it to the previous.

def _get_layouts(difficulty: int) -> list:
    """
    Returns a list of layout templates appropriate for this difficulty.
    Each template is a dict with:
      - name: display name
      - segments: list of segment definitions
        Each segment: {"start_from": key_or_"start", "steps": [(dx,dy), ...], "role": "spine"|"wing"}
    """

    # ── DIFFICULTY 1: Compact, linear-ish, 8-11 rooms ────────────────────────
    d1_layouts = [
        {
            "name": "barrow",         # Linear with one side branch
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(0,1),(1,0)]},           # main corridor E then N
                {"role": "wing",  "branch_from": 1, "steps": [(0,1),(0,1)]},     # branch off 2nd room going N
                {"role": "wing",  "branch_from": 3, "steps": [(0,-1)]},          # short dead-end S of 4th room
            ],
        },
        {
            "name": "crypt",          # L-shaped with one vault branch
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(1,0),(0,1)]},
                {"role": "wing",  "branch_from": 2, "steps": [(0,-1),(0,-1)]},
            ],
        },
        {
            "name": "outpost",        # T-shape
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(0,1),(0,1)]},
                {"role": "wing",  "branch_from": 2, "steps": [(1,0),(1,0)]},
                {"role": "wing",  "branch_from": 2, "steps": [(-1,0)]},
            ],
        },
    ]

    # ── DIFFICULTY 2: Medium complexity, 11-14 rooms, two full wings ─────────
    d2_layouts = [
        {
            "name": "watchtower",     # Cross-shaped
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(0,1),(0,1),(1,0)]},
                {"role": "wing",  "branch_from": 1, "steps": [(0,1),(0,1)]},
                {"role": "wing",  "branch_from": 3, "steps": [(1,0),(1,0)]},
                {"role": "wing",  "branch_from": 2, "steps": [(0,-1)]},
            ],
        },
        {
            "name": "keep",           # Two parallel corridors joined at end
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(1,0),(0,1)]},
                {"role": "wing",  "branch_from": 0, "steps": [(0,1),(1,0),(1,0),(1,0)]},
                {"role": "wing",  "branch_from": 1, "steps": [(0,-1)]},
                {"role": "wing",  "branch_from": 3, "steps": [(0,1),(1,0)]},
            ],
        },
        {
            "name": "vault",          # Central hall with radiating wings
            "segments": [
                {"role": "spine", "steps": [(0,1),(1,0),(1,0),(0,-1)]},
                {"role": "wing",  "branch_from": 1, "steps": [(1,0),(1,0)]},
                {"role": "wing",  "branch_from": 2, "steps": [(0,1),(0,1)]},
                {"role": "wing",  "branch_from": 0, "steps": [(-1,0),(-1,0)]},
            ],
        },
    ]

    # ── DIFFICULTY 3: Complex, 14-17 rooms, multiple wings with sub-branches ──
    d3_layouts = [
        {
            "name": "ruins_complex",  # Asymmetric ruin with many branches
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(0,1),(1,0),(0,1)]},
                {"role": "wing",  "branch_from": 1, "steps": [(0,-1),(1,0)]},
                {"role": "wing",  "branch_from": 2, "steps": [(0,1),(1,0),(0,1)]},
                {"role": "wing",  "branch_from": 3, "steps": [(0,-1),(0,-1)]},
                {"role": "wing",  "branch_from": 4, "steps": [(1,0),(1,0)]},
            ],
        },
        {
            "name": "aeridor_vault",  # Formal Aeridorian layout with symmetry
            "segments": [
                {"role": "spine", "steps": [(1,0),(0,1),(1,0),(0,1),(1,0)]},
                {"role": "wing",  "branch_from": 0, "steps": [(0,-1),(0,-1)]},
                {"role": "wing",  "branch_from": 2, "steps": [(1,0),(1,0)]},
                {"role": "wing",  "branch_from": 2, "steps": [(-1,0),(-1,0)]},
                {"role": "wing",  "branch_from": 4, "steps": [(0,1),(1,0)]},
            ],
        },
        {
            "name": "deep_sanctum",   # Long approach with guarded sub-wings
            "segments": [
                {"role": "spine", "steps": [(1,0),(1,0),(1,0),(0,1),(1,0),(0,1)]},
                {"role": "wing",  "branch_from": 1, "steps": [(0,1),(1,0)]},
                {"role": "wing",  "branch_from": 3, "steps": [(1,0),(1,0),(0,-1)]},
                {"role": "wing",  "branch_from": 5, "steps": [(0,-1),(0,-1)]},
            ],
        },
    ]

    if difficulty == 1:
        return d1_layouts
    elif difficulty == 2:
        return d2_layouts
    else:
        return d3_layouts


# ── Layout builder ────────────────────────────────────────────────────────────

def _build_layout_from_template(template: dict) -> Tuple[Dict, Dict, list]:
    """
    Walk a layout template and return:
      rooms_meta: {key: {"segment_role": ..., "segment_idx": ..., "dist_from_start": ..., "is_terminal": bool}}
      connections: {key: [direction, ...]}
      all_positions: [(x, y), ...]
    """
    rooms_meta = {}
    connections: Dict[str, List[str]] = {}
    all_positions = []
    segment_endpoints: Dict[int, Tuple[int, int]] = {}  # segment_idx → last placed (x,y)

    def _connect(ax, ay, bx, by):
        # Find direction from a to b
        dx, dy = bx - ax, by - ay
        for d, (ddx, ddy) in DIRECTIONS.items():
            if ddx == dx and ddy == dy:
                connections.setdefault(_key(ax, ay), []).append(d)
                connections.setdefault(_key(bx, by), []).append(DIR_OPPOSITE[d])
                return

    def _place(x, y, role, seg_idx, dist, is_terminal=False):
        if not _in_bounds(x, y):
            return False
        k = _key(x, y)
        if k in rooms_meta:
            return False   # collision — skip
        rooms_meta[k] = {
            "segment_role": role,
            "segment_idx": seg_idx,
            "dist_from_start": dist,
            "is_terminal": is_terminal,
        }
        all_positions.append((x, y))
        return True

    # Always place start at (0, 0)
    sx, sy = START_POS
    _place(sx, sy, "spine", -1, 0, False)
    segment_endpoints[-1] = (sx, sy)
    prev_x, prev_y = sx, sy

    segments = template["segments"]
    for seg_idx, seg in enumerate(segments):
        role = seg["role"]
        steps = seg["steps"]
        branch_from = seg.get("branch_from", -1)  # which segment to branch off

        # Starting point: branch from last room of segment branch_from
        if branch_from in segment_endpoints:
            cur_x, cur_y = segment_endpoints[branch_from]
        else:
            cur_x, cur_y = segment_endpoints.get(-1, START_POS)

        prev_in_seg_x, prev_in_seg_y = cur_x, cur_y
        dist_base = rooms_meta.get(_key(cur_x, cur_y), {}).get("dist_from_start", 0)

        for step_i, (dx, dy) in enumerate(steps):
            nx, ny = cur_x + dx, cur_y + dy
            is_terminal = (step_i == len(steps) - 1)
            dist = dist_base + step_i + 1

            if not _in_bounds(nx, ny) or _key(nx, ny) in rooms_meta:
                # Try to nudge: shift one step perpendicular
                perp_options = [(-dy, dx), (dy, -dx)]
                placed = False
                for pdx, pdy in perp_options:
                    nx2, ny2 = cur_x + pdx, cur_y + pdy
                    if _in_bounds(nx2, ny2) and _key(nx2, ny2) not in rooms_meta:
                        nx, ny = nx2, ny2
                        placed = True
                        break
                if not placed:
                    # Dead-end early — record last valid pos as endpoint
                    segment_endpoints[seg_idx] = (cur_x, cur_y)
                    break

            if _place(nx, ny, role, seg_idx, dist, is_terminal):
                _connect(cur_x, cur_y, nx, ny)
                prev_in_seg_x, prev_in_seg_y = cur_x, cur_y
                cur_x, cur_y = nx, ny

        segment_endpoints[seg_idx] = (cur_x, cur_y)

    return rooms_meta, connections, all_positions


# ── Room type assignment ──────────────────────────────────────────────────────

def _assign_room_types(rooms_meta: dict, connections: dict,
                       template: dict, theme: dict) -> dict:
    """
    Assign room types to each position based on structural role and position.

    Rules:
    - (0,0) = start, always
    - First spine room after start = empty (entrance buffer)
    - Second spine room after start = guard or empty
    - Spine rooms in the middle = mix of monster/empty/trap
    - The single farthest room from start = boss
    - Room immediately before boss = antechamber
    - Wing terminals = based on wing_purpose terminal_room table
    - Wing bodies = based on wing_purpose body_rooms table
    - Any room within 2 of start = never a trap or boss
    """
    room_types: Dict[str, str] = {}

    # Find the farthest room — that's the boss
    farthest_key = max(
        rooms_meta.keys(),
        key=lambda k: rooms_meta[k]["dist_from_start"]
    )
    farthest_dist = rooms_meta[farthest_key]["dist_from_start"]

    # Find antechamber: the room on the path to boss that is one step before it
    antechamber_key = None
    boss_neighbors = connections.get(farthest_key, [])
    for d in boss_neighbors:
        dx, dy = DIRECTIONS[d]
        bx, by = int(farthest_key.split(",")[0]), int(farthest_key.split(",")[1])
        nk = _key(bx + dx, by + dy)
        if nk in rooms_meta and nk != farthest_key:
            # Prefer the neighbor that is on the spine
            if rooms_meta[nk].get("segment_role") == "spine":
                antechamber_key = nk
                break
    # Fallback: any neighbor that isn't start
    if not antechamber_key:
        for d in boss_neighbors:
            dx, dy = DIRECTIONS[d]
            bx, by = int(farthest_key.split(",")[0]), int(farthest_key.split(",")[1])
            nk = _key(bx + dx, by + dy)
            if nk in rooms_meta and nk != _key(*START_POS):
                antechamber_key = nk
                break

    # Assign wing purposes — one per unique segment_idx that is a wing
    wing_purposes_assigned: Dict[int, str] = {}
    wing_seg_indices = sorted(set(
        m["segment_idx"] for m in rooms_meta.values()
        if m["segment_role"] == "wing"
    ))
    available_purposes = WING_PURPOSE_KEYS.copy()
    for seg_idx in wing_seg_indices:
        if not available_purposes:
            available_purposes = WING_PURPOSE_KEYS.copy()
        chosen = available_purposes.pop(secrets.randbelow(len(available_purposes)))
        wing_purposes_assigned[seg_idx] = chosen

    def _weighted_choice(table):
        total = sum(w for _, w in table)
        r = secrets.randbelow(total)
        cum = 0
        for rt, w in table:
            cum += w
            if r < cum:
                return rt
        return table[0][0]

    for k, meta in rooms_meta.items():
        dist = meta["dist_from_start"]
        role = meta["segment_role"]
        seg_idx = meta["segment_idx"]
        is_terminal = meta["is_terminal"]

        # Fixed placements
        if k == _key(*START_POS):
            room_types[k] = R_START
            continue
        if k == farthest_key:
            room_types[k] = R_BOSS
            continue
        if k == antechamber_key:
            room_types[k] = R_ANTECHAMBER
            continue

        # Entry buffer — first 2 rooms from start are never dangerous
        if dist <= 1:
            room_types[k] = R_EMPTY
            continue
        if dist == 2:
            room_types[k] = R_GUARD if secrets.randbelow(2) == 0 else R_EMPTY
            continue

        # Wing rooms — use wing purpose tables
        if role == "wing":
            purpose_key = wing_purposes_assigned.get(seg_idx, "guard_post")
            purpose = WING_PURPOSES[purpose_key]
            if is_terminal:
                room_types[k] = _weighted_choice(purpose["terminal_room"])
            else:
                room_types[k] = _weighted_choice(purpose["body_rooms"])
            continue

        # Spine rooms in the middle
        # Closer to boss = more dangerous
        danger_pct = dist / max(farthest_dist, 1)
        if danger_pct < 0.4:
            spine_table = [(R_EMPTY, 40), (R_MONSTER, 35), (R_TRAP, 15), (R_SHRINE, 10)]
        elif danger_pct < 0.7:
            spine_table = [(R_MONSTER, 45), (R_GUARD, 25), (R_TRAP, 20), (R_EMPTY, 10)]
        else:
            spine_table = [(R_MONSTER, 50), (R_GUARD, 30), (R_TRAP, 20)]
        room_types[k] = _weighted_choice(spine_table)

    return room_types, wing_purposes_assigned, farthest_key


# ── Dungeon theme system (unchanged from original) ───────────────────────────

DUNGEON_THEMES = {
    "undead": {
        "name": "Undead Crypts",
        "emoji": "💀",
        "flavor": "The air reeks of old death. Something was interred here and refused to stay down.",
        "pools": {
            1: ["decaying_skeleton", "zombie", "ghoul", "ghost", "blood_slime"],
            2: ["skeleton", "ghoul", "ghost", "wight", "revenant"],
            3: ["skull_knight", "wight", "spectral_knight", "dullahan", "lich"],
        },
        "boss_pools": {
            1: ["dullahan", "revenant", "ghoul"],
            2: ["skull_knight", "dark_knight", "wight"],
            3: ["lich", "shadow_lich", "tonberry_king"],
        },
    },
    "constructs": {
        "name": "Aeridorian Vault",
        "emoji": "💎",
        "flavor": "Crystal formations absorb light. The constructs still remember their orders.",
        "pools": {
            1: ["crew_dust", "gargoyle", "soldier", "flan"],
            2: ["gargoyle", "soldier", "golem", "crystelle", "dark_wizard"],
            3: ["soldier", "crystelle", "iron_giant", "clay_golem", "skull_knight"],
        },
        "boss_pools": {
            1: ["gargoyle", "dark_wizard"],
            2: ["golem", "crystelle", "dark_knight"],
            3: ["iron_giant", "crystelle"],
        },
    },
    "beasts": {
        "name": "Hunting Grounds",
        "emoji": "🐺",
        "flavor": "Something territorial has nested here. Claw marks on every stone.",
        "pools": {
            1: ["wolf", "bat", "large_bat", "spiderling", "forest_boar"],
            2: ["wolf", "werewolf", "basilisk", "coeurl", "harpy"],
            3: ["manticore", "werewolf", "wyvern", "earth_bear", "jura_aevis"],
        },
        "boss_pools": {
            1: ["cockatrice", "wolf"],
            2: ["manticore", "wyvern", "griffon"],
            3: ["behemoth", "jura_aevis", "magic_dragon"],
        },
    },
    "deepwood": {
        "name": "Living Depths",
        "emoji": "🌑",
        "flavor": "The roots have grown through the walls. The Whisperwood consumed this place long ago.",
        "pools": {
            1: ["myconid", "grat", "ochu", "vegepygmy", "leg_eater"],
            2: ["ochu", "lamia", "cray_claw", "wind_serpent", "treant"],
            3: ["treant", "malboro", "lamia", "earth_bear", "killer_mantis"],
        },
        "boss_pools": {
            1: ["ochu", "grat"],
            2: ["treant", "lamia"],
            3: ["elder_treant", "malboro"],
        },
    },
    "demons": {
        "name": "Infernal Breach",
        "emoji": "🔥",
        "flavor": "The walls are scorched. Something forced its way through here — from below.",
        "pools": {
            1: ["imp", "bomb", "black_flan", "blood_slime"],
            2: ["grenade", "mini_satana", "dark_wizard", "nachtmahr"],
            3: ["dark_knight", "nachtmahr", "shadow_dancer", "dullahan"],
        },
        "boss_pools": {
            1: ["dark_wizard", "mini_satana"],
            2: ["dark_knight", "nachtmahr"],
            3: ["gilgamesh", "apocalypse"],
        },
    },
}

LOCATION_THEME_WEIGHTS = {
    "whisperwood_edge": [("beasts", 45), ("deepwood", 30), ("undead", 25)],
    "whisperwood_deep": [("deepwood", 40), ("undead", 30), ("beasts", 20), ("demons", 10)],
    "aeridor_ruins":    [("constructs", 45), ("undead", 30), ("demons", 25)],
    "trade_road":       [("undead", 35), ("beasts", 35), ("demons", 30)],
}

LOCATION_DIFFICULTY_BONUS = {
    "whisperwood_edge": 0,
    "whisperwood_deep": 0,
    "trade_road":       0,
    "aeridor_ruins":    1,
}


def _roll_theme(location: str) -> str:
    weights = LOCATION_THEME_WEIGHTS.get(location, [
        ("undead", 25), ("constructs", 25), ("beasts", 25), ("deepwood", 15), ("demons", 10)
    ])
    total = sum(w for _, w in weights)
    r = secrets.randbelow(total)
    cum = 0
    for theme_key, w in weights:
        cum += w
        if r < cum:
            return theme_key
    return weights[0][0]


def _scale_boss_to_level(monster: dict, player_level: int) -> dict:
    scale = max(0.45, min(1.0, 0.45 + (player_level - 1) * 0.07))
    m = dict(monster)
    m["hp"] = max(15, int(monster["hp"] * scale))
    m["attack"] = max(3, int(monster["attack"] * scale))
    m["defense"] = max(8, monster["defense"] - max(0, 5 - player_level))
    return m


def _pick_monster(room_type: str, difficulty: int, theme: dict) -> str:
    if room_type == R_BOSS:
        pool = theme["boss_pools"].get(difficulty, theme["boss_pools"].get(1, ["goblin"]))
    elif room_type == R_GUARD:
        # Guards use one tier lower than regular monsters — they're checkpoints not horrors
        low_diff = max(1, difficulty - 1)
        pool = theme["pools"].get(low_diff, theme["pools"].get(1, ["goblin"]))
    else:
        pool = theme["pools"].get(difficulty, theme["pools"].get(1, ["goblin"]))
    return pool[secrets.randbelow(len(pool))]


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

# Wing purpose flavor text shown when entering a wing's first room
WING_ENTRANCE_FLAVOR = {
    "guard_post":      "*The corridor narrows. Something was stationed here — the fixtures suggest a long watch.*",
    "ritual_space":    "*The stones hum. Aeridorian glyphs cover the walls. Something was practiced here regularly.*",
    "barracks":        "*Rusted fixtures line the walls. Whatever slept here doesn't anymore.*",
    "vault_approach":  "*The floor is scored with old drag marks. Something heavy was moved through here often.*",
    "collapsed_wing":  "*The ceiling has partially given way. Rubble everywhere. The path is passable, barely.*",
    "sanctum_approach": "*The air thickens. The light from your source dims slightly. Something ahead doesn't want visitors.*",
}

SHRINE_ROOM_SEALED    = "An alcove with a single candle. Ancient Aeridorian script. A circular seal in the stone — *three flames intertwined*. It feels like it's waiting for something."
SHRINE_ROOM_UNLOCKED  = "An alcove with a single candle. The seal glows faintly when you approach. Your hand finds the groove naturally. Something inside the stone shifts."
SHRINE_ROOM_COMPLETED = "An alcove with a single candle. The seal is dark now — whatever was stored here has been given."


# ── Main dungeon generator ────────────────────────────────────────────────────

def generate_dungeon(difficulty: int = 1, player_level: int = 1,
                     location: str = "whisperwood_edge") -> dict:
    """
    Generate a structured dungeon using layout templates.
    Returns the full dungeon state dict ready for save/play.
    """
    theme_key = _roll_theme(location)
    theme     = DUNGEON_THEMES.get(theme_key, DUNGEON_THEMES["undead"])

    # Pick a layout template
    layouts   = _get_layouts(difficulty)
    template  = layouts[secrets.randbelow(len(layouts))]

    # Build the structural skeleton
    rooms_meta, connections, all_positions = _build_layout_from_template(template)

    # Assign room types based on structure
    room_types, wing_purposes, boss_key = _assign_room_types(
        rooms_meta, connections, template, theme
    )

    # Build final rooms dict
    rooms: Dict[str, dict] = {}
    has_secret_shrine = False

    for pos in all_positions:
        k = _key(*pos)
        rt = room_types.get(k, R_EMPTY)

        boss_name = generate_boss_name() if rt == R_BOSS else None

        # Secret shrine: one per dungeon, only on shrine rooms
        is_secret_shrine = (
            rt == R_SHRINE
            and not has_secret_shrine
            and secrets.randbelow(100) < (25 + difficulty * 20)
        )
        if is_secret_shrine:
            has_secret_shrine = True

        monster_key = None
        if rt in (R_MONSTER, R_BOSS, R_GUARD):
            monster_key = _pick_monster(rt, difficulty, theme)

        desc = ROOM_DESCRIPTIONS.get(rt, "A stone room.")

        # Wing entrance flavor: first non-start room of each wing
        meta = rooms_meta.get(k, {})
        seg_idx = meta.get("segment_idx", -1)
        if (meta.get("segment_role") == "wing"
                and not meta.get("is_terminal")
                and meta.get("dist_from_start", 0) > 0):
            # Only show wing flavor on the FIRST room of a wing
            wing_rooms_in_seg = [
                kk for kk, mm in rooms_meta.items()
                if mm.get("segment_idx") == seg_idx
            ]
            min_dist_in_seg = min(
                rooms_meta[kk]["dist_from_start"] for kk in wing_rooms_in_seg
            )
            if meta["dist_from_start"] == min_dist_in_seg:
                purpose_key = wing_purposes.get(seg_idx, "guard_post")
                wing_flavor = WING_ENTRANCE_FLAVOR.get(purpose_key, "")
                if wing_flavor:
                    desc = desc + f"\n\n{wing_flavor}"

        rooms[k] = {
            "type":          rt,
            "cleared":       rt in (R_START, R_EMPTY, R_ANTECHAMBER),
            "monster_key":   monster_key,
            "boss_name":     boss_name,
            "description":   desc,
            "secret_shrine": is_secret_shrine,
            "wing_purpose":  wing_purposes.get(seg_idx) if meta.get("segment_role") == "wing" else None,
        }

    # Guarantee at least one shrine if none was placed
    has_shrine = any(r["type"] == R_SHRINE for r in rooms.values())
    if not has_shrine:
        # Find a mid-spine room (not start, not boss, not antechamber) to convert
        candidates = [
            k for k, r in rooms.items()
            if r["type"] in (R_EMPTY, R_MONSTER)
            and rooms_meta.get(k, {}).get("segment_role") == "spine"
            and rooms_meta.get(k, {}).get("dist_from_start", 0) > 2
            and k != boss_key
        ]
        if candidates:
            chosen = candidates[secrets.randbelow(len(candidates))]
            rooms[chosen]["type"] = R_SHRINE
            rooms[chosen]["cleared"] = False
            rooms[chosen]["monster_key"] = None
            rooms[chosen]["description"] = ROOM_DESCRIPTIONS[R_SHRINE]
            if not has_secret_shrine and secrets.randbelow(100) < (25 + difficulty * 20):
                rooms[chosen]["secret_shrine"] = True

    return {
        "player_pos":    list(START_POS),
        "connections":   connections,
        "rooms":         rooms,
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
        "layout_name":   template["name"],
        "boss_key":      boss_key,
        "wing_purposes": {str(k): v for k, v in wing_purposes.items()},
    }


# ── Map renderer ─────────────────────────────────────────────────────────────

def render_map(state: dict) -> str:
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
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


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
