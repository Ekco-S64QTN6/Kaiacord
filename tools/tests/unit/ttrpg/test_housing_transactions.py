"""Fault-injection coverage for character + housing multi-file transactions."""
import asyncio
import copy
import json

import pytest

from utils.ttrpg import character_manager, housing, housing_transactions


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(
        housing_transactions,
        "_journal_dir",
        lambda: str(tmp_path / "journals"),
    )
    monkeypatch.setattr(housing_transactions, "_transaction_lock", asyncio.Lock())
    character_writes = []
    housing_writes = []

    async def save_character(sheet):
        character_writes.append(copy.deepcopy(sheet))

    async def save_housing_snapshot(home):
        housing_writes.append(copy.deepcopy(home))

    monkeypatch.setattr(character_manager, "save", save_character)
    monkeypatch.setattr(housing, "save_housing_async", save_housing_snapshot)
    return character_writes, housing_writes


def _snapshots(action):
    sheet = {
        "user_id": "42",
        "character_name": "Tester",
        "gil": 500,
        "xp": 100,
        "inventory": ["seed", "healing_herb"],
        "mailbox": [],
        "conditions": [],
    }
    home = {
        "user_id": "42",
        "character_name": "Tester",
        "tier": "hut",
        "pets": [],
        "furniture": [],
        "farming": {"plots": []},
        "mognet_deliveries": 0,
    }
    if action == "plant_crop":
        sheet["inventory"].remove("seed")
        home["farming"]["plots"].append({"crop_key": "blood_thistle_seed"})
    elif action == "harvest_crops":
        sheet["inventory"].append("blood_thistle")
        home["farming"]["plots"] = []
    elif action == "treat_blight":
        sheet["inventory"].remove("healing_herb")
        sheet["xp"] += 25
        home["farming"]["plots"] = [{"crop_key": "blood_thistle_seed", "blighted": False, "blight_hardened": True}]
    elif action == "buy_pet":
        sheet["gil"] -= 50
        home["pets"].append({"key": "cat", "name": "Oakhaven Cat", "fed_today": False})
    elif action == "buy_furniture":
        sheet["gil"] -= 100
        home["furniture"].append("training_dummy")
    elif action == "feed_pets":
        sheet["gil"] -= 5
        home["pets"] = [{"key": "cat", "name": "Oakhaven Cat", "fed_today": True}]
    elif action == "buy_house":
        sheet["gil"] -= 50_000
        home["tier"] = "hut"
    elif action == "upgrade_house":
        sheet["gil"] -= 100_000
        home["tier"] = "cottage"
    elif action == "home_training":
        sheet["conditions"].append("hunt_bonus")
        home["last_training"] = "2026-11-04"
    elif action == "daily_mognet_delivery":
        home["mognet_deliveries"] = 0
        sheet["mailbox"].append({"from_name": "House Moogle", "item": "tonic", "gil": 0})
    return sheet, home


@pytest.mark.parametrize(
    "action",
    [
        "plant_crop",
        "harvest_crops",
        "treat_blight",
        "buy_pet",
        "buy_furniture",
        "feed_pets",
        "buy_house",
        "upgrade_house",
        "home_training",
        "daily_mognet_delivery",
    ],
)
def test_character_housing_action_commits_both_snapshots(monkeypatch, tmp_path, action):
    character_writes, housing_writes = _isolate(monkeypatch, tmp_path)
    sheet, home = _snapshots(action)

    asyncio.run(housing_transactions.commit_character_housing(
        sheet, home, action=action
    ))

    assert character_writes == [sheet]
    assert housing_writes == [home]
    journal_files = list((tmp_path / "journals").glob("*.json"))
    assert len(journal_files) == 1
    assert json.loads(journal_files[0].read_text(encoding="utf-8")) == {}


