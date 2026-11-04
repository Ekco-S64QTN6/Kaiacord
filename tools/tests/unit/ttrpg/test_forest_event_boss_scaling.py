"""Published forest-event rates and procedural boss scaling stay in sync."""
import pytest

from utils.ttrpg.dungeon import _scale_boss_to_level, boss_level_multiplier
from utils.ttrpg.encounter_tables import EVENT_CHANCE


def test_forest_event_base_probabilities_match_the_system_manual():
    assert EVENT_CHANCE == {
        "whisperwood_edge": 20,
        "trade_road": 18,
        "whisperwood_deep": 15,
        "aeridor_ruins": 10,
    }


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (1, 0.45),
        (5, 0.6071428571428571),
        (9, 0.7642857142857142),
        (10, 0.8035714285714286),
        (15, 1.0),
    ],
)
def test_boss_level_multiplier_matches_documented_linear_curve(level, expected):
    assert boss_level_multiplier(level) == pytest.approx(expected)


def test_boss_level_multiplier_is_clamped_to_the_character_level_range():
    assert boss_level_multiplier(0) == pytest.approx(0.45)
    assert boss_level_multiplier(16) == pytest.approx(1.0)


def test_level_ten_boss_attack_cap_remains_seventeen():
    boss = {"name": "Test Boss", "hp": 1000, "attack": 100, "defense": 20}

    scaled = _scale_boss_to_level(boss, 10)

    assert scaled["hp"] == 270
    assert scaled["attack"] == 17
    assert boss == {"name": "Test Boss", "hp": 1000, "attack": 100, "defense": 20}
