"""Housing reads are pure; daily farm, pet, and Mognet changes commit together."""
import asyncio
import copy
from datetime import date

from utils.ttrpg import character_manager, housing, housing_transactions, progression, world_state


def test_load_housing_does_not_apply_or_persist_daily_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(housing, "HOUSING_DIR", str(tmp_path))
    home = housing.default_housing_sheet("42", "Tester")
    home["last_farm_reset"] = "2000-01-01"
    home["farming"]["plots"] = [{"watered_today": True}]
    home["pets"] = [{"key": "moogle", "fed_today": True, "fed_days": 6, "days_owned": 2}]
    housing.save_housing(home)
    path = tmp_path / "42.json"
    original = path.read_bytes()

    loaded = housing.load_housing("42")
    loaded_again = asyncio.run(housing.load_housing_async("42"))

    assert loaded["last_farm_reset"] == "2000-01-01"
    assert loaded["farming"]["plots"][0]["watered_today"] is True
    assert loaded["pets"][0]["fed_today"] is True
    assert loaded["pets"][0]["fed_days"] == 6
    assert loaded_again == loaded
    assert path.read_bytes() == original


def test_new_housing_starts_with_today_reset_marker():
    home = housing.default_housing_sheet("42", "Tester")
    assert home["last_farm_reset"] == date.today().isoformat()


def test_daily_housing_transition_is_idempotent_and_queues_mognet_once():
    home = {
        "user_id": "42",
        "last_farm_reset": "2000-01-01",
        "farming": {"plots": [{"watered_today": True}]},
        "pets": [
            {"key": "moogle", "fed_today": True, "fed_days": 6, "days_owned": 2},
            {"key": "cat", "fed_today": False, "days_owned": 4},
        ],
    }
    assert housing.apply_daily_housing_reset(home, today="2026-01-02") is True
    assert home["last_farm_reset"] == "2026-01-02"
    assert home["farming"]["plots"][0]["watered_today"] is False
    assert home["pets"][0]["fed_today"] is False
    assert home["pets"][0]["fed_days"] == 0
    assert home["pets"][0]["days_owned"] == 3
    assert home["pets"][1]["days_owned"] == 5
    assert home["mognet_deliveries"] == 1
    after_first_reset = copy.deepcopy(home)
    assert housing.apply_daily_housing_reset(home, today="2026-01-02") is False
    assert home == after_first_reset


def _patch_character_load(monkeypatch, sheet, home):
    commits = []

    async def no_world_recovery():
        return False

    async def no_housing_recovery(_uid):
        return False

    async def get_test_lock(_uid):
        return asyncio.Lock()

    async def commit(sheet_snapshot, home_snapshot, *, action, character_lock_held=False):
        commits.append({
            "sheet": copy.deepcopy(sheet_snapshot),
            "home": copy.deepcopy(home_snapshot),
            "action": action,
            "character_lock_held": character_lock_held,
        })

    monkeypatch.setattr(world_state, "recover_pending_world_state_transaction", no_world_recovery)
    monkeypatch.setattr(housing_transactions, "recover_pending_housing_transaction", no_housing_recovery)
    monkeypatch.setattr(character_manager, "get_user_lock", get_test_lock)
    monkeypatch.setattr(character_manager, "_load_sync", lambda _uid: copy.deepcopy(sheet))
    monkeypatch.setattr(housing, "load_housing", lambda _uid: copy.deepcopy(home))
    monkeypatch.setattr(housing_transactions, "commit_character_housing", commit)
    monkeypatch.setattr(
        character_manager,
        "_save_sync",
        lambda _sheet: (_ for _ in ()).throw(AssertionError("unexpected direct character save")),
    )
    return commits


def test_character_load_journals_daily_reset_and_mognet_mailbox_together(monkeypatch):
    uid = "42021"
    today = date.today().isoformat()
    sheet = {
        "user_id": uid, "character_name": "Moogle Keeper",
        "hunts_today": 5, "hunts_reset_date": "2000-01-01",
        "forest_event_attempts_today": 4,
        "conditions": ["ale_warmth", "blessed"],
        "hp": {"current": 13, "max": 13}, "xp": 100, "gil": 25, "mailbox": [],
    }
    home = {
        "user_id": uid, "character_name": "Moogle Keeper",
        "last_farm_reset": "2000-01-01",
        "farming": {"plots": [{"watered_today": True}]},
        "pets": [{"key": "moogle", "fed_today": True, "fed_days": 6, "days_owned": 2}],
        "mognet_deliveries": 0,
    }
    commits = _patch_character_load(monkeypatch, sheet, home)
    loaded = asyncio.run(character_manager.load(uid))

    assert loaded["hunts_today"] == 0
    assert loaded["hunts_reset_date"] == today
    assert loaded["forest_event_attempts_today"] == 0
    assert loaded["conditions"] == ["blessed"]
    assert loaded["hp"] == {"current": 10, "max": 10}
    assert len(loaded["mailbox"]) == 1
    assert loaded["mailbox"][0]["from_name"] == "your House Moogle (Mognet)"
    assert len(commits) == 1
    transaction = commits[0]
    assert transaction["action"] == "daily_mognet_delivery"
    assert transaction["character_lock_held"] is True
    assert transaction["home"]["last_farm_reset"] == today
    assert transaction["home"]["farming"]["plots"][0]["watered_today"] is False
    assert transaction["home"]["pets"][0]["fed_today"] is False
    assert transaction["home"]["pets"][0]["fed_days"] == 0
    assert transaction["home"]["mognet_deliveries"] == 0


def test_character_load_repairs_housing_reset_when_hunt_marker_is_already_today(monkeypatch):
    uid = "42022"
    today = date.today().isoformat()
    sheet = {
        "user_id": uid, "character_name": "Already Reset",
        "hunts_today": 2, "hunts_reset_date": today,
        "forest_event_attempts_today": 1, "conditions": ["blessed"],
        "hp": {"current": 20, "max": 20}, "mailbox": [],
    }
    home = {
        "user_id": uid, "character_name": "Already Reset",
        "last_farm_reset": "2000-01-01",
        "farming": {"plots": [{"watered_today": True}]},
        "pets": [{"key": "cat", "fed_today": False, "days_owned": 4}],
        "mognet_deliveries": 0,
    }
    commits = _patch_character_load(monkeypatch, sheet, home)
    loaded = asyncio.run(character_manager.load(uid))

    assert loaded["hunts_today"] == 2
    assert loaded["hunts_reset_date"] == today
    assert len(commits) == 1
    transaction = commits[0]
    assert transaction["action"] == "daily_housing_reset"
    assert transaction["character_lock_held"] is True
    assert transaction["home"]["last_farm_reset"] == today
    assert transaction["home"]["farming"]["plots"][0]["watered_today"] is False
    assert transaction["home"]["pets"][0]["days_owned"] == 5


def test_progression_daily_hunt_reset_never_mutates_passed_housing():
    home = {
        "last_farm_reset": "2000-01-01",
        "farming": {"plots": [{"watered_today": True}]},
        "pets": [{"key": "moogle", "fed_today": True, "fed_days": 6}],
    }
    original_home = copy.deepcopy(home)
    sheet = {
        "hunts_today": 5, "hunts_reset_date": "2000-01-01",
        "forest_event_attempts_today": 2, "conditions": [],
        "hp": {"current": 10, "max": 10},
    }
    progression.check_and_reset_hunts(sheet, housing=home)
    assert sheet["hunts_today"] == 0
    assert home == original_home