@pytest.mark.parametrize(
    "action",
    [
        "plant_crop",
        "harvest_crops",
        "treat_blight",
        "buy_pet",
        "buy_furniture",
        "feed_pets",
        "buy_house",
        "upgrade_house",
        "home_training",
        "daily_mognet_delivery",
    ],
)
@pytest.mark.parametrize("failure_boundary", ["character_save", "housing_save"])
def test_character_housing_action_recovers_after_either_save_boundary(
    monkeypatch, tmp_path, action, failure_boundary
):
    _isolate(monkeypatch, tmp_path)
    sheet, home = _snapshots(action)
    intended_sheet = copy.deepcopy(sheet)
    intended_home = copy.deepcopy(home)
    character_calls = []
    housing_calls = []

    async def save_character(current):
        character_calls.append(copy.deepcopy(current))
        if failure_boundary == "character_save" and len(character_calls) == 1:
            raise OSError("injected character save failure")

    async def save_housing_snapshot(current):
        housing_calls.append(copy.deepcopy(current))
        if failure_boundary == "housing_save" and len(housing_calls) == 1:
            raise OSError("injected housing save failure")

    monkeypatch.setattr(character_manager, "save", save_character)
    monkeypatch.setattr(housing, "save_housing_async", save_housing_snapshot)

    with pytest.raises(OSError, match="injected"):
        asyncio.run(housing_transactions.commit_character_housing(
            sheet, home, action=action
        ))

    journal_path = housing_transactions._journal_path("42")
    record = json.loads(open(journal_path, encoding="utf-8").read())
    assert record["action"] == action
    assert record["character_sheet"] == intended_sheet
    assert record["resource_kind"] == "housing"
    assert record["resource_state"] == intended_home

    recovered_character = []
    recovered_housing = []

    async def save_character_recovered(current):
        recovered_character.append(copy.deepcopy(current))

    async def save_housing_recovered(current):
        recovered_housing.append(copy.deepcopy(current))

    monkeypatch.setattr(character_manager, "save", save_character_recovered)
    monkeypatch.setattr(housing, "save_housing_async", save_housing_recovered)

    assert asyncio.run(housing_transactions.recover_pending_housing_transaction("42"))
    assert not asyncio.run(housing_transactions.recover_pending_housing_transaction("42"))
    assert recovered_character == [intended_sheet]
    assert recovered_housing == [intended_home]
    assert json.loads(open(journal_path, encoding="utf-8").read()) == {}


def test_unknown_housing_journal_version_fails_closed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    journal_path = housing_transactions._journal_path("42")
    from utils.core.atomic_write import write_atomic
    write_atomic(journal_path, json.dumps({
        "version": 99,
        "transaction_id": "unknown",
        "user_id": "42",
        "character_sheet": {"user_id": "42"},
        "housing": {"user_id": "42"},
    }))

    with pytest.raises(RuntimeError, match="Unknown RPG transaction version"):
        asyncio.run(housing_transactions.recover_pending_housing_transaction("42"))
    assert json.loads(open(journal_path, encoding="utf-8").read())["transaction_id"] == "unknown"


