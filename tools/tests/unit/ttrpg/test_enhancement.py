"""Hemlock's rework: an escalating gil sink whose bonus goes through the
existing combat caps and survives unequipping."""
from utils.ttrpg import enhancement as enh
from utils.ttrpg.combat_engine import _compute_player_defense
from utils.ttrpg.equipment_registry import ARMOR, get_equipment


def _sheet(armor_key, gil=10**6):
    return {"gil": gil, "level": 15, "stats": {"dex": 10}, "conditions": [],
            "equipment": {"armor": get_equipment(armor_key)}, "inventory": []}


def test_top_gear_to_plus_five_costs_150k():
    assert sum(enh.cost(20000, n) for n in range(1, 6)) == 150_000
    assert enh.cost(12, 1) == 500                       # the floor still costs something


def test_enhancing_spends_gil_and_raises_defence():
    key = max(ARMOR, key=lambda k: ARMOR[k]["defense_bonus"])
    sheet = _sheet(key)
    before = _compute_player_defense(sheet)
    ok, _ = enh.enhance(sheet, "armor")
    assert ok and sheet["enhancements"][key] == 1 and sheet["gil"] < 10**6
    assert _compute_player_defense(sheet) >= before     # soft-cap and global cap still apply


def test_it_stops_at_plus_five_and_refuses_without_gil():
    key = next(iter(ARMOR))
    sheet = _sheet(key)
    for _ in range(5):
        assert enh.enhance(sheet, "armor")[0]
    ok, text = enh.enhance(sheet, "armor")
    assert not ok and "+5" in text
    poor = _sheet(key, gil=0)
    assert not enh.enhance(poor, "armor")[0] and poor["gil"] == 0


def test_weapon_levels_alternate_attack_and_damage():
    sheet = {"enhancements": {"sword": 5}}
    assert enh.weapon_bonus(sheet, "sword") == (3, 2)
    assert enh.weapon_bonus(sheet, "other") == (0, 0)
