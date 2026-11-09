"""Level 1 → 15, played: days per level, fights, deaths, and where the gil came from.

Each simulated character plays a day the way the game allows one: its daily
hunts (5, +1 after a night at the inn), each spent on a hunt or two of them on
a dungeon. At the Aeridor Ruins the dungeon is the Spine, entered from the
deepest floor reached and followed down until the character is too hurt to go
on. Fights run through the real combat engine round by round, with the
overworld and dungeon scaling the game applies; drops are equipped when they
are better for the class and sold when they are not; Hemlock's stock is bought
when it is an upgrade; a hurt character rests at the inn.

Nothing here touches the game's state: world state, weather and the calendar
are neutral, and no sheet is loaded or saved.

    venv/bin/python3 tools/simulation/progression_sim.py              # 5 classes x 3 lives, 90 days
    venv/bin/python3 tools/simulation/progression_sim.py --days 60 --lives 2 --json out.json
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import secrets
import statistics as st
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
os.environ.setdefault("KAIACORD_LOG_FILE", os.devnull)


def _neutral_world():
    """World state, weather and the calendar at rest, so a run measures the rules."""
    from utils.ttrpg import calendar, combat_engine, world_state, encounter_tables, shop
    neutral = copy.deepcopy(world_state.DEFAULT_STATE)
    world_state.load_world_state = lambda: copy.deepcopy(neutral)
    calm = {"key": "clear", "name": "Clear", "desc": "", "emoji": "", "effect": None, "season": "summer"}
    calendar.get_weather = lambda today=None: dict(calm)
    combat_engine.get_weather = calendar.get_weather
    calendar.get_special_day = lambda *a, **k: None
    encounter_tables.get_special_day = calendar.get_special_day
    calendar.weather_mod = lambda *a, **k: None


from utils.ttrpg import progression as prog                                   # noqa: E402
from utils.ttrpg.class_advancement import apply_advanced_class_to_sheet       # noqa: E402
from utils.ttrpg.combat_engine import _resolve_combat                         # noqa: E402
from utils.ttrpg.dice_engine import CLASSES                                   # noqa: E402
from utils.ttrpg.dungeon import (                                             # noqa: E402
    R_BOSS, R_GUARD, R_MONSTER, R_SHRINE, R_TREASURE, LOCATION_DIFFICULTY_BONUS,
    _scale_boss_to_level, generate_dungeon,
)
from utils.ttrpg.encounter_tables import random_encounter                     # noqa: E402
from utils.ttrpg.equipment_registry import (                                  # noqa: E402
    ACCESSORIES, ARMOR, BOOTS, HEADGEAR, WEAPONS,
)
from utils.ttrpg.loot_tables import (                                         # noqa: E402
    DUNGEON_GEAR_CHANCE, get_consumable_loot, get_gear_loot,
)
from utils.ttrpg.monster_registry import get as get_monster                   # noqa: E402
from utils.ttrpg.shop import find_item, get_shop_inventory, get_sell_price, get_buy_price  # noqa: E402
from utils.ttrpg.spine_dungeon import generate_spine_floor, scale_stair_guardian, MAX_FLOOR  # noqa: E402
from utils.ttrpg.world import LOCATION_DATA                                   # noqa: E402

SLOTS = {"weapon": WEAPONS, "armor": ARMOR, "head": HEADGEAR, "boots": BOOTS, "accessory": ACCESSORIES}
STARTER = {
    "Warrior": "hand_axe", "Ranger": "shortbow", "Mage": "wooden_staff",
    "Rogue": "rusty_dagger", "Cleric": "wooden_staff",
}
ADVANCE = {"Warrior": "Shadowknight", "Ranger": "Hunter", "Mage": "Wizard",
           "Rogue": "Shadowblade", "Cleric": "High Priest"}
REST_COST_FN = None          # set by a variant; default reads the game's rule
REST_AT = 0.5                # rest when HP falls under this share
LEAVE_DUNGEON_AT = 0.3
DUNGEON_FROM = 3             # nobody takes a level-1 character into a dungeon twice


def rest_cost(sheet) -> int:
    if REST_COST_FN:
        return REST_COST_FN(sheet)
    try:
        from utils.ttrpg.rpg_recovery_handler import rest_cost as game_rest_cost
        return game_rest_cost(sheet)
    except ImportError:
        return 5


def new_sheet(cls: str) -> dict:
    from utils.ttrpg.rpg_character_creation_handler import STATS_ORDER, assign_rolls
    rolls = []
    for _ in STATS_ORDER:
        d = sorted(secrets.randbelow(6) + 1 for _ in range(4))[1:]
        rolls.append((sum(d), d))
    stats = {s: base + 1 for s, (base, _) in zip(STATS_ORDER, assign_rolls(rolls, CLASSES[cls]))}  # Human +1
    from utils.ttrpg.character_manager import starting_hp
    hp = starting_hp(cls, stats)
    return {
        "user_id": "sim", "character_name": f"Sim {cls}", "class": cls, "advanced_class": "",
        "level": 1, "xp": 0, "gil": 50, "bank_balance": 0, "reputation": 0,
        "hp": {"current": hp, "max": hp}, "stats": stats, "conditions": [],
        "inventory": ["bandage", "healing_herb"],        # the Adventurer's Pack
        "equipment": {"weapon": STARTER[cls], "armor": "leather_armor" if cls != "Mage" else "mages_robe",
                      "head": None, "boots": None, "accessory": None, "offhand": None},
        "location": "whisperwood_edge", "hunt_streak": 0, "hunts_today": 0, "level_flags": {},
    }


def fits(item: dict, sheet: dict) -> bool:
    classes = item.get("classes")
    return not classes or sheet["class"] in classes or sheet.get("advanced_class") in classes


def score(item: dict | None) -> float:
    if not item:
        return 0.0
    s = item.get("attack_bonus", 0) * 2 + item.get("damage_bonus", 0) * 2 + item.get("damage_die", 0) * 0.5
    s += item.get("defense_bonus", 0) * 2 + item.get("hp_bonus", 0) * 0.2
    s += sum(item.get("stat_bonus", {}).values()) * 0.5
    proc = item.get("proc")
    if proc:
        s += proc.get("die", 0) * 0.25
    return s


def slot_of(key: str):
    for slot, reg in SLOTS.items():
        if key in reg:
            return slot
    return None


class Ledger:
    def __init__(self):
        self.earned = Counter()
        self.spent = Counter()

    def earn(self, sheet, source, amount):
        amount = int(amount)
        if amount:
            sheet["gil"] += amount
            self.earned[source] += amount

    def spend(self, sheet, sink, amount):
        amount = int(amount)
        sheet["gil"] -= amount
        self.spent[sink] += amount


def sell_value(key):
    item = find_item(key)
    return get_sell_price(item["value"], 0, 0) if item else 0


def take_drop(sheet, key, ledger: Ledger):
    """Equip an upgrade, sell the rest (the old piece included)."""
    if not key:
        return
    slot = slot_of(key)
    item = SLOTS[slot][key] if slot else None
    if item and fits(item, sheet):
        cur_key = sheet["equipment"].get(slot)
        cur = SLOTS[slot].get(cur_key) if cur_key else None
        if score(item) > score(cur):
            sheet["equipment"][slot] = key
            if cur_key:
                ledger.earn(sheet, "loot sales", sell_value(cur_key))
            return
    ledger.earn(sheet, "loot sales", sell_value(key))


POTIONS = ("potion_standard", "tonic", "bandage", "healing_herb")


def stock_potions(sheet, ledger: Ledger):
    """Keep a few of the best healing item Hemlock sells that the purse allows:
    three, and one more every three levels."""
    want = 3 + sheet["level"] // 3
    have = sum(sheet["inventory"].count(k) for k in POTIONS)
    hemlock = get_shop_inventory("hemlocks_store")[5]
    for key in POTIONS:
        if key not in hemlock:
            continue
        item = find_item(key)
        price = get_buy_price(item, "hemlocks_store")
        while have < want and sheet["gil"] - price >= 20:
            ledger.spend(sheet, "potions", price)
            sheet["inventory"].append(key)
            have += 1


def shop(sheet, ledger: Ledger):
    """Buy the best affordable upgrade per slot from Hemlock, keeping a rest fund."""
    stock = get_shop_inventory("hemlocks_store")[:5]
    for slot, items in zip(SLOTS, stock):
        cur_key = sheet["equipment"].get(slot)
        cur = SLOTS[slot].get(cur_key) if cur_key else None
        best = None
        for key, item in items.items():
            if not fits(item, sheet) or score(item) <= score(cur):
                continue
            price = get_buy_price(find_item(key), "hemlocks_store")
            if price <= sheet["gil"] - 50 and (best is None or score(item) > score(best[1])):
                best = (key, item, price)
        if best:
            ledger.spend(sheet, "shop gear", best[2])
            if cur_key:
                ledger.earn(sheet, "loot sales", sell_value(cur_key))
            sheet["equipment"][slot] = best[0]


def level_up(sheet, stats: dict):
    before = sheet["level"]
    prog.check_level_up(sheet)
    for lvl in range(before + 1, sheet["level"] + 1):
        stats["level_day"].setdefault(lvl, stats["day"])
    while prog.consume_stat_choice(sheet) or sheet.pop("_stat_choice_pending", False):
        primary = CLASSES[sheet["class"]]["primary"]
        sheet["stats"][primary] += 1
    sheet.pop("_stat_choice_levels_pending", None)
    if sheet.pop("_advancement_pending", False) and not sheet.get("advanced_class"):
        apply_advanced_class_to_sheet(sheet, ADVANCE[sheet["class"]])
        sheet["advanced_class"] = ADVANCE[sheet["class"]]


def fight(sheet, monster, stats, ledger: Ledger, *, xp_gil_mult=1, gear_tier=None, gear_chance=None,
          kind="overworld"):
    """One fight to the end. Returns True when the character won."""
    rounds = 0
    start = sheet["hp"]["current"]
    m_start = monster["hp"]["current"]
    fled = False
    while True:
        res = _resolve_combat(sheet, monster)
        sheet, monster = res["sheet"], res["monster"]
        rounds += 1
        if res.get("monster_defeated") or not res.get("player_alive", True) or rounds >= 60:
            break
        # A player watching one round at a time drinks or runs before the end.
        if sheet["hp"]["current"] < sheet["hp"]["max"] * 0.35:
            potion = next((k for k in POTIONS if k in sheet["inventory"]), None)
            if potion:
                sheet["inventory"].remove(potion)
                sheet["hp"]["current"] = min(sheet["hp"]["max"],
                                             sheet["hp"]["current"] + find_item(potion)["hp_restore"])
                stats["potions"] = stats.get("potions", 0) + 1
            elif monster["hp"]["current"] > monster["hp"]["max"] * 0.25:
                fled = True
                break
    stats["fights"] += 1
    stats["rounds"].append(rounds)
    stats.setdefault("dpr", defaultdict(list))[sheet["level"]].append((m_start - monster["hp"]["current"]) / rounds)
    stats.setdefault("mhp", defaultdict(list))[sheet["level"]].append(m_start)
    k = stats.setdefault("kinds", {}).setdefault(kind, defaultdict(lambda: [0, 0, 0, 0.0]))[sheet["level"]]
    k[0] += 1                                             # fights
    stats["hp_lost"].append((start - max(0, sheet["hp"]["current"])) / max(1, sheet["hp"]["max"]))
    k[3] += stats["hp_lost"][-1]
    sheet["conditions"] = [c for c in sheet.get("conditions", []) if c in prog.PERMANENT_CONDITIONS]
    note_outcome(sheet, stats, fled or sheet["hp"]["current"] <= 0 or not res.get("player_alive", True))
    if fled or sheet["hp"]["current"] <= 0 or not res.get("player_alive", True):
        k[1 if fled else 2] += 1                          # fled / died
    if fled:
        stats["fled"] = stats.get("fled", 0) + 1
        sheet["hunt_streak"] = 0
        return False
    if sheet["hp"]["current"] <= 0 or not res.get("player_alive", True):
        stats["deaths"] += 1
        sheet["xp"] = max(0, sheet["xp"] - int(sheet["xp"] * 0.10))
        loss = int(sheet["gil"] * 0.05)
        ledger.spend(sheet, "blackout", loss)
        sheet["hp"]["current"] = 1
        sheet["hunt_streak"] = 0
        return False
    if res.get("monster_defeated"):
        stats["wins"] += 1
        sheet["xp"] += int(monster.get("xp", 10) * xp_gil_mult)
        gil = int(monster.get("gil", 5) * xp_gil_mult)
        sheet["hunt_streak"] = sheet.get("hunt_streak", 0) + 1
        if sheet["hunt_streak"] > 1:
            gil += prog.streak_bonus(gil, sheet["hunt_streak"])
        ledger.earn(sheet, "kill gil", gil)
        from utils.ttrpg.loot_tables import roll_kill_drops, KILL_GEAR_CHANCE
        tier = gear_tier or monster.get("tier", "medium")
        if gear_chance is not None and gear_chance >= 1.0:   # a boss: the guaranteed drop
            gear, cons = get_gear_loot(tier), get_consumable_loot(tier)
        else:
            gear, cons = roll_kill_drops(tier, gear_chance if gear_chance is not None else KILL_GEAR_CHANCE)
        take_drop(sheet, gear, ledger)
        if cons:
            ledger.earn(sheet, "loot sales", sell_value(cons))
        level_up(sheet, stats)
        return True
    return False


ZONES = sorted((loc for loc, ld in LOCATION_DATA.items() if ld.get("hunting")),
               key=lambda loc: LOCATION_DATA[loc].get("recommended_level", 1))


def zone_for(level: int) -> str:
    """The deepest zone the game recommends for this level."""
    best = ZONES[0]
    for loc in ZONES:
        if LOCATION_DATA[loc].get("recommended_level", 1) <= level:
            best = loc
    return best


def choose_zone(sheet, stats) -> str:
    """Where a sensible player goes today: the recommended zone, one back while
    the last fights there went badly (a fifth or more ended in a death or a run)."""
    top = zone_for(sheet["level"])
    recent = stats.setdefault("recent", {}).get(top, [])
    if len(recent) >= 10 and sum(recent[-20:]) / len(recent[-20:]) >= 0.2:
        idx = ZONES.index(top)
        if idx > 0:
            # Come back every few days to see whether the gear has caught up.
            if stats["day"] % 4:
                return ZONES[idx - 1]
            stats["recent"][top] = recent[-5:]
    return top


def note_outcome(sheet, stats, bad: bool):
    stats.setdefault("recent", {}).setdefault(sheet["location"], []).append(1 if bad else 0)


def overworld_monster(loc: str, level: int) -> dict:
    from utils.ttrpg.encounter_tables import scale_overworld_monster
    return scale_overworld_monster(get_monster(random_encounter(loc, level)), level,
                                   LOCATION_DATA[loc].get("dist_mult", 1.0))


def hunt(sheet, stats, ledger):
    loc = sheet["location"]
    density = LOCATION_DATA[loc].get("density", 1)
    n = 1
    if density == 2 and secrets.randbelow(100) < 25:
        n = 2
    elif density == 3:
        r = secrets.randbelow(100)
        n = 3 if r < 15 else 2 if r < 40 else 1
    for _ in range(n):
        if not fight(sheet, overworld_monster(loc, sheet["level"]), stats, ledger):
            return
        maybe_rest(sheet, ledger, stats)


def dungeon_monster(room, state, level):
    from utils.ttrpg.dungeon import scale_dungeon_mob
    m = dict(get_monster(room.get("monster_key") or "goblin"))
    m = _scale_boss_to_level(m, level) if room["type"] == R_BOSS else scale_dungeon_mob(m, state, level)
    m["hp"] = {"current": m["hp"], "max": m["hp"]}
    return m


def run_rooms(sheet, state, stats, ledger) -> bool:
    """Clear a dungeon or Spine floor. True when its boss (or stairs) was reached."""
    from utils.ttrpg.rpg_combat_handler import _dungeon_reward_amounts
    level = sheet["level"]
    rooms = list(state["rooms"].values())
    order = [r for r in rooms if r.get("type") != R_BOSS] + [r for r in rooms if r.get("type") == R_BOSS]
    for room in order:
        t = room.get("type")
        if t in (R_MONSTER, R_GUARD, R_BOSS) and room.get("monster_key"):
            if sheet["hp"]["current"] < sheet["hp"]["max"] * LEAVE_DUNGEON_AT:
                return False
            m = dungeon_monster(room, state, level)
            if state.get("is_spine") and t == R_GUARD:
                pass
            xp, gil = _dungeon_reward_amounts(m, is_boss=(t == R_BOSS), world={})
            before_xp, before_gil = sheet["xp"], sheet["gil"]
            won = fight(sheet, m, stats, ledger, xp_gil_mult=0,
                        kind="spine" if state.get("is_spine") else "dungeon",
                        gear_tier=m.get("tier", "medium"),
                        gear_chance=1.0 if t == R_BOSS else DUNGEON_GEAR_CHANCE)
            if not won:
                return False
            sheet["xp"] += xp
            ledger.earn(sheet, "dungeon kills", gil)
            level_up(sheet, stats)
        elif t == R_TREASURE:
            ledger.earn(sheet, "dungeon treasure", secrets.randbelow(25) + 10)
        elif t == R_SHRINE:
            sheet["hp"]["current"] = min(sheet["hp"]["max"], sheet["hp"]["current"] + sheet["hp"]["max"] // 3)
    return True


def dungeon(sheet, stats, ledger):
    from utils.ttrpg.rpg_combat_handler import _apply_dungeon_completion_rewards
    loc = sheet["location"]
    stats["dungeons"] += 1
    if loc == "aeridor_ruins":
        floor = stats.setdefault("spine_floor", 1)
        while floor <= MAX_FLOOR:
            state = generate_spine_floor(floor, sheet["level"])
            if not state or not run_rooms(sheet, state, stats, ledger):
                break
            floor += 1
            stats["spine_floor"] = max(stats["spine_floor"], floor)
        return
    from utils.ttrpg.dungeon import dungeon_difficulty
    diff = dungeon_difficulty(sheet["level"], loc)
    state = generate_dungeon(diff, player_level=sheet["level"], location=loc)
    if run_rooms(sheet, state, stats, ledger):
        before = sheet["gil"]
        _apply_dungeon_completion_rewards(sheet, state)
        ledger.earned["dungeon completion"] += sheet["gil"] - before
        level_up(sheet, stats)


def maybe_rest(sheet, ledger, stats):
    if sheet["hp"]["current"] < sheet["hp"]["max"] * REST_AT:
        cost = rest_cost(sheet)
        if sheet["gil"] >= cost:
            ledger.spend(sheet, "inn", cost)
            sheet["hp"]["current"] = sheet["hp"]["max"]
            stats["rests"] += 1


def play_day(sheet, stats, ledger, policy):
    hunts = prog.MAX_HUNTS_PER_DAY + 1          # rested the night before
    if sheet.get("advanced_class") == "Ranger":
        hunts += 1
    sheet["location"] = choose_zone(sheet, stats)
    shop(sheet, ledger)
    stock_potions(sheet, ledger)
    sheet["hp"]["current"] = sheet["hp"]["max"]
    ledger.spend(sheet, "inn", rest_cost(sheet))
    while hunts > 0:
        if policy == "dungeon" and hunts >= 2 and sheet["level"] >= DUNGEON_FROM:
            hunts -= 2
            dungeon(sheet, stats, ledger)
        else:
            hunts -= 1
            hunt(sheet, stats, ledger)
        maybe_rest(sheet, ledger, stats)
        if sheet["hp"]["current"] <= 1:
            ledger.spend(sheet, "inn", min(sheet["gil"], rest_cost(sheet)))
            sheet["hp"]["current"] = sheet["hp"]["max"]


def life(cls, days, policy):
    sheet = new_sheet(cls)
    ledger = Ledger()
    stats = {"day": 0, "level_day": {1: 0}, "fights": 0, "wins": 0, "deaths": 0, "rounds": [],
             "hp_lost": [], "rests": 0, "dungeons": 0, "by_level": {}}
    for day in range(1, days + 1):
        stats["day"] = day
        lvl = sheet["level"]
        f0, d0, e0 = stats["fights"], stats["deaths"], sum(ledger.earned.values())
        fl0 = stats.get("fled", 0)
        xp0 = prog.XP_THRESHOLDS.get(sheet["level"], 0) + sheet["xp"] - prog.XP_THRESHOLDS.get(sheet["level"], 0)
        r0, h0 = len(stats["rounds"]), len(stats["hp_lost"])
        play_day(sheet, stats, ledger, policy)
        b = stats["by_level"].setdefault(lvl, {"days": 0, "fights": 0, "deaths": 0, "earned": 0,
                                               "rounds": [], "hp_lost": []})
        b["days"] += 1
        b["fights"] += stats["fights"] - f0
        b["deaths"] += stats["deaths"] - d0
        b["fled"] = b.get("fled", 0) + stats.get("fled", 0) - fl0
        b["xp"] = b.get("xp", 0) + sheet["xp"] - xp0
        b["earned"] += sum(ledger.earned.values()) - e0
        b["rounds"] += stats["rounds"][r0:]
        b["hp_lost"] += stats["hp_lost"][h0:]
    stats["final"] = {"level": sheet["level"], "gil": sheet["gil"], "equipment": dict(sheet["equipment"])}
    return stats, ledger


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--lives", type=int, default=3, help="characters per class")
    ap.add_argument("--policy", choices=("dungeon", "hunt"), default="dungeon")
    ap.add_argument("--classes", default="Warrior,Ranger,Mage,Rogue,Cleric")
    ap.add_argument("--json", help="write the summary here")
    args = ap.parse_args(argv)
    _neutral_world()

    results = []
    for cls in args.classes.split(","):
        for _ in range(args.lives):
            results.append((cls, *life(cls, args.days, args.policy)))

    level_days = defaultdict(list)
    per_level = defaultdict(lambda: {"days": 0, "fights": 0, "deaths": 0, "fled": 0, "earned": 0, "rounds": [], "hp": []})
    earned, spent = Counter(), Counter()
    for cls, stats, ledger in results:
        for lvl, d in stats["level_day"].items():
            level_days[lvl].append(d)
        for lvl, b in stats["by_level"].items():
            p = per_level[lvl]
            p["days"] += b["days"]; p["fights"] += b["fights"]; p["deaths"] += b["deaths"]
            p["fled"] += b.get("fled", 0)
            p["xp"] = p.get("xp", 0) + b.get("xp", 0)
            p["earned"] += b["earned"]; p["rounds"] += b["rounds"]; p["hp"] += b["hp_lost"]
        earned.update(ledger.earned); spent.update(ledger.spent)

    n = len(results)
    print(f"{n} lives, {args.days} days, policy={args.policy}")
    print("lvl  reached(day, median)  days@lvl  gil/day  fights/day  rounds  hp lost/fight  deaths/100  fled/100")
    summary = {"levels": {}, "earned": {}, "spent": {}, "final": []}
    for lvl in range(1, 16):
        days = level_days.get(lvl, [])
        p = per_level.get(lvl)
        if not p or not p["days"]:
            print(f"{lvl:>3}  {'-' if not days else st.median(days):>8}   (reached by {len(days)}/{n})")
            continue
        row = {
            "reached_day": st.median(days) if days else None, "reached_by": len(days),
            "gil_per_day": p["earned"] / p["days"], "fights_per_day": p["fights"] / p["days"],
            "rounds": st.mean(p["rounds"]) if p["rounds"] else 0,
            "hp_lost": st.mean(p["hp"]) if p["hp"] else 0,
            "deaths_per_100": 100 * p["deaths"] / max(1, p["fights"]),
            "fled_per_100": 100 * p["fled"] / max(1, p["fights"]),
            "xp_per_day": p.get("xp", 0) / p["days"],
            "days_at_level": p["days"] / max(1, len(days)),
        }
        dpr = [x for _, st_, _ in results for x in st_.get("dpr", {}).get(lvl, [])]
        mhp = [x for _, st_, _ in results for x in st_.get("mhp", {}).get(lvl, [])]
        row["dpr"] = st.mean(dpr) if dpr else 0
        row["monster_hp"] = st.mean(mhp) if mhp else 0
        summary["levels"][lvl] = row
        print(f"{lvl:>3}  {row['reached_day']!s:>8} ({len(days)}/{n})  {row['days_at_level']:7.1f}  {row['gil_per_day']:7.0f}"
              f"  {row['fights_per_day']:9.1f}  {row['rounds']:6.1f}  {row['hp_lost']:12.0%}  {row['deaths_per_100']:9.1f}"
              f"  {row['fled_per_100']:7.1f}   dpr {row['dpr']:5.1f} vs hp {row['monster_hp']:5.0f}  xp/day {row['xp_per_day']:6.0f}")
    tot = sum(earned.values()) or 1
    print("\ngil earned by source (all lives):")
    for k, v in earned.most_common():
        print(f"  {k:20} {v / n:10.0f} per life  {v / tot:5.0%}")
        summary["earned"][k] = v / n
    print("gil spent by sink:")
    for k, v in spent.most_common():
        print(f"  {k:20} {v / n:10.0f} per life")
        summary["spent"][k] = v / n
    print("\nby where (fights, fled/100, deaths/100, hp lost) per level:")
    for kind in ("overworld", "dungeon", "spine"):
        cells = []
        for lvl in range(1, 16):
            tot = [0, 0, 0, 0.0]
            for _, st_, _ in results:
                c = st_.get("kinds", {}).get(kind, {}).get(lvl)
                if c:
                    tot = [a + b for a, b in zip(tot, c)]
            if tot[0]:
                cells.append(f"L{lvl}:{tot[0]}/{100*tot[1]/tot[0]:.0f}/{100*tot[2]/tot[0]:.0f}/{tot[3]/tot[0]:.0%}")
        print(f"  {kind:9} " + "  ".join(cells))
    finals = [s["final"] for _, s, _ in results]
    print(f"final: level median {st.median(f['level'] for f in finals)}, "
          f"gil median {st.median(f['gil'] for f in finals):.0f}, max {max(f['gil'] for f in finals)}")
    summary["final"] = finals
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(summary, fh, indent=1, default=str)


if __name__ == "__main__":
    main()
