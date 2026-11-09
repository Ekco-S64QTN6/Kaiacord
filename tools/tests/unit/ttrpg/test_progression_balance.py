"""The November 2026 progression and economy pass, rule by rule.

Each number here was set from tools/simulation/progression_sim.py; the tests
hold the shape of the rule, so a later retune changes a constant, not a test.
"""
import secrets

import pytest

from utils.ttrpg import encounter_tables as et
from utils.ttrpg.progression import XP_THRESHOLDS

TIERS = ["trivial", "easy", "medium", "hard", "deadly", "boss"]


def _zone_levels():
    from utils.ttrpg.world import LOCATION_DATA
    return {ld["recommended_level"] for ld in LOCATION_DATA.values()
            if ld.get("hunting") and ld.get("recommended_level", 1) > 1}


def test_a_level_up_moves_at_most_one_bound_of_the_encounter_tiers_and_never_with_a_new_zone():
    zones = _zone_levels()
    for level in range(2, 16):
        before = [TIERS.index(t) for t in et.tier_window(level - 1)]
        after = [TIERS.index(t) for t in et.tier_window(level)]
        moved = sum(a != b for a, b in zip(before, after))
        assert moved <= 1, (level, before, after)
        assert all(a - b <= 1 for a, b in zip(after, before)), (level, "a bound jumped two tiers")
        if level in zones:
            assert moved == 0, f"level {level} opens a zone and a tier at once"


def test_an_overworld_monster_is_capped_to_the_players_level():
    deadly = {"name": "Big", "hp": 200, "attack": 30, "defense": 12, "tier": "deadly"}
    for level in (1, 4, 7, 10, 15):
        m = et.scale_overworld_monster(deadly, level, dist_mult=1.5)
        assert m["hp"]["max"] == et.overworld_hp_cap(level)
        assert m["attack"] <= int(level * 1.5 + 2)
    small = et.scale_overworld_monster({"hp": 10, "attack": 2, "defense": 10}, 15, 1.0)
    assert small["hp"] == {"current": 10, "max": 10}                    # a cap, not a floor


def test_the_hunt_uses_the_shared_overworld_scaling():
    import inspect
    from utils.ttrpg import rpg_combat_handler
    src = inspect.getsource(rpg_combat_handler._handle_hunt)
    assert "scale_overworld_monster(" in src and "math.log(dist_mult)" not in src


def test_a_new_characters_best_roll_is_its_main_stat_and_the_next_its_con():
    from utils.ttrpg.dice_engine import CLASSES
    from utils.ttrpg.rpg_character_creation_handler import STATS_ORDER, assign_rolls
    rolls = [(8, [2, 3, 3]), (17, [5, 6, 6]), (11, [3, 4, 4]), (15, [4, 5, 6]), (9, [3, 3, 3]), (12, [4, 4, 4])]
    for cls, info in CLASSES.items():
        out = dict(zip(STATS_ORDER, (base for base, _ in assign_rolls(rolls, info))))
        assert out[info["primary"]] == 17 and out["con"] == 15, cls
        assert sorted(out.values()) == sorted(base for base, _ in rolls)   # nothing invented or lost
    assert assign_rolls(rolls, {}) == rolls                               # no class info: as rolled


def test_level_one_hp_is_two_hit_dice_plus_con():
    from utils.ttrpg.character_manager import starting_hp
    stats = {"con": 14}
    assert starting_hp("Warrior", stats) == 22 and starting_hp("Mage", stats) == 14


def test_a_kill_rolls_the_loot_tables_only_on_its_drop_chance(monkeypatch):
    from utils.ttrpg import loot_tables as lt
    assert lt.roll_kill_drops("deadly", gear_chance=0.0)[0] is None
    monkeypatch.setattr(lt, "KILL_CONSUMABLE_CHANCE", 0.0)
    assert lt.roll_kill_drops("deadly", gear_chance=0.0) == (None, None)
    got = sum(1 for _ in range(4000) if lt.roll_kill_drops("deadly")[0])
    assert abs(got / 4000 - lt.KILL_GEAR_CHANCE) < 0.04


def test_the_overworld_kill_and_dungeon_mobs_roll_through_the_gate():
    import inspect
    from utils.ttrpg import rpg_combat_handler as h
    assert "roll_kill_drops(" in inspect.getsource(h._handle_attack)
    assert "roll_kill_drops(tier, DUNGEON_GEAR_CHANCE)" in inspect.getsource(h._roll_dungeon_loot)


