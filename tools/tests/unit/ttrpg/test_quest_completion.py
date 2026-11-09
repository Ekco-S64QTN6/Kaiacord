"""Quest completion must settle payout and progression in one sheet mutation."""
from utils.ttrpg.progression import XP_THRESHOLDS
from utils.ttrpg.quest_completion import apply_quest_completion


def _sheet():
    return {
        "user_id": "quest-tester",
        "class": "Warrior",
        "level": 3,
        "xp": 0,
        "gil": 25,
        "stats": {"con": 10},
        "hp": {"current": 30, "max": 30},
        "inventory": [],
        "mailbox": [],
        "recipes": [],
        "active_quests": ["deep_hunt"],
        "completed_quests": [],
    }


def test_quest_completion_applies_multi_level_progression_before_save():
    sheet = _sheet()
    quest = {
        "id": "deep_hunt",
        "name": "The Deep Hunt",
        "rewards": {
            "xp": XP_THRESHOLDS[13],
            "gil": 75,
            "item": "potion_standard",
            "recipe": "potion_minor",
        },
    }

    result = apply_quest_completion(sheet, quest)

    assert result["awarded"] is True
    assert result["leveled"] is True
    assert result["new_level"] == 13
    assert sheet["level"] == 13
    assert sheet["_stat_choice_levels_pending"] == [4, 8, 12]
    assert sheet["xp"] == XP_THRESHOLDS[13]
    assert sheet["gil"] == 100
    assert "deep_hunt" not in sheet["active_quests"]
    assert sheet["completed_quests"] == ["deep_hunt"]
    assert "potion_standard" in sheet["inventory"]
    assert sheet["recipes"] == ["potion_minor"]


def test_quest_completion_is_idempotent_after_completion_marker():
    sheet = _sheet()
    quest = {
        "id": "deep_hunt",
        "name": "The Deep Hunt",
        "rewards": {"xp": 100, "gil": 50, "recipe": "potion_minor"},
    }

    first = apply_quest_completion(sheet, quest)
    xp_after_first = sheet["xp"]
    gil_after_first = sheet["gil"]
    recipes_after_first = list(sheet["recipes"])
    second = apply_quest_completion(sheet, quest)

    assert first["awarded"] is True
    assert second is None
    assert sheet["xp"] == xp_after_first
    assert sheet["gil"] == gil_after_first
    assert sheet["recipes"] == recipes_after_first
    assert sheet["completed_quests"] == ["deep_hunt"]


def test_duplicate_active_quest_entry_is_removed_without_duplicate_payout():
    sheet = _sheet()
    sheet["completed_quests"] = ["deep_hunt"]
    sheet["active_quests"] = ["deep_hunt", "deep_hunt"]
    sheet["xp"] = 500
    result = apply_quest_completion(sheet, {
        "id": "deep_hunt",
        "rewards": {"xp": 1000, "gil": 100},
    })

    assert result == {"awarded": False}
    assert sheet["active_quests"] == []
    assert sheet["xp"] == 500
    assert sheet["gil"] == 25
