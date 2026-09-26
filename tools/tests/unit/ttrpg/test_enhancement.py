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


def test_the_sheet_shows_the_rework_combat_uses(monkeypatch):
    import asyncio
    import types
    from utils.ttrpg import rpg_core_handler as core
    from utils.ttrpg.equipment_registry import WEAPONS
    key = max(WEAPONS, key=lambda k: WEAPONS[k]["attack_bonus"])
    base = {"character_name": "T", "user_id": "1", "class": "Warrior", "race": "Human", "level": 15, "xp": 0, "gil": 0,
            "hp": {"current": 10, "max": 10}, "stats": {"str": 10, "dex": 10}, "conditions": [],
            "equipment": {"weapon": key}, "inventory": [], "location": "oakhaven"}
    sent = []

    def render(sheet):
        async def load(_):
            return sheet
        monkeypatch.setattr(core, "load", load)

        async def send(embed=None, **_):
            sent.append(embed)
        msg = types.SimpleNamespace(mentions=[], channel=types.SimpleNamespace(send=send))
        asyncio.run(core._handle_sheet(None, msg, None, "", "1", "T", False))
        return str(sent[-1].to_dict())
    plain = render(dict(base))
    reworked = render(dict(base, enhancements={key: 2}))
    assert f"{WEAPONS[key]['name']} +2" in reworked and f"{WEAPONS[key]['name']} +2" not in plain
    assert plain != reworked.replace(" +2", "")         # the attack figure moved too