def test_hemlock_sells_tier_two_and_the_caravan_tier_three():
    from utils.ttrpg.equipment_registry import (
        HEMLOCK_STOCK_WEAPONS, HEMLOCK_STOCK_ARMOR, HEMLOCK_STOCK_CONSUMABLES, get_caravan_stock,
    )
    from utils.ttrpg.shop import find_item
    tiers = {find_item(k)["tier"] for k in HEMLOCK_STOCK_WEAPONS + HEMLOCK_STOCK_ARMOR}
    assert tiers == {1, 2}
    assert not any(find_item(k).get("droppable_only") for k in HEMLOCK_STOCK_WEAPONS)
    assert "potion_standard" in HEMLOCK_STOCK_CONSUMABLES
    gear, consumables = get_caravan_stock()
    assert {find_item(k)["tier"] for k in gear} == {3}
    assert "hi_potion" in consumables


def test_the_shop_menu_fits_every_class_by_listing_what_it_can_wear():
    from utils.ttrpg.rpg_views import _wearable
    from utils.ttrpg.shop import get_shop_inventory
    gear = [item for stock in get_shop_inventory("hemlocks_store")[:5] for item in stock.values()]
    for cls in ("Warrior", "Ranger", "Mage", "Rogue", "Cleric"):
        assert sum(_wearable(i, {"class": cls}) for i in gear) <= 50, cls      # two 25-option menus
    staff = {"classes": ["Mage", "Cleric"]}
    assert _wearable(staff, {"class": "Mage"}) and not _wearable(staff, {"class": "Warrior"})
    assert _wearable(staff, {"class": "Warrior", "advanced_class": "Mage"})


def test_a_night_at_the_inn_costs_more_as_a_character_grows():
    from utils.ttrpg.rpg_recovery_handler import rest_cost
    assert rest_cost({"level": 1}) == 5 and rest_cost({"level": 15}) == 33


def test_selling_returns_a_fifth_of_value_and_reputation_adds_a_little(monkeypatch):
    from utils.ttrpg import shop, world_state
    monkeypatch.setattr(world_state, "load_world_state", lambda: {"shop_price_mult": 1.0})
    assert shop.get_sell_price(1000) == 200
    assert shop.get_sell_price(1000, reputation=100) == 300


def test_spine_mobs_scale_with_the_floor_not_as_the_deepest_one():
    from utils.ttrpg.dungeon import scale_dungeon_mob, spine_scaling_difficulty
    assert [spine_scaling_difficulty(f) for f in (1, 19, 20, 40, 60, 77)] == [2, 2, 3, 4, 5, 5]
    rat = {"hp": 40, "attack": 5, "defense": 12}
    shallow = scale_dungeon_mob(rat, {"is_spine": True, "difficulty": 5, "floor_num": 1}, 7)
    deep = scale_dungeon_mob(rat, {"is_spine": True, "difficulty": 5, "floor_num": 70}, 7)
    assert shallow["defense"] < deep["defense"]


def test_a_dungeon_mob_is_bounded_by_the_players_level():
    from utils.ttrpg.dungeon import DUNGEON_LEVEL_HP_SHARE, scale_dungeon_mob
    brute = {"hp": 500, "attack": 40, "defense": 10}
    m = scale_dungeon_mob(brute, {"difficulty": 2}, 5)
    assert m["hp"] == int(et.overworld_hp_cap(5) * DUNGEON_LEVEL_HP_SHARE)
    assert m["attack"] == int(5 * 1.5 + 2)


def test_dungeon_difficulty_steps_a_level_after_each_zone_opens():
    from utils.ttrpg.dungeon import dungeon_difficulty
    steps = [lvl for lvl in range(2, 16)
             if dungeon_difficulty(lvl, "whisperwood_deep") != dungeon_difficulty(lvl - 1, "whisperwood_deep")]
    assert steps == [5, 8, 11] and not set(steps) & _zone_levels()


def test_each_level_costs_more_xp_than_the_last():
    steps = [XP_THRESHOLDS[l + 1] - XP_THRESHOLDS[l] for l in range(1, 15)]
    assert all(b > a for a, b in zip(steps, steps[1:])), steps


def test_the_simulator_plays_a_few_days(tmp_path):
    """Run as its own process: it neutralises world state by patching modules."""
    import pathlib, subprocess, sys, json
    root = pathlib.Path(__file__).resolve().parents[4]
    out = tmp_path / "sim.json"
    done = subprocess.run(
        [sys.executable, "tools/simulation/progression_sim.py", "--days", "3", "--lives", "1",
         "--classes", "Warrior,Mage", "--json", str(out)],
        cwd=root, capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    summary = json.loads(out.read_text())
    assert summary["levels"] and summary["earned"]
