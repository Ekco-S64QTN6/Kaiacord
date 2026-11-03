"""Wisp-specific loot is tied to the kill, not to character level-ups."""
from unittest.mock import patch

from utils.ttrpg.rpg_combat_handler import _roll_wisp_lightstone_drop
from utils.ttrpg.character_manager import INVENTORY_LIMIT


def test_wisp_lightstone_roll_is_independent_of_level_up():
    sheet = {"inventory": [], "xp": 0, "level": 3}

    with patch("utils.ttrpg.rpg_combat_handler.secrets.randbelow", return_value=0) as roll:
        assert _roll_wisp_lightstone_drop(sheet, "wisp") == "granted"

    roll.assert_called_once_with(3)
    assert sheet["inventory"] == ["lightstone"]
    # No XP or level mutation is required to receive the drop.
    assert sheet["xp"] == 0
    assert sheet["level"] == 3


def test_wisp_lightstone_is_unique_and_does_not_roll_twice():
    sheet = {"inventory": ["lightstone"]}

    with patch("utils.ttrpg.rpg_combat_handler.secrets.randbelow") as roll:
        assert _roll_wisp_lightstone_drop(sheet, "ice_wisp") == ""

    roll.assert_not_called()
    assert sheet["inventory"] == ["lightstone"]


def test_non_wisp_kills_never_roll_for_lightstone():
    sheet = {"inventory": []}

    with patch("utils.ttrpg.rpg_combat_handler.secrets.randbelow") as roll:
        assert _roll_wisp_lightstone_drop(sheet, "bandit") == ""

    roll.assert_not_called()
    assert sheet["inventory"] == []


def test_full_inventory_reports_wisp_lightstone_left_behind():
    sheet = {"inventory": [f"item_{i}" for i in range(INVENTORY_LIMIT)]}

    with patch("utils.ttrpg.rpg_combat_handler.secrets.randbelow", return_value=0) as roll:
        assert _roll_wisp_lightstone_drop(sheet, "moldwynd") == "full"

    roll.assert_called_once_with(3)
    assert len(sheet["inventory"]) == INVENTORY_LIMIT
    assert "lightstone" not in sheet["inventory"]
