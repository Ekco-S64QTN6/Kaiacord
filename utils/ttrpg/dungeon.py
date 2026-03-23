"""
Aethelgard Dungeon System
Procedural maze generation, state persistence, map rendering.
"""
import secrets
import json
import os
from typing import Dict, List, Optional, Tuple

GRID_SIZE = 5
START_POS = (0, 0)

R_START    = "start"
R_EMPTY    = "empty"
R_MONSTER  = "monster"
R_TREASURE = "treasure"
R_SHRINE   = "shrine"
R_TRAP     = "trap"
R_BOSS     = "boss"
R_EXIT     = "exit"

ROOM_WEIGHTS = [
    (R_EMPTY,    18),
    (R_MONSTER,  45),
    (R_TREASURE, 15),
    (R_SHRINE,    8),
    (R_TRAP,     14),
]

ROOM_EMOJIS = {
    R_START:    "🏠",
    R_EMPTY:    "⬛",
    R_MONSTER:  "⚔️",
    R_TREASURE: "💰",
    R_SHRINE:   "✨",
    R_TRAP:     "⚡",
    R_BOSS:     "💀",
    R_EXIT:     "🚪",
    "player":   "🔴",
    "unknown":  "░░",
}

# Boss name generator
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
    "of the Silent Ones", "", "", "",  # weighted toward no suffix
]

def generate_boss_name() -> str:
    prefix = _BOSS_PREFIXES[secrets.randbelow(len(_BOSS_PREFIXES))]
    title  = _BOSS_TITLES[secrets.randbelow(len(_BOSS_TITLES))]
    suffix = _BOSS_SUFFIXES[secrets.randbelow(len(_BOSS_SUFFIXES))]
    return f"{prefix} {title}{(' ' + suffix) if suffix else ''}"


# Tiered boss monster pools — matched to player level/difficulty
BOSS_POOLS = {
    1: [  # Level 1-3 (difficulty 1)
        "skull_knight", "dark_wizard", "dullahan", "revenant",
        "gargoyle", "nachtmahr", "werewolf",
    ],
    2: [  # Level 4-6 (difficulty 2)
        "tonberry", "dark_knight", "minotaur", "iron_giant",
        "crystelle", "jura_aevis", "necrophobe",
    ],
    3: [  # Level 7+ (difficulty 3)
        "tonberry_king", "lich", "magic_dragon", "adamantoise",
        "gilgamesh", "azulmagia", "behemoth", "archaeoaevis",
    ],
}

# Regular monster pools per difficulty
MONSTER_POOLS = {
    1: ["goblin", "skeleton", "bat", "wolf", "zombie", "bandit", "ghoul"],
    2: ["skeleton", "ghoul", "wolf", "harpy", "lizardman", "dark_wizard", "gargoyle"],
    3: ["dark_knight", "skull_knight", "gargoyle", "lamia", "soldier", "iron_giant"],
}


def _scale_boss_to_level(monster: dict, player_level: int) -> dict:
    """
    Scale boss stats to be challenging but beatable at the player's level.
    At level 5, a tonberry becomes ~55 HP / 14 ATK rather than 80 HP / 22 ATK.
    Scale rises smoothly: ~0.5x at level 1, ~0.8x at level 5, 1.0x at level 9.
    """
    scale = max(0.45, min(1.0, 0.45 + (player_level - 1) * 0.07))
    m = dict(monster)
    m["hp"] = max(15, int(monster["hp"] * scale))
    m["attack"] = max(3, int(monster["attack"] * scale))
    # Defense stays roughly the same — DEF is easier to counter with gear
    m["defense"] = max(8, monster["defense"] - max(0, 5 - player_level))
    return m


ROOM_DESCRIPTIONS = {
    R_START:    "The entry shaft. Torchlight from above. The way back is behind you.",
    R_EMPTY:    "Bare stone. Something was here once. The marks on the floor suggest it left in a hurry.",
    R_MONSTER:  "The air changes the moment you step in. Something moves in the dark.",
    R_TREASURE: "A battered chest, lock already sprung. Whatever got here first left the heavy stuff.",
    R_SHRINE:   "An alcove with a single candle. Ancient Aeridorian script. The flame doesn't waver in any draft.",
    R_TRAP:     "The floor looks wrong. Too smooth. The stones are too evenly placed.",
    R_BOSS:     "The chamber opens wider than any other. Something large has been waiting here for a long time.",
    R_EXIT:     "Light from a crack above. A rope. The way out.",
}

# Special shrine room description if player has the flame-mark from the Oakhaven shrine
SHRINE_ROOM_SEALED    = "An alcove with a single candle. Ancient Aeridorian script. A circular seal in the stone — *three flames intertwined*. It feels like it's waiting for something."
SHRINE_ROOM_UNLOCKED  = "An alcove with a single candle. The seal glows faintly when you approach. Your hand finds the groove naturally. Something inside the stone shifts."
SHRINE_ROOM_COMPLETED = "An alcove with a single candle. The seal is dark now — whatever was stored here has been given."

