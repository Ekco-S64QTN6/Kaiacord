"""
The Ironvein Deep — Static Mega Dungeon beneath the Spine of the World.

Completely separate from the procedural dungeon system in dungeon.py.
77 floors with persistent state and daily monster respawn.
"""
import secrets
import json
import os
import asyncio
import datetime
from typing import Dict, List, Optional, Tuple

# Reuse room type constants from dungeon.py
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

ROOM_EMOJIS = {
    R_START:       "⬜", R_EMPTY:       "⬜", R_GUARD:       "🟧",
    R_MONSTER:     "🟥", R_TREASURE:    "🟨", R_SHRINE:      "🟪",
    R_TRAP:        "🟫", R_BOSS:        "🟥", R_ANTECHAMBER: "⬜",
    R_STAIRS_UP:   "🟩", R_STAIRS_DOWN: "🟦",
    "player":      "🔴", "unknown":     "🟫",
}

DIRECTIONS   = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}
SPINE_DIR    = os.path.join("memory", "ttrpg", "dungeons")
GRID_SIZE    = 15

def _key(x, y): return f"{x},{y}"
def _xy(k):     return tuple(int(v) for v in k.split(","))


# ── Floor builder ─────────────────────────────────────────────────────────────



# Load static mega-dungeon layouts
_LAYOUT_FILE = os.path.join(os.path.dirname(__file__), "spine_layouts.json")
with open(_LAYOUT_FILE, "r") as f:
    FLOORS_STR = json.load(f)
    
FLOORS = {int(k): v for k, v in FLOORS_STR.items()}
MAX_FLOOR = 77

STAIR_GUARDIANS = {
    1: "foreman_kregg",
    2: "cactuar",
    3: "crypt_stalker",
    4: "lich",
    5: "bone_weaver_spider",
    6: "cave_troll",
    7: "necrophobe",
    8: "forge_fire_elemental",
    9: "behemoth",
    10: "vampire_lord",
    11: "shadow_lich",
    12: "azulmagia",
    13: "antlion",
    14: "dark_rider",
    15: "elara_turned",
    16: "ossuary_golem",
    17: "mind_flayer_outcast",
    18: "dragon",
    19: "tonberry_king",
    20: "slag_horror",
    21: "white_dragon",
    22: "atomos",
    23: "frost_dragon",
    24: "black_dragon",
    25: "green_dragon",
    26: "gilgamesh",
    27: "red_dragon",
    28: "void_stalker",
    29: "blue_dragon",
    30: "shadow_dragon",
    31: "hydra",
    32: "storm_dragon",
    33: "crystal_dragon",
    34: "exdeath_tree",
    35: "great_behemoth",
    36: "iron_golem",
    37: "demogorgon_echo",
    38: "orcus_aspect",
    39: "the_hooded_figure",
    40: "the_first_miner",
    41: "iron_sentinel",
    42: "brass_dragon",
    43: "the_unburied",
    44: "copper_dragon",
    45: "void_dragon",
    46: "silver_dragon",
    47: "aeridor_wyrm",
    48: "bronze_dragon",
    49: "apocalypse",
    50: "king_behemoth",
    51: "death_knight_dd",
    52: "beholder_king",
    53: "abyssal_crawler",
    54: "gold_dragon",
    55: "adamantoise",
    56: "shivan_dragon",
    57: "ancient_red_dragon",
    58: "elder_treant",
    59: "chaos_ff1",
    60: "zeromus_ff4",
    61: "kefka_ascended",
    62: "elder_brain",
    63: "resonance_wraith",
    64: "ancient_white_dragon",
    65: "vorath_chain_devil",
    66: "ancient_black_dragon",
    67: "resonance_warden",
    68: "ancient_green_dragon",
    69: "ancient_blue_dragon",
    70: "shinryu",
    71: "nicol_bolas_echo",
    72: "lord_soth",
    73: "exdeath_ff5",
    74: "aeridorian_guardian",
    75: "malachar_the_undying",
    76: "the_unburied_king",
    77: "the_mountain_heart"
}

# Loot tier scales with depth
def _loot_tier(floor_num):
    if floor_num <= 25: return 3
    if floor_num <= 50: return 4
    return 5

FLOOR_LOOT_TIER = {f: _loot_tier(f) for f in range(1, MAX_FLOOR + 1)}


# ── State generation ──────────────────────────────────────────────────────────

def generate_spine_floor(floor_num: int, player_level: int) -> dict:
    """Generate a playable dungeon state dict for a specific floor."""
    layout = FLOORS.get(floor_num)
    if not layout:
        return None

    # Deep copy rooms so we don't mutate the template
    import copy
    rooms = copy.deepcopy(layout["rooms"])
    connections = copy.deepcopy(layout["connections"])

    stairs_up = layout["stairs_up_key"]
    sx, sy = _xy(stairs_up)

    return {
        "player_pos":    [sx, sy],
        "connections":   connections,
        "rooms":         rooms,
        "visited":       [stairs_up],
        "grid_size":     layout["grid_size"],
        "stairs_up_key": stairs_up,
        "stairs_down_key": layout.get("stairs_down_key"),
        "active":        True,
        "xp_gained":     0,
        "gil_gained":    0,
        "loot_gained":   [],
        "player_level":  player_level,
        "difficulty":    5,  # Spine is endgame L15 — always max difficulty
        "location":      "spine_of_the_world",
        "theme_key":     "spine_deep",
        "theme_name":    layout["floor_name"],
        "theme_emoji":   "⛏️",
        "theme_flavor":  layout["floor_flavor"],
        "layout_name":   "spine_static",
        "boss_key":      layout["boss_key"],
        "floor_num":     floor_num,
        "is_spine":      True,
        "type":          "spine",
    }


