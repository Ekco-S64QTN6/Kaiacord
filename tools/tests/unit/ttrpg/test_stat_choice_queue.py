"""Every RPG stat-growth milestone grants one independently consumable choice."""
from utils.ttrpg.progression import check_level_up, consume_stat_choice


def test_multi_level_xp_gain_queues_all_stat_choice_milestones():
    sheet = {
        "class": "Warrior",
        "level": 3,
        "xp": 148000,  # cross levels 4, 8 and 12 in a single progression pass
        "stats": {"con": 10},
        "hp": {"current": 30, "max": 30},
    }

    leveled, level = check_level_up(sheet)

    assert leveled is True
    assert level == 13
    assert sheet["_stat_choice_pending"] is True
    assert sheet["_stat_choice_levels_pending"] == [4, 8, 12]

    assert consume_stat_choice(sheet) is True
    assert sheet["_stat_choice_levels_pending"] == [8, 12]
    assert consume_stat_choice(sheet) is True
    assert sheet["_stat_choice_levels_pending"] == [12]
    assert consume_stat_choice(sheet) is False
    assert "_stat_choice_pending" not in sheet
    assert "_stat_choice_levels_pending" not in sheet


def test_each_single_level_milestone_creates_one_choice():
    sheet = {
        "class": "Mage",
        "level": 3,
        "xp": 2700,
        "stats": {"con": 10},
        "hp": {"current": 18, "max": 18},
    }

    check_level_up(sheet)

    assert sheet["_stat_choice_levels_pending"] == [4]
    assert consume_stat_choice(sheet) is False


def test_legacy_boolean_pending_choice_is_still_consumable():
    sheet = {"_stat_choice_pending": True}

    assert consume_stat_choice(sheet) is False
    assert "_stat_choice_pending" not in sheet