DIRECTIONS = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}

DUNGEON_DIR = os.path.join("memory", "ttrpg", "dungeons")


def _key(x, y): return f"{x},{y}"
def _in_bounds(x, y): return 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE


def _bfs_distances(sx, sy, connections):
    from collections import deque
    dist = {_key(sx, sy): 0}
    q = deque([(sx, sy)])
    while q:
        cx, cy = q.popleft()
        for d in connections.get(_key(cx, cy), []):
            dx, dy = DIRECTIONS[d]
            nx, ny = cx + dx, cy + dy
            nk = _key(nx, ny)
            if nk not in dist:
                dist[nk] = dist[_key(cx, cy)] + 1
                q.append((nx, ny))
    return dist


def _roll_room_type(dist: int) -> str:
    weights = ROOM_WEIGHTS if dist < 3 else [
        (R_EMPTY, 8), (R_MONSTER, 55), (R_TREASURE, 18), (R_SHRINE, 5), (R_TRAP, 14)
    ]
    total = sum(w for _, w in weights)
    r = secrets.randbelow(total)
    cum = 0
    for rt, w in weights:
        cum += w
        if r < cum:
            return rt
    return R_EMPTY


def _pick_monster(room_type: str, difficulty: int) -> str:
    if room_type == R_BOSS:
        pool = BOSS_POOLS.get(difficulty, BOSS_POOLS[1])
        return pool[secrets.randbelow(len(pool))]
    pool = MONSTER_POOLS.get(difficulty, MONSTER_POOLS[1])
    return pool[secrets.randbelow(len(pool))]


def generate_dungeon(difficulty: int = 1, player_level: int = 1) -> dict:
    sx, sy = START_POS
    visited = {(sx, sy)}
    connections: Dict[str, List[str]] = {_key(sx, sy): []}
    all_positions = [(sx, sy)]
    frontier = [(sx, sy)]
    target = secrets.randbelow(4) + 9  # 9-12 rooms

    while len(all_positions) < target and frontier:
        cx, cy = frontier[secrets.randbelow(len(frontier))]
        dirs = list(DIRECTIONS.keys())
        for i in range(len(dirs) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            dirs[i], dirs[j] = dirs[j], dirs[i]

        moved = False
        for d in dirs:
            dx, dy = DIRECTIONS[d]
            nx, ny = cx + dx, cy + dy
            if _in_bounds(nx, ny) and (nx, ny) not in visited:
                visited.add((nx, ny))
                all_positions.append((nx, ny))
                ck, nk = _key(cx, cy), _key(nx, ny)
                connections.setdefault(ck, []).append(d)
                connections.setdefault(nk, []).append(DIR_OPPOSITE[d])
                frontier.append((nx, ny))
                moved = True
                break
        if not moved and (cx, cy) in frontier:
            frontier.remove((cx, cy))

    distances = _bfs_distances(sx, sy, connections)
    farthest = max(all_positions, key=lambda p: distances.get(_key(*p), 0))

    rooms = {}
    boss_assigned = False
    has_secret_shrine = False

    for pos in all_positions:
        x, y = pos
        k = _key(x, y)
        if pos == (sx, sy):
            rt = R_START
        elif pos == farthest and not boss_assigned:
            rt = R_BOSS
            boss_assigned = True
        else:
            rt = _roll_room_type(distances.get(k, 1))

        boss_name = generate_boss_name() if rt == R_BOSS else None

        # One secret shrine per dungeon (chance increases with difficulty)
        is_secret_shrine = (
            rt == R_SHRINE
            and not has_secret_shrine
            and secrets.randbelow(100) < (20 + difficulty * 15)
        )
        if is_secret_shrine:
            has_secret_shrine = True

        rooms[k] = {
            "type": rt,
            "cleared": rt in (R_START, R_EMPTY),
            "monster_key": _pick_monster(rt, difficulty) if rt in (R_MONSTER, R_BOSS) else None,
            "boss_name": boss_name,
            "description": ROOM_DESCRIPTIONS.get(rt, "A stone room."),
            "secret_shrine": is_secret_shrine,
        }

    return {
        "player_pos": list(START_POS),
        "connections": connections,
        "rooms": rooms,
        "visited": [_key(*START_POS)],
        "grid_size": GRID_SIZE,
        "active": True,
        "xp_gained": 0,
        "gil_gained": 0,
        "loot_gained": [],
        "player_level": player_level,
        "difficulty": difficulty,
    }


def render_map(state: dict) -> str:
    size = state["grid_size"]
    px, py = state["player_pos"]
    visited = set(state["visited"])
    rooms = state["rooms"]

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
                row += "░░"  # in dungeon but unseen
            else:
                row += "　　"  # outside dungeon (full-width spaces)
        lines.append(row)
    return "\n".join(lines)


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