# ── Daily respawn ─────────────────────────────────────────────────────────────

def respawn_monsters(state: dict) -> dict:
    """Reset monster/guard/boss rooms. Treasure/shrine stay cleared."""
    floor_num = state.get("floor_num", 1)
    layout = FLOORS.get(floor_num)
    if not layout:
        return state

    for k, room in state["rooms"].items():
        template = layout["rooms"].get(k)
        if not template:
            continue
        if template["type"] in (R_MONSTER, R_GUARD, R_BOSS):
            room["cleared"] = False
            room["monster_key"] = template.get("monster_key")
            room["boss_name"] = template.get("boss_name")
    # Clear active combat on respawn
    state.pop("active_combat", None)
    return state


# ── Map renderer ──────────────────────────────────────────────────────────────

def render_spine_map(state: dict) -> str:
    """Render the spine dungeon floor as a viewport-cropped emoji grid.

    Matches the regular dungeon renderer style:
    🔴 = player, type emoji = visited room, ░░ = unvisited, wall = empty space.
    Uses an 11×11 viewport centered on the player.
    """
    size = state["grid_size"]
    visited = set(state["visited"])
    rooms = state["rooms"]
    px, py = state["player_pos"]

    VIEW = 11
    half = VIEW // 2
    vx0 = max(0, min(px - half, size - VIEW))
    vy0 = max(0, min(py - half, size - VIEW))
    vx1 = min(size, vx0 + VIEW)
    vy1 = min(size, vy0 + VIEW)

    lines = []

    for y in range(vy0, vy1):
        row = ""
        for x in range(vx0, vx1):
            k = _key(x, y)
            if [x, y] == state["player_pos"]:
                row += "🔴"
            elif k in visited:
                rt = rooms.get(k, {}).get("type", R_EMPTY)
                row += ROOM_EMOJIS.get(rt, "⬛")
            elif k in rooms:
                row += "🟫"
            else:
                row += "⬛"   # wall
        lines.append(row)

    floor_num = state.get("floor_num", 1)
    lines.insert(0, f"⛏️ **Floor {floor_num}** — {state.get('theme_name', 'The Ironvein Deep')}")

    return "\n".join(lines)


# ── Persistence (separate from procedural dungeons) ───────────────────────────

async def save_spine_dungeon(user_id: str, state: dict):
    def _save():
        os.makedirs(SPINE_DIR, exist_ok=True)
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        
        container = {}
        if os.path.exists(path):
            with open(path) as f:
                container = json.load(f)
                
        if "floors" not in container:
            container["floors"] = {}
            
        floor_num = str(state["floor_num"])
        container["floors"][floor_num] = state
        
        container["active"] = state.get("active", False)
        container["current_floor"] = state["floor_num"]
        container["last_respawn_date"] = state.get("last_respawn_date", datetime.date.today().isoformat())
        
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(container, f, indent=2)
        os.replace(tmp, path)
    await asyncio.to_thread(_save)


async def load_spine_dungeon(user_id: str, target_floor: int = None) -> Optional[dict]:
    def _load():
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            container = json.load(f)
            
        if "floors" not in container:
            fnum = str(container.get("floor_num", 1))
            container = {
                "active": container.get("active", False),
                "current_floor": container.get("floor_num", 1),
                "last_respawn_date": container.get("last_respawn_date"),
                "floors": {fnum: container}
            }
            
        today = datetime.date.today().isoformat()
        if container.get("last_respawn_date") != today:
            for fn, floor_state in container["floors"].items():
                container["floors"][fn] = respawn_monsters(floor_state)
            container["last_respawn_date"] = today
            tmp = path + ".tmp"
            with open(tmp, "w") as fw:
                json.dump(container, fw, indent=2)
            os.replace(tmp, path)

        if target_floor is not None:
            active_fnum = str(target_floor)
        else:
            if container.get("active"):
                active_fnum = str(container.get("current_floor", 1))
            else:
                return None
                
        state = container["floors"].get(active_fnum)
        
        if not state:
            return None
            
        state["active"] = container["active"]
        state["last_respawn_date"] = container["last_respawn_date"]
        
        layout = FLOORS.get(int(active_fnum))
        if layout:
            if "stairs_up_key" not in state:
                state["stairs_up_key"] = layout.get("stairs_up_key")
            if "stairs_down_key" not in state:
                state["stairs_down_key"] = layout.get("stairs_down_key")
        

        return state
    return await asyncio.to_thread(_load)


async def clear_spine_dungeon(user_id: str):
    def _clear():
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        if os.path.exists(path):
            os.remove(path)
    await asyncio.to_thread(_clear)
