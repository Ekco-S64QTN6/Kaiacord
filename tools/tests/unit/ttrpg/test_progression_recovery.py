"""Migration regressions for persisted RPG progression flags."""
import json

from utils.ttrpg import character_manager


def test_loading_a_level_five_sheet_recovers_missing_advancement_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(tmp_path))
    path = tmp_path / "42.json"
    path.write_text(json.dumps({
        "user_id": "42",
        "class": "Warrior",
        "level": 5,
        "xp": 5000,
        "hp": {"current": 30, "max": 30},
        "stats": {"con": 10},
        # Simulate an old/corrupt save in which the one-shot flag was lost.
    }), encoding="utf-8")

    sheet = character_manager._load_sync("42")

    assert sheet is not None
    assert sheet["_advancement_pending"] is True


def test_loading_a_level_five_sheet_does_not_rearm_after_specialization(tmp_path, monkeypatch):
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(tmp_path))
    path = tmp_path / "42.json"
    path.write_text(json.dumps({
        "user_id": "42",
        "class": "Warrior",
        "advanced_class": "Paladin",
        "_advancement_pending": True,  # stale flag must not permit a second choice
        "level": 5,
        "xp": 5000,
        "hp": {"current": 35, "max": 35},
        "stats": {"con": 10},
    }), encoding="utf-8")

    sheet = character_manager._load_sync("42")

    assert sheet is not None
    assert "_advancement_pending" not in sheet


def test_load_all_also_recovers_missing_advancement_prompts(tmp_path, monkeypatch):
    monkeypatch.setattr(character_manager, "CHARACTERS_DIR", str(tmp_path))
    (tmp_path / "42.json").write_text(json.dumps({
        "user_id": "42",
        "class": "Ranger",
        "level": 7,
        "xp": 19000,
        "hp": {"current": 40, "max": 40},
        "stats": {"con": 10},
    }), encoding="utf-8")

    sheets = character_manager._load_all_sync()

    assert len(sheets) == 1
    assert sheets[0]["_advancement_pending"] is True
