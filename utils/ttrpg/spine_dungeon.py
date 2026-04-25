"""
The Ironvein Deep — Static Mega Dungeon beneath the Spine of the World.

Completely separate from the procedural dungeon system in dungeon.py.
5 hand-crafted floors with persistent state and daily monster respawn.
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
    R_START:       "🏠", R_EMPTY:       "⬜", R_GUARD:       "🛡️",
    R_MONSTER:     "⚔️", R_TREASURE:    "💰", R_SHRINE:      "✨",
    R_TRAP:        "⚡", R_BOSS:        "💀", R_ANTECHAMBER: "🌑",
    R_STAIRS_UP:   "🔼", R_STAIRS_DOWN: "🔽",
    "player":      "🔴", "unknown":     "░░",
}

DIRECTIONS   = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}
SPINE_DIR    = os.path.join("memory", "ttrpg", "dungeons")
GRID_SIZE    = 15

def _key(x, y): return f"{x},{y}"
def _xy(k):     return tuple(int(v) for v in k.split(","))


# ── Floor builder ─────────────────────────────────────────────────────────────

import os, json

# Load static mega-dungeon layouts
_LAYOUT_FILE = os.path.join(os.path.dirname(__file__), "spine_layouts.json")
with open(_LAYOUT_FILE, "r") as f:
    FLOORS_STR = json.load(f)
    
FLOORS = {int(k): v for k, v in FLOORS_STR.items()}
MAX_FLOOR = 5

FLOOR_LOOT_TIER = {1: 2, 2: 3, 3: 4, 4: 4, 5: 5}


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
        "active":        True,
        "xp_gained":     0,
        "gil_gained":    0,
        "loot_gained":   [],
        "player_level":  player_level,
        "difficulty":    min(5, floor_num + 1),
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
            room["monster_key"] = template["monster_key"]
            room["boss_name"] = template.get("boss_name")
    # Clear active combat on respawn
    state.pop("active_combat", None)
    return state


# ── Map renderer ──────────────────────────────────────────────────────────────

def render_spine_map(state: dict) -> str:
    """Render the spine dungeon floor as a viewport-cropped emoji grid.

    Shows an 11×11 window centered on the player. Named rooms display
    their label letter when unvisited, and their type emoji when visited.
    """
    size = state["grid_size"]
    visited = set(state["visited"])
    rooms = state["rooms"]
    px, py = state["player_pos"]

    # Letter labels → emoji digits for unvisited rooms
    LABEL_EMOJI = {
        "A": "🇦", "B": "🇧", "C": "🇨", "D": "🇩", "E": "🇪",
        "F": "🇫", "G": "🇬", "H": "🇭", "I": "🇮", "J": "🇯",
        "K": "🇰", "L": "🇱", "M": "🇲", "N": "🇳",
    }

    # Viewport: 11×11 centered on player, clamped to grid bounds
    VIEW = 11
    half = VIEW // 2
    vx0 = max(0, min(px - half, size - VIEW))
    vy0 = max(0, min(py - half, size - VIEW))
    vx1 = min(size, vx0 + VIEW)
    vy1 = min(size, vy0 + VIEW)

    lines = []

    # Top edge indicator
    if vy0 > 0:
        lines.append("  " * (VIEW // 2) + "⬆️")

    for y in range(vy0, vy1):
        row = ""
        for x in range(vx0, vx1):
            k = _key(x, y)
            if [x, y] == state["player_pos"]:
                row += "🔴"
            elif k in visited:
                rm = rooms.get(k, {})
                rt = rm.get("type", R_EMPTY)
                if rm.get("cleared"):
                    # Show type emoji for cleared rooms (so the map is readable)
                    if rm.get("is_room"):
                        row += ROOM_EMOJIS.get(rt, "⬜")
                    else:
                        row += "⬜"  # corridor
                else:
                    row += ROOM_EMOJIS.get(rt, "⬜")
            elif k in rooms:
                rm = rooms[k]
                label = rm.get("label")
                if label and label in LABEL_EMOJI:
                    row += LABEL_EMOJI[label]
                elif rm.get("is_room"):
                    row += "░░"
                else:
                    row += "▫️"  # unvisited corridor
            else:
                row += "⬛"
        lines.append(row)

    # Bottom edge indicator
    if vy1 < size:
        lines.append("  " * (VIEW // 2) + "⬇️")

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
                active_fnum = "1"
                
        state = container["floors"].get(active_fnum)
        
        if not state:
            return None
            
        state["active"] = container["active"]
        state["last_respawn_date"] = container["last_respawn_date"]
        
        if target_floor is None and not container.get("active") and active_fnum == "1":
            from utils.ttrpg.spine_dungeon import _xy
            state["player_pos"] = list(_xy(state["stairs_up_key"]))
            state["active"] = True
            
        return state
    return await asyncio.to_thread(_load)


async def clear_spine_dungeon(user_id: str):
    def _clear():
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        if os.path.exists(path):
            os.remove(path)
    await asyncio.to_thread(_clear)
