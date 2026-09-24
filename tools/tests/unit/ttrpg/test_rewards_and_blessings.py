"""Kill rewards scale with the kill; every blessing does what it says, for a whole fight."""
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.ttrpg import combat_engine as ce
from utils.ttrpg.progression import golden_tongue_bonus, harvest_bonus, streak_bonus

FOREST = Path(__file__).resolve().parents[4] / "utils" / "ttrpg" / "forest_events.py"


def test_every_veiled_blessing_is_read_by_combat():
    """Ten of the fifteen were granted to advanced classes and read nowhere."""
    block = FOREST.read_text(encoding="utf-8").split("class_buffs = {", 1)[1].split("}", 1)[0]
    granted = re.findall(r'\("([a-z_]+)",', block)
    assert len(granted) == 15
    assert set(granted) <= set(ce.ONE_FIGHT_BUFFS)


@pytest.mark.parametrize("gil", [4, 65, 300, 5000])
def test_bonuses_are_a_share_of_the_kill_and_never_less_than_they_were(gil):
    assert harvest_bonus(gil, 0.25) >= 1 and harvest_bonus(gil, 0.25) >= round(gil * 0.25)
    assert streak_bonus(gil, 5) >= 10
    assert golden_tongue_bonus(gil) >= 2
    if gil >= 300:
        assert harvest_bonus(gil, 0.25) >= 75, "the +1 gil autumn bonus, at the level people play"


def _sheet(conditions=(), armor=None, hp=50):
    return {"character_name": "T", "class": "Warrior", "level": 10, "stats": {"str": 16, "dex": 10},
            "hp": {"current": hp, "max": hp}, "conditions": list(conditions),
            "equipment": {"weapon": None, "armor": armor}}


def _monster(hp):
    return {"name": "Skeleton Knight", "defense": 1, "attack": 0, "tier": "trivial",
            "hp": {"current": hp, "max": hp}}


def test_a_blessing_lasts_the_fight_and_is_spent_when_it_ends():
    sheet = _sheet(["battle_focus", "golden_tongue"])
    with patch.object(ce.secrets, "randbelow", return_value=9):     # every die rolls mid: a hit, no crit
        res = ce._resolve_combat(sheet, _monster(10_000))
        assert "battle_focus" in res["sheet"]["conditions"], "spent after one round"
        res = ce._resolve_combat(res["sheet"], _monster(1))
    assert res["monster_defeated"]
    assert not {"battle_focus", "golden_tongue"} & set(res["sheet"]["conditions"])
    assert "golden_tongue" in res["spent_buffs"]


def test_heat_costs_heavy_armor_two_def_once():
    hot = {"effect": {"type": "armor_penalty", "value": -2}}
    with patch.object(ce, "get_weather", return_value=hot):
        plate = ce._compute_player_defense(_sheet(armor="full_plate"))
        leather = ce._compute_player_defense(_sheet(armor="leather_armor"))
    with patch.object(ce, "get_weather", return_value={}):
        plate_cool = ce._compute_player_defense(_sheet(armor="full_plate"))
        leather_cool = ce._compute_player_defense(_sheet(armor="leather_armor"))
    assert plate_cool - plate == 2
    assert leather == leather_cool


def test_the_dawn_task_does_not_also_take_the_heat_off_def():
    src = (Path(__file__).resolve().parents[4] / "utils" / "core" / "background_tasks.py").read_text(encoding="utf-8")
    assert 'state["def_mod"] = state.get("def_mod", 0) + effect_value' not in src
