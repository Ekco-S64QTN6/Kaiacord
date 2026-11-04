"""Regression tests for forest-event probabilities and procedural boss scaling."""
import pytest

from utils.ttrpg import calendar, encounter_tables, world_state
from utils.ttrpg.dungeon import _scale_boss_to_level, boss_level_multiplier


EXPECTED_EVENT_CHANCE = {
    "whisperwood_edge": 20,
    "trade_road": 18,
    "whisperwood_deep": 15,
    "aeridor_ruins": 10,
}


def test_forest_event_base_probabilities_match_the_system_manual():
    assert encounter_tables.EVENT_CHANCE == EXPECTED_EVENT_CHANCE


@pytest.mark.parametrize("location,chance", EXPECTED_EVENT_CHANCE.items())
def test_forest_event_roll_uses_the_documented_base_threshold(
    monkeypatch, location, chance
):
    monkeypatch.setattr(
        world_state, "load_world_state", lambda: {"forest_event_bonus": 0.0}
    )
    monkeypatch.setattr(calendar, "weather_mod", lambda _key: None)

    monkeypatch.setattr(encounter_tables.secrets, "randbelow", lambda _n: chance - 1)
    assert encounter_tables.roll_for_event(location) is True

    monkeypatch.setattr(encounter_tables.secrets, "randbelow", lambda _n: chance)
    assert encounter_tables.roll_for_event(location) is False


@pytest.mark.parametrize(
    "level,expected",
    [
        (1, 0.45),
        (5, 0.6071428571428571),
        (9, 0.7642857142857142),
        (10, 0.8035714285714286),
        (15, 1.0),
    ],
)
def test_boss_multiplier_is_linear_at_documented_level_points(level, expected):
    assert boss_level_multiplier(level) == pytest.approx(expected)


@pytest.mark.parametrize("level", [0, 1, 5, 9, 10, 15, 16, 99])
def test_boss_scaling_clamps_to_the_supported_level_range(level):
    expected_level = max(1, min(15, level))
    expected = 0.45 + (expected_level - 1) * (0.55 / 14)
    assert boss_level_multiplier(level) == pytest.approx(expected)


def test_level_ten_boss_attack_cap_is_unchanged_and_non_binding():
    boss_template = {
        "name": "Test Boss",
        "hp": 1000,
        "attack": 12,
        "defense": 12,
        "tier": "boss",
    }

    # L10's existing ATK cap remains 17. With registry boss ATK <= 12,
    # the new 0.80357x multiplier yields 9 ATK, so that cap does not bind.
    scaled = _scale_boss_to_level(boss_template, 10)

    assert scaled["attack"] == 9
    assert scaled["attack"] < 17
    assert boss_template["attack"] == 12
