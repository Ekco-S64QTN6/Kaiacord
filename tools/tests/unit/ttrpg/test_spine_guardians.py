"""Floor-scaled progression gates for the Spine's 77 stair guardians."""
import copy
from unittest.mock import patch

import pytest

from utils.ttrpg import combat_engine
from utils.ttrpg.monster_registry import MONSTERS, get as get_monster
from utils.ttrpg.progression import XP_THRESHOLDS
from utils.ttrpg.spine_dungeon import (
    MAX_FLOOR,
    STAIR_GUARDIANS,
    scale_stair_guardian,
)


@pytest.mark.parametrize("floor_num", [1, 15, 33, 52, 67, 77])
def test_guardian_stats_exceed_the_same_monsters_ordinary_floor_encounter(floor_num):
    guardian_key = STAIR_GUARDIANS[floor_num]
    original = get_monster(guardian_key)
    registry_before = copy.deepcopy(MONSTERS[guardian_key])

    guardian = scale_stair_guardian(original, floor_num)

    # The comparison is the ordinary difficulty-5 Spine room path:
    # 1.6x base stats, then the documented floor HP/ATK caps.
    floor_hp_cap = 80 + floor_num * 3
    floor_atk_cap = min(12 + floor_num // 5, int(max(XP_THRESHOLDS) * 1.5 + 2))
    ordinary_hp = min(int(original["hp"] * 1.6), floor_hp_cap)
    ordinary_attack = min(int(original["attack"] * 1.6), floor_atk_cap)
    ordinary_defense = int(original["defense"] * 1.6)

    assert guardian["hp"] > ordinary_hp
    assert guardian["attack"] > ordinary_attack
    assert guardian["defense"] > ordinary_defense
    assert guardian["hp"] >= (floor_hp_cap * 6 + 4) // 5
    assert guardian["attack"] >= floor_atk_cap + 2
    assert guardian["guardian_floor"] == floor_num

    # Scaling returns an isolated encounter instance. The shared bestiary is
    # immutable even when a caller later changes the guardian's combat state.
    assert MONSTERS[guardian_key] == registry_before
    guardian["hp"] = 1
    guardian["attack"] = 0
    assert MONSTERS[guardian_key] == registry_before


def test_guardian_progression_bands_are_monotonic_and_unlock_resonance_ward():
    floors = [1, 15, 30, 45, 60, 75, 77]
    scaled = [
        scale_stair_guardian(get_monster(STAIR_GUARDIANS[floor]), floor)
        for floor in floors
    ]

    assert [item["guardian_band"] for item in scaled] == [1, 2, 3, 4, 5, 6, 6]
    assert [item["guardian_ward_pct"] for item in scaled] == [0, 5, 10, 15, 20, 25, 25]
    assert [item["guardian_mechanic"] for item in scaled] == [
        "none", "resonance_ward", "resonance_ward", "resonance_ward",
        "resonance_ward", "resonance_ward", "resonance_ward",
    ]
    for field in ("hp", "attack", "defense"):
        values = [item[field] for item in scaled]
        assert values == sorted(values), (field, values)

    mountain_heart = scaled[-1]
    assert mountain_heart["name"] == get_monster("the_mountain_heart")["name"]
    assert mountain_heart["hp"] == 374
    assert mountain_heart["attack"] == 26
    assert mountain_heart["defense"] == 29
    assert mountain_heart["guardian_ward_pct"] == 25


@pytest.mark.parametrize("floor_num", [0, -1, MAX_FLOOR + 1, "not-a-floor", True])
def test_guardian_scaler_rejects_invalid_floor_numbers(floor_num):
    with pytest.raises(ValueError):
        scale_stair_guardian(get_monster("the_mountain_heart"), floor_num)


def test_resonance_ward_reduces_damage_only_on_the_guardian_instance():
    sheet = {
        "character_name": "Test",
        "class": "Warrior",
        "level": 1,
        "stats": {"str": 10},
        "equipment": {},
        "conditions": [],
        "hp": {"current": 20, "max": 20},
        "hunt_streak": 0,
    }
    base_monster = get_monster("the_mountain_heart")
    guardian = scale_stair_guardian(base_monster, 77)
    guardian.update({
        "hp": {"current": 20, "max": 20},
        "attack": 0,
        "defense": 1,
        "tier": "trivial",
    })
    ordinary = copy.deepcopy(guardian)
    ordinary.pop("guardian_ward_pct")
    ordinary.pop("guardian_mechanic")
    ordinary.pop("guardian_band")
    ordinary.pop("guardian_floor")

    # Hit with 1d4 = 4, then make the monster miss its counter-attack.
    with patch.object(combat_engine.secrets, "randbelow", side_effect=[13, 3, 0]):
        warded = combat_engine._resolve_combat(
            copy.deepcopy(sheet), guardian, def_mod_global=100
        )
    with patch.object(combat_engine.secrets, "randbelow", side_effect=[13, 3, 0]):
        unwarded = combat_engine._resolve_combat(
            copy.deepcopy(sheet), ordinary, def_mod_global=100
        )

    assert warded["player_damage"] == 3
    assert warded["monster"]["hp"]["current"] == 17
    assert any("Resonance Ward absorbs 1 damage" in line for line in warded["exchanges"])
    assert unwarded["player_damage"] == 4
    assert unwarded["monster"]["hp"]["current"] == 16
