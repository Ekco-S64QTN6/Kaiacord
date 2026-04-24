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
    R_START:       "🏠", R_EMPTY:       "⬛", R_GUARD:       "🛡️",
    R_MONSTER:     "⚔️", R_TREASURE:    "💰", R_SHRINE:      "✨",
    R_TRAP:        "⚡", R_BOSS:        "💀", R_ANTECHAMBER: "🌑",
    R_STAIRS_UP:   "🔼", R_STAIRS_DOWN: "🔽",
    "player":      "🔴", "unknown":     "░░",
}

DIRECTIONS   = {"N": (0, -1), "S": (0, 1), "W": (-1, 0), "E": (1, 0)}
DIR_OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}
SPINE_DIR    = os.path.join("memory", "ttrpg", "dungeons")
GRID_SIZE    = 10

def _key(x, y): return f"{x},{y}"
def _xy(k):     return tuple(int(v) for v in k.split(","))


# ── Floor builder ─────────────────────────────────────────────────────────────

def _build_floor(room_defs, edge_list, floor_num, name, flavor, boss_key,
                 stairs_up_key, stairs_down_key=None):
    """
    Build a floor state dict from compact definitions.

    room_defs: dict of "x,y" -> (type, monster_key, description)
    edge_list: list of ("x1,y1", "x2,y2") pairs (adjacent rooms with passage)
    """
    rooms = {}
    for k, (rtype, mkey, desc) in room_defs.items():
        rooms[k] = {
            "type":        rtype,
            "cleared":     rtype in (R_EMPTY, R_STAIRS_UP, R_STAIRS_DOWN, R_ANTECHAMBER),
            "monster_key": mkey,
            "boss_name":   None,
            "description": desc,
            "is_room":     True,
        }
    # Set boss name
    if boss_key and boss_key in rooms:
        rooms[boss_key]["boss_name"] = room_defs[boss_key][1]  # monster_key as name ref

    # Build bidirectional connections from edges
    connections = {k: [] for k in rooms}
    for a, b in edge_list:
        ax, ay = _xy(a)
        bx, by = _xy(b)
        dx, dy = bx - ax, by - ay
        for d, (ddx, ddy) in DIRECTIONS.items():
            if ddx == dx and ddy == dy:
                if d not in connections[a]: connections[a].append(d)
                opp = DIR_OPPOSITE[d]
                if opp not in connections[b]: connections[b].append(opp)
                break

    return {
        "floor_num":      floor_num,
        "floor_name":     name,
        "floor_flavor":   flavor,
        "boss_key":       boss_key,
        "stairs_up_key":  stairs_up_key,
        "stairs_down_key": stairs_down_key,
        "rooms":          rooms,
        "connections":    connections,
        "grid_size":      GRID_SIZE,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FLOOR 1: THE WORKING TUNNELS
# ══════════════════════════════════════════════════════════════════════════════

_F1_ROOMS = {
    "1,0": (R_STAIRS_UP, None, "Rough-hewn steps lead up to daylight. Guild equipment stacked near the entrance."),
    "1,1": (R_EMPTY,     None, "A mine corridor. Lanterns flicker on iron hooks. Ore cart tracks in the floor."),
    "1,2": (R_EMPTY,     None, "A junction. The rails split. One path goes deeper, one veers west."),
    "0,2": (R_MONSTER,   "bat", "A low-ceilinged alcove. Something screeches in the dark."),
    "2,2": (R_EMPTY,     None, "Timber supports creak overhead. Fresh tool marks on the walls."),
    "3,2": (R_GUARD,     "soldier", "A checkpoint. Ironclad Guild banners nailed to the stone."),
    "2,3": (R_EMPTY,     None, "A sloping passage. The air gets heavier."),
    "1,4": (R_SHRINE,    None, "A miner's shrine — candles, a wooden figure, a prayer scratched into the wall: 'Bring us back up.'"),
    "2,4": (R_EMPTY,     None, "A wide passage. Timber supports every three paces. The rock is wet."),
    "3,4": (R_MONSTER,   "soldier", "Boot prints in the dust. Someone patrols this stretch."),
    "4,4": (R_TREASURE,  None, "A supply cache. Crates marked with the Guild seal, some already pried open."),
    "3,5": (R_EMPTY,     None, "The corridor narrows. You can hear dripping ahead."),
    "3,6": (R_MONSTER,   "road_bandit", "A wider chamber. Bedrolls and cold fire — someone's been living down here."),
    "4,6": (R_TRAP,      None, "The floor looks wrong. Too smooth. A pressure plate under a thin layer of dust."),
    "3,7": (R_EMPTY,     None, "A passage with rubble on one side. Something was sealed here once."),
    "3,8": (R_ANTECHAMBER, None, "A still room. The air is stale. A heavy door ahead, partially open."),
    "4,8": (R_BOSS,      "foreman_kregg", "The foreman's chamber. A desk, a lantern, and a man who doesn't intend to let you pass."),
    "3,9": (R_EMPTY,     None, "Past the foreman's room. The rock changes color here — darker, older."),
    "4,9": (R_STAIRS_DOWN, None, "A rough stairwell descending into darkness. The Guild rails end here. Below is something older."),
}

_F1_EDGES = [
    ("1,0","1,1"), ("1,1","1,2"), ("0,2","1,2"), ("1,2","2,2"),
    ("2,2","3,2"), ("2,2","2,3"), ("2,3","2,4"), ("1,4","2,4"),
    ("2,4","3,4"), ("3,4","4,4"), ("3,4","3,5"), ("3,5","3,6"),
    ("3,6","4,6"), ("3,6","3,7"), ("3,7","3,8"), ("3,8","4,8"),
    ("3,8","3,9"), ("3,9","4,9"),
]

FLOOR_1 = _build_floor(_F1_ROOMS, _F1_EDGES, 1,
    "The Working Tunnels",
    "Active mine workings. Lanterns burn. The Guild doesn't want visitors.",
    "4,8", "1,0", "4,9")


# ══════════════════════════════════════════════════════════════════════════════
# FLOOR 2: THE ABANDONED SECTION
# ══════════════════════════════════════════════════════════════════════════════

_F2_ROOMS = {
    "4,0": (R_STAIRS_UP,   None, "Steps lead back up to the working tunnels. Lantern light above."),
    "4,1": (R_EMPTY,       None, "The timber supports are rotten here. Nobody's maintained this level in years."),
    "3,1": (R_MONSTER,     "skeleton", "Bones scattered on the floor. Some of them are standing."),
    "5,1": (R_EMPTY,       None, "A collapsed side tunnel. Rubble blocks what was once a wider passage."),
    "5,2": (R_MONSTER,     "ghoul", "The stench hits first. Something feeds down here."),
    "4,2": (R_EMPTY,       None, "Old rail tracks rusted into the stone. A miner's helmet, crushed."),
    "3,2": (R_TRAP,        None, "The ceiling sags. One wrong step and it comes down."),
    "4,3": (R_EMPTY,       None, "A junction. Three passages branch out. The air moves differently in each."),
    "3,3": (R_TREASURE,    None, "A sealed supply room. The lock is old but the contents are intact — someone hid provisions."),
    "5,3": (R_MONSTER,     "wight", "A figure stands in the dark. It was a miner once. It isn't anymore."),
    "4,4": (R_GUARD,       "revenant", "A wider chamber with old barricades. Something is still defending this post."),
    "3,4": (R_MONSTER,     "zombie", "A narrow tunnel. Movement in the dark — slow, deliberate, wrong."),
    "4,5": (R_EMPTY,       None, "Aeridorian script appears on the walls. Faint, half-buried under centuries of stone."),
    "5,5": (R_SHRINE,      None, "An alcove with a dim crystal. Not a miner's shrine — older. The three-flame seal is carved above it."),
    "4,6": (R_EMPTY,       None, "The corridor widens. The stone changes — this was carved by different hands."),
    "3,6": (R_MONSTER,     "ghoul", "Feeding sounds echo from the dark. More than one."),
    "4,7": (R_ANTECHAMBER, None, "The passage opens into a vaulted chamber. A figure waits at the far end, swaying."),
    "4,8": (R_BOSS,        "the_unburied", "A miner's lantern still burns on his belt. He died down here. He got back up. He remembers the way out but he can't leave."),
    "4,9": (R_EMPTY,       None, "Past the Unburied. The stone hums faintly. Crystal veins in the walls catch no light."),
    "5,9": (R_STAIRS_DOWN, None, "A carved stairwell — not rough-hewn. Aeridorian craftsmanship. The air below is electric."),
}

_F2_EDGES = [
    ("4,0","4,1"), ("3,1","4,1"), ("4,1","5,1"), ("5,1","5,2"),
    ("4,1","4,2"), ("3,2","4,2"), ("4,2","4,3"), ("3,3","4,3"),
    ("4,3","5,3"), ("4,3","4,4"), ("3,4","4,4"), ("4,4","4,5"),
    ("4,5","5,5"), ("4,5","4,6"), ("3,6","4,6"), ("4,6","4,7"),
    ("4,7","4,8"), ("4,8","4,9"), ("4,9","5,9"),
]

FLOOR_2 = _build_floor(_F2_ROOMS, _F2_EDGES, 2,
    "The Abandoned Section",
    "Old workings. Rotten timber. The miners who died here didn't all stay dead.",
    "4,8", "4,0", "5,9")


# ══════════════════════════════════════════════════════════════════════════════
# FLOOR 3: THE RESONANCE VEIN
# ══════════════════════════════════════════════════════════════════════════════

_F3_ROOMS = {
    "2,0": (R_STAIRS_UP,   None, "Steps back to the abandoned section. The air above smells of rot."),
    "2,1": (R_EMPTY,       None, "Crystal formations jut from the walls. They absorb light rather than reflect it."),
    "1,1": (R_MONSTER,     "crystelle", "A crystalline construct activates as you enter. Still running its thousand-year-old orders."),
    "3,1": (R_MONSTER,     "gargoyle", "Stone wings unfold from the ceiling. It was waiting."),
    "2,2": (R_EMPTY,       None, "The air hums. You feel it in your teeth, your bones. This is what Rook saw."),
    "2,3": (R_GUARD,       "golem", "A construct blocks the passage. Too large to go around."),
    "1,3": (R_TREASURE,    None, "A crystal alcove. Aeridorian tools — still functional, still warm to the touch."),
    "3,3": (R_TRAP,        None, "A resonance node. The crystal pulses — step wrong and it discharges."),
    "2,4": (R_EMPTY,       None, "The vein opens into a cathedral-like cavern. Crystal pillars hold the ceiling."),
    "1,4": (R_MONSTER,     "aeridorian_soldier", "It still holds formation. It still remembers orders. It thinks you're an intruder. It's right."),
    "3,4": (R_MONSTER,     "crystelle", "Another construct. The crystals are its eyes. They track you."),
    "2,5": (R_SHRINE,      None, "A resonance shrine. The three-flame seal pulses with light. The crystal responds to those who've studied it."),
    "2,6": (R_EMPTY,       None, "A narrowing passage. The crystal veins converge ahead."),
    "1,6": (R_MONSTER,     "gargoyle", "Stone sentries flank the passage. One of them isn't stone anymore."),
    "3,6": (R_TREASURE,    None, "A crystal node that has partially shattered. Shards of enormous value lie scattered."),
    "2,7": (R_ANTECHAMBER, None, "The convergence point. Every crystal vein in the floor leads to the chamber ahead."),
    "2,8": (R_BOSS,        "resonance_warden", "An Aeridorian construct of pure crystal. It was built to protect this vein. It has been doing so for a thousand years. It is very good at its job."),
    "2,9": (R_EMPTY,       None, "Past the Warden. The crystal dims. Something sealed waits below."),
    "3,9": (R_STAIRS_DOWN, None, "An Aeridorian lift shaft. The mechanisms still work. Far below, ancient light."),
}

_F3_EDGES = [
    ("2,0","2,1"), ("1,1","2,1"), ("2,1","3,1"), ("2,1","2,2"),
    ("2,2","2,3"), ("1,3","2,3"), ("2,3","3,3"), ("2,3","2,4"),
    ("1,4","2,4"), ("2,4","3,4"), ("2,4","2,5"), ("2,5","2,6"),
    ("1,6","2,6"), ("2,6","3,6"), ("2,6","2,7"), ("2,7","2,8"),
    ("2,8","2,9"), ("2,9","3,9"),
]

FLOOR_3 = _build_floor(_F3_ROOMS, _F3_EDGES, 3,
    "The Resonance Vein",
    "Crystal formations that absorb light. The air hums at a frequency felt in bone. Constructs still guard what Aeridor left behind.",
    "2,8", "2,0", "3,9")


# ══════════════════════════════════════════════════════════════════════════════
# FLOOR 4: THE SEALED VAULT
# ══════════════════════════════════════════════════════════════════════════════

_F4_ROOMS = {
    "5,0": (R_STAIRS_UP,   None, "The lift shaft back to the Resonance Vein. Crystal light above."),
    "5,1": (R_EMPTY,       None, "Ancient corridors. Aeridorian architecture — walls at angles that shouldn't hold but have for a millennium."),
    "4,1": (R_MONSTER,     "iron_golem", "A construct of black iron. Slow. Deliberate. It fills the corridor."),
    "6,1": (R_MONSTER,     "spectral_knight", "A spectral figure in ancient armor. It salutes you before it attacks."),
    "5,2": (R_EMPTY,       None, "Mining equipment scattered — picks, ropes, a shattered lantern. The missing party came through here."),
    "5,3": (R_GUARD,       "dark_knight", "An armored figure blocks an archway. It hasn't moved in centuries. It moves now."),
    "4,3": (R_TRAP,        None, "Aeridorian ward-stones. The glyphs glow when you approach. This was not meant to be walked through."),
    "6,3": (R_TREASURE,    None, "The missing party's supply cache. Gear from five miners. No bodies."),
    "5,4": (R_EMPTY,       None, "A vast hall. Pillars carved with Aeridorian script. The ceiling is lost in darkness above."),
    "4,4": (R_MONSTER,     "mind_flayer", "Something reaches for your thoughts before you see it. It has been alone down here for a very long time."),
    "6,4": (R_MONSTER,     "beholder", "An eye opens in the dark. Then more eyes. It has been watching the sealed door for centuries."),
    "5,5": (R_SHRINE,      None, "An Aeridorian prayer chamber. The seal responds to those who carry the flame-mark. The air tastes of ozone."),
    "5,6": (R_EMPTY,       None, "A passage lined with sealed doors. Each bears a different glyph. None will open."),
    "4,6": (R_MONSTER,     "spectral_knight", "Another guardian. This one wears the insignia of a rank that no longer exists."),
    "6,6": (R_MONSTER,     "iron_golem", "Iron construct. Newer than the others — someone repaired this one recently. The Guild?"),
    "5,7": (R_ANTECHAMBER, None, "The final seal. New ironwork bolted over ancient stone. The Guild tried to keep this shut. It didn't work."),
    "5,8": (R_BOSS,        "the_last_of_the_party", "He was the party leader. He found what was sealed. He wasn't strong enough to resist it. His pickaxe is still in his hand. His eyes are not his own."),
    "5,9": (R_EMPTY,       None, "Past the broken seal. The stone itself vibrates. Something vast waits below."),
    "6,9": (R_STAIRS_DOWN, None, "A spiraling descent into raw rock. No Aeridorian craftsmanship here. This was carved by something else."),
}

_F4_EDGES = [
    ("5,0","5,1"), ("4,1","5,1"), ("5,1","6,1"), ("5,1","5,2"),
    ("5,2","5,3"), ("4,3","5,3"), ("5,3","6,3"), ("5,3","5,4"),
    ("4,4","5,4"), ("5,4","6,4"), ("5,4","5,5"), ("5,5","5,6"),
    ("4,6","5,6"), ("5,6","6,6"), ("5,6","5,7"), ("5,7","5,8"),
    ("5,8","5,9"), ("5,9","6,9"),
]

FLOOR_4 = _build_floor(_F4_ROOMS, _F4_EDGES, 4,
    "The Sealed Vault",
    "Ancient Aeridorian infrastructure. New ironwork over old stone. The missing mining party's equipment is here. They are not.",
    "5,8", "5,0", "6,9")


# ══════════════════════════════════════════════════════════════════════════════
# FLOOR 5: THE DEEP RESONANCE
# ══════════════════════════════════════════════════════════════════════════════

_F5_ROOMS = {
    "3,0": (R_STAIRS_UP,   None, "The spiral back to the vault. Relative safety above."),
    "3,1": (R_EMPTY,       None, "Raw stone. The walls pulse with inner light. This place was never meant for human feet."),
    "2,1": (R_MONSTER,     "death_tyrant", "An eye of death, hovering in the resonance field. It has absorbed the energy of this place."),
    "4,1": (R_MONSTER,     "iron_golem", "A construct unlike the others — grown, not built. Crystal and iron fused."),
    "3,2": (R_GUARD,       "aeridorian_guardian", "The final defense construct of Aeridor. Fully operational. It has been waiting."),
    "2,2": (R_TRAP,        None, "Raw resonance discharge. The air itself is weaponized. The stone screams."),
    "4,2": (R_TREASURE,    None, "A crystal formation that has grown around ancient artifacts. They pulse with power."),
    "3,3": (R_EMPTY,       None, "A vast open cavern. The ceiling glows. Crystal pillars rise from a floor that moves like water."),
    "2,3": (R_MONSTER,     "shadow_lich", "A figure of pure shadow. It was an Aeridorian mage once. Now it is a memory that refuses to end."),
    "4,3": (R_MONSTER,     "death_knight_dd", "An armored revenant standing guard over something it can no longer name. It fights with precision."),
    "3,4": (R_SHRINE,      None, "The deepest shrine. The three-flame seal blazes. The resonance here is overwhelming. Something acknowledges you."),
    "3,5": (R_EMPTY,       None, "A passage to the core. The stone flows. The light is alive."),
    "2,5": (R_MONSTER,     "vampire_lord", "A lord of the dark. It came here seeking power. It found it. It can never leave."),
    "4,5": (R_MONSTER,     "mind_flayer", "Thoughts that aren't yours. Images of a civilization at its peak. Then the attack."),
    "3,6": (R_ANTECHAMBER, None, "The threshold. Beyond this door the resonance is absolute. Whatever built this place is still inside."),
    "3,7": (R_BOSS,        "the_bound_architect", "The thing that built this vault. Still here. Still building. It is not Aeridorian — it is what the Aeridorians found and tried to contain. It has been patient. It is finished waiting."),
}

_F5_EDGES = [
    ("3,0","3,1"), ("2,1","3,1"), ("3,1","4,1"), ("3,1","3,2"),
    ("2,2","3,2"), ("3,2","4,2"), ("3,2","3,3"), ("2,3","3,3"),
    ("3,3","4,3"), ("3,3","3,4"), ("3,4","3,5"), ("2,5","3,5"),
    ("3,5","4,5"), ("3,5","3,6"), ("3,6","3,7"),
]

FLOOR_5 = _build_floor(_F5_ROOMS, _F5_EDGES, 5,
    "The Deep Resonance",
    "Raw resonance. The stone moves. Something ancient waits at the center — not dormant, patient.",
    "3,7", "3,0", None)


# ── Floor registry ────────────────────────────────────────────────────────────

FLOORS = {1: FLOOR_1, 2: FLOOR_2, 3: FLOOR_3, 4: FLOOR_4, 5: FLOOR_5}
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
    """Render the spine dungeon floor as an emoji grid."""
    size = state["grid_size"]
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
                row += "░░"
            else:
                row += "\u3000\u3000"  # full-width space
        lines.append(row)
    return "\n".join(lines)


# ── Persistence (separate from procedural dungeons) ───────────────────────────

async def save_spine_dungeon(user_id: str, state: dict):
    def _save():
        os.makedirs(SPINE_DIR, exist_ok=True)
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
    await asyncio.to_thread(_save)


async def load_spine_dungeon(user_id: str) -> Optional[dict]:
    def _load():
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        # Daily respawn check
        today = datetime.date.today().isoformat()
        if data.get("last_respawn_date") != today:
            data = respawn_monsters(data)
            data["last_respawn_date"] = today
            # Save the respawned state
            tmp = path + ".tmp"
            with open(tmp, "w") as fw:
                json.dump(data, fw, indent=2)
            os.replace(tmp, path)
        return data
    return await asyncio.to_thread(_load)


async def clear_spine_dungeon(user_id: str):
    def _clear():
        path = os.path.join(SPINE_DIR, f"{user_id}_spine.json")
        if os.path.exists(path):
            os.remove(path)
    await asyncio.to_thread(_clear)