def test_transaction_rejects_mismatched_character_and_housing_owners(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    sheet, home = _snapshots("buy_pet")
    home["user_id"] = "different-user"

    with pytest.raises(ValueError, match="same user_id"):
        asyncio.run(housing_transactions.commit_character_housing(
            sheet, home, action="buy_pet"
        ))


def test_daily_reset_commit_can_save_while_character_manager_lock_is_held(
    monkeypatch, tmp_path
):
    _, housing_writes = _isolate(monkeypatch, tmp_path)
    sheet, home = _snapshots("daily_mognet_delivery")
    sync_writes = []
    monkeypatch.setattr(
        character_manager,
        "_save_sync",
        lambda current: sync_writes.append(copy.deepcopy(current)),
    )

    asyncio.run(housing_transactions.commit_character_housing(
        sheet, home, action="daily_mognet_delivery", character_lock_held=True
    ))

    # This path intentionally uses _save_sync rather than re-entering the
    # character manager's non-reentrant per-user asyncio lock.
    assert sync_writes == [sheet]
    assert housing_writes == [home]


@pytest.mark.parametrize("resource_kind", ["dungeon", "spine_dungeon"])
@pytest.mark.parametrize("failure_boundary", ["character_save", "resource_save"])
def test_dungeon_entry_recovers_character_cost_and_dungeon_snapshot(
    monkeypatch, tmp_path, resource_kind, failure_boundary
):
    _isolate(monkeypatch, tmp_path)
    sheet = {
        "user_id": "42",
        "character_name": "Tester",
        "gil": 500,
        "hunts_today": 2,
        "inventory": ["torch"],
    }
    sheet["inventory"].remove("torch")
    sheet["hunts_today"] += 2
    state = {
        "active": True,
        "floor_num": 1,
        "player_level": 5,
        "rooms": {"0,0": {"type": "entrance"}},
    }
    character_calls = []
    resource_calls = []

    async def save_character(current):
        character_calls.append(copy.deepcopy(current))
        if failure_boundary == "character_save" and len(character_calls) == 1:
            raise OSError("injected character save failure")

    async def save_resource(uid, current):
        resource_calls.append((uid, copy.deepcopy(current)))
        if failure_boundary == "resource_save" and len(resource_calls) == 1:
            raise OSError("injected dungeon save failure")

    monkeypatch.setattr(character_manager, "save", save_character)
    if resource_kind == "dungeon":
        from utils.ttrpg import dungeon as resource_module
        monkeypatch.setattr(resource_module, "save_dungeon", save_resource)
    else:
        from utils.ttrpg import spine_dungeon as resource_module
        monkeypatch.setattr(resource_module, "save_spine_dungeon", save_resource)

    commit = (
        housing_transactions.commit_character_dungeon
        if resource_kind == "dungeon"
        else housing_transactions.commit_character_spine_dungeon
    )
    with pytest.raises(OSError, match="injected"):
        asyncio.run(commit(sheet, state, action=f"{resource_kind}_entry"))

    journal_path = housing_transactions._journal_path("42")
    record = json.loads(open(journal_path, encoding="utf-8").read())
    assert record["resource_kind"] == resource_kind
    assert record["character_sheet"] == sheet
    assert record["resource_state"] == state

    recovered_character = []
    recovered_resource = []

    async def save_character_recovered(current):
        recovered_character.append(copy.deepcopy(current))

    async def save_resource_recovered(uid, current):
        recovered_resource.append((uid, copy.deepcopy(current)))

    monkeypatch.setattr(character_manager, "save", save_character_recovered)
    if resource_kind == "dungeon":
        monkeypatch.setattr(resource_module, "save_dungeon", save_resource_recovered)
    else:
        monkeypatch.setattr(resource_module, "save_spine_dungeon", save_resource_recovered)

    assert asyncio.run(housing_transactions.recover_pending_housing_transaction("42"))
    assert not asyncio.run(housing_transactions.recover_pending_housing_transaction("42"))
    assert recovered_character == [sheet]
    assert recovered_resource == [("42", state)]
    assert json.loads(open(journal_path, encoding="utf-8").read()) == {}


def test_unsupported_resource_kind_fails_closed(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    sheet = {"user_id": "42", "inventory": []}
    resource = {"active": True}

    with pytest.raises(ValueError, match="unsupported multi-file resource"):
        asyncio.run(housing_transactions.commit_character_resource(
            sheet, resource, resource_kind="shared_session", action="fishing_hook"
        ))


def test_character_load_recovers_pending_housing_transaction_before_loading_sheet(
    monkeypatch, tmp_path
):
    from datetime import date
    from utils.ttrpg import housing, world_state

    _isolate(monkeypatch, tmp_path)
    intended_sheet = {
        "user_id": "42",
        "character_name": "Tester",
        "gil": 450,
        "hunts_reset_date": date.today().strftime("%Y-%m-%d"),
    }
    home = {
        "user_id": "42",
        "character_name": "Tester",
        "tier": "hut",
        "pets": [{"key": "cat", "name": "Oakhaven Cat"}],
        "furniture": [],
        "farming": {"plots": []},
    }
    housing_transactions._write_journal("42", {
        "version": 1,
        "transaction_id": "42:load-recovery",
        "user_id": "42",
        "action": "buy_pet",
        "resource_kind": "housing",
        "character_sheet": copy.deepcopy(intended_sheet),
        "resource_state": copy.deepcopy(home),
    })

    events = []
    persisted_sheet = {"user_id": "42", "character_name": "Tester", "gil": 500}

    async def save_character(current):
        events.append("save_character")
        persisted_sheet.clear()
        persisted_sheet.update(copy.deepcopy(current))

    async def save_housing_snapshot(current):
        events.append("save_housing")

    async def no_world_recovery():
        return False

    async def get_test_lock(_user_id):
        return asyncio.Lock()

    def load_sheet(_user_id):
        events.append("load_sheet")
        return copy.deepcopy(persisted_sheet)

    monkeypatch.setattr(character_manager, "save", save_character)
    monkeypatch.setattr(character_manager, "get_user_lock", get_test_lock)
    monkeypatch.setattr(character_manager, "_load_sync", load_sheet)
    monkeypatch.setattr(housing, "save_housing_async", save_housing_snapshot)
    monkeypatch.setattr(world_state, "recover_pending_world_state_transaction", no_world_recovery)

    loaded = asyncio.run(character_manager.load("42"))

    assert events == ["save_character", "save_housing", "load_sheet"]
    assert loaded["gil"] == 450
    assert len(loaded["hunts_reset_date"]) == 10
    assert json.loads(
        open(housing_transactions._journal_path("42"), encoding="utf-8").read()
    ) == {}
