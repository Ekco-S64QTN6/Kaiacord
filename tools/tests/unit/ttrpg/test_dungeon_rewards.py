"""The dungeon kill's reward helpers, split out of _dungeon_combat_round (#45).

The expected numbers were computed with the inline code these helpers
replaced, on inputs chosen so every int() truncation matters: a change of
order changes them."""
from unittest.mock import patch

from utils.ttrpg import rpg_combat_handler as rch

MONSTER = {"xp": 37, "gil": 19}


def test_dungeon_reward_order_is_pinned():
    assert rch._dungeon_reward_amounts(MONSTER, is_boss=False, world={}) == (37, 19)
    assert rch._dungeon_reward_amounts(
        MONSTER, is_boss=True, world={"xp_mult": 1.3, "gil_mult": 1.1},
        special_day={"buff": "remembrance", "buff_value": 1.5},
        adv_bonuses={"xp_bonus_pct": 0.15, "forest_xp_bonus": 0.1, "gil_bonus_pct": 0.07},
        in_forest=True, spent_buffs=("golden_tongue",), xp_boosted=True,
        pet={"gil_bonus_pct": 0.2, "xp_bonus_pct": 0.1}) == (248, 64)
    assert rch._dungeon_reward_amounts(
        MONSTER, is_boss=False, world={"gil_mult": 1.25},
        special_day={"buff": "harvest_strength", "buff_value": 0.3}, adv_bonuses={},
        spent_buffs=("golden_tongue",), pet={"gil_bonus_pct": 0.2}) == (37, 45)


def test_forest_bonus_applies_only_in_the_forest():
    adv = {"forest_xp_bonus": 0.5}
    inside = rch._dungeon_reward_amounts(MONSTER, is_boss=False, world={}, adv_bonuses=adv, in_forest=True)
    outside = rch._dungeon_reward_amounts(MONSTER, is_boss=False, world={}, adv_bonuses=adv, in_forest=False)
    assert inside[0] > outside[0] == 37


def test_victory_hp_effects_keep_their_order_and_once_a_day_flags():
    sheet = {"hp": {"current": 5, "max": 20}}
    rch._apply_victory_hp_effects(sheet, {"buff": "winter_resolve", "buff_value": 5},
                                  {"heal_on_combat_end": 3}, True)
    assert sheet["hp"] == {"current": 13, "max": 25} and sheet["_winter_resolve_applied"]
    rch._apply_victory_hp_effects(sheet, {"buff": "winter_resolve", "buff_value": 5}, None, True)
    assert sheet["hp"] == {"current": 13, "max": 25}               # once only
    knocked = {"hp": {"current": 0, "max": 20}}
    rch._apply_victory_hp_effects(knocked, {"buff": "long_fire", "buff_value": 4},
                                  {"heal_on_combat_end": 3}, False)
    assert knocked["hp"]["current"] == 0                            # no heal for the fallen


def test_grant_drop_respects_the_bag(monkeypatch):
    from utils.ttrpg import character_manager
    monkeypatch.setattr(character_manager, "INVENTORY_LIMIT", 2)
    monkeypatch.setattr(rch, "find_item", lambda key: {"name": key.title()})
    sheet, state = {"inventory": ["a"]}, {}
    assert rch._grant_drop(sheet, state, "b", "⚔️") == "⚔️ B"
    assert sheet["inventory"] == ["a", "b"] and state["loot_gained"] == ["b"]
    assert rch._grant_drop(sheet, state, "c", "🧪").startswith("🎒 **[Inventory Full]**")
    assert sheet["inventory"] == ["a", "b"] and state["loot_gained"] == ["b"]
    assert rch._grant_drop(sheet, state, "a", "⚔️") == "⚔️ A"     # a stack of what is held fits


def test_a_boss_that_drops_nothing_pays_gil():
    sheet, state = {"inventory": [], "gil": 10}, {}
    with patch("utils.ttrpg.loot_tables.get_gear_loot", return_value=None), \
         patch("utils.ttrpg.loot_tables.get_consumable_loot", return_value=None), \
         patch.object(rch.secrets, "randbelow", return_value=0):
        text = rch._roll_dungeon_loot(sheet, state, "boss", True)
    assert "25 gil" in text and sheet["gil"] == 35 and state["gil_gained"] == 25


def test_a_boss_drop_retries_until_the_table_gives_gear(monkeypatch):
    monkeypatch.setattr(rch, "find_item", lambda key: {"name": key})
    rolls = iter([None, None, "sword"])
    sheet, state = {"inventory": []}, {}
    with patch("utils.ttrpg.loot_tables.get_gear_loot", side_effect=lambda tier: next(rolls, None)), \
         patch("utils.ttrpg.loot_tables.get_consumable_loot", return_value="potion"), \
         patch.object(rch.secrets, "randbelow", return_value=9):     # no second gear
        text = rch._roll_dungeon_loot(sheet, state, "boss", True)
    assert sheet["inventory"] == ["sword", "potion"] and "Boss drops" in text
