"""Cross-player world-state transactions and crash recovery."""
import asyncio
import copy
import json

import pytest

from utils.ttrpg import character_manager, town_projects, world_state


def _isolated_world_state(monkeypatch, tmp_path):
    state_path = tmp_path / "world_state.json"
    journal_path = tmp_path / "world_state_pending.json"
    monkeypatch.setattr(world_state, "_path", lambda: str(state_path))
    monkeypatch.setattr(world_state, "_transaction_path", lambda: str(journal_path))
    # asyncio.Lock is loop-bound after contention. Give each test an isolated
    # transaction lock so tests can use independent pytest event loops.
    monkeypatch.setattr(world_state, "_transaction_lock", asyncio.Lock())
    saved_sheets = []

    async def save_sheet(sheet):
        saved_sheets.append(copy.deepcopy(sheet))

    monkeypatch.setattr(character_manager, "save", save_sheet)
    return state_path, journal_path, saved_sheets


def _purify(sheet, state):
    if not state.get("fishing_water_tainted"):
        return False, False
    reagent = next(
        (item for item in ("aeridor_shard", "tonic", "healing_herb")
         if item in sheet.get("inventory", [])),
        None,
    )
    if reagent is None:
        return False, False
    sheet["inventory"].remove(reagent)
    sheet["xp"] += 50
    sheet["reputation"] += 15
    state["fishing_water_tainted"] = False
    state["fishing_water_tainted_expiry"] = 0
    return True, True


def test_two_players_cannot_claim_the_same_global_pond_purification(monkeypatch, tmp_path):
    state_path, _, saved_sheets = _isolated_world_state(monkeypatch, tmp_path)
    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "fishing_water_tainted": True,
        "fishing_water_tainted_expiry": 12345,
    })
    alice = {
        "user_id": "alice", "character_name": "Alice", "inventory": ["tonic"],
        "xp": 100, "reputation": 1,
    }
    bob = {
        "user_id": "bob", "character_name": "Bob", "inventory": ["healing_herb"],
        "xp": 200, "reputation": 2,
    }

    async def run():
        return await asyncio.gather(
            world_state.mutate_world_state(_purify, alice),
            world_state.mutate_world_state(_purify, bob),
        )

    results = asyncio.run(run())
    assert sorted(results) == [False, True]
    assert sum("tonic" not in s["inventory"] for s in (alice, bob)) == 1
    assert sum("healing_herb" not in s["inventory"] for s in (alice, bob)) == 1
    assert sum(s["xp"] for s in (alice, bob)) == 350
    assert sum(s["reputation"] for s in (alice, bob)) == 18
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["fishing_water_tainted"] is False
    assert persisted["fishing_water_tainted_expiry"] == 0
    assert len(saved_sheets) == 1
    assert saved_sheets[0]["xp"] in (150, 250)


def test_concurrent_donations_preserve_each_contribution_and_threshold(monkeypatch, tmp_path):
    state_path, _, saved_sheets = _isolated_world_state(monkeypatch, tmp_path)
    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "town_fund": 0,
        "town_donors": {},
    })
    donors = [
        {"user_id": "a", "character_name": "A", "gil": 120_000},
        {"user_id": "b", "character_name": "B", "gil": 120_000},
        {"user_id": "c", "character_name": "C", "gil": 120_000},
    ]

    def donation(sheet, state):
        ok, message = town_projects.donate(sheet, state, 100_000, now=1_800_000_000)
        return ok, (ok, message)

    async def run():
        return await asyncio.gather(*[
            world_state.mutate_world_state(donation, sheet) for sheet in donors
        ])

    results = asyncio.run(run())
    assert all(ok for ok, _ in results)
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert [s["gil"] for s in donors] == [20_000, 20_000, 20_000]
    assert persisted["town_fund"] == 50_000
    assert persisted["town_donors"] == {"A": 100_000, "B": 100_000, "C": 100_000}
    assert persisted["fortified_until"] == 1_800_000_000 + town_projects.FORTIFIED_S
    assert len(saved_sheets) == 3


def test_threshold_crossing_is_serialized_once_and_later_donation_extends_expiry(
    monkeypatch, tmp_path
):
    state_path, _, _ = _isolated_world_state(monkeypatch, tmp_path)
    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "town_fund": town_projects.PROJECT_COST - 50_000,
        "town_donors": {},
        "fortified_until": 1_800_000_000 + 86_400,
    })
    sheets = [
        {"user_id": "a", "character_name": "A", "gil": 100_000},
        {"user_id": "b", "character_name": "B", "gil": 100_000},
    ]

    def donation(sheet, state):
        ok, message = town_projects.donate(sheet, state, 50_000, now=1_800_000_000)
        return ok, (ok, message)

    async def run():
        return await asyncio.gather(*[
            world_state.mutate_world_state(donation, sheet) for sheet in sheets
        ])

    assert all(ok for ok, _ in asyncio.run(run()))
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["town_fund"] == 50_000
    assert persisted["fortified_until"] == 1_800_000_000 + 8 * 86_400
    assert persisted["town_donors"] == {"A": 50_000, "B": 50_000}


def test_pending_world_transaction_replays_both_sheets_after_character_save_failure(
    monkeypatch, tmp_path
):
    state_path, journal_path, _ = _isolated_world_state(monkeypatch, tmp_path)
    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "fishing_water_tainted": True,
    })
    sheet = {
        "user_id": "alice", "character_name": "Alice", "inventory": ["aeridor_shard"],
        "xp": 500, "reputation": 10,
    }
    calls = []

    async def fail_once_then_save(current):
        calls.append(copy.deepcopy(current))
        if len(calls) == 1:
            raise OSError("simulated character-sheet disk failure")

    monkeypatch.setattr(character_manager, "save", fail_once_then_save)

    with pytest.raises(OSError, match="simulated"):
        asyncio.run(world_state.mutate_world_state(_purify, sheet))

    # The global file may be ahead of the character file, but the journal
    # contains the intended snapshots for both sides.
    assert json.loads(state_path.read_text(encoding="utf-8"))["fishing_water_tainted"] is False
    record = json.loads(journal_path.read_text(encoding="utf-8"))
    assert record["character_sheet"]["inventory"] == []
    assert record["character_sheet"]["xp"] == 550
    assert record["character_sheet"]["reputation"] == 25

    recovered_sheets = []

    async def save_recovered(current):
        recovered_sheets.append(copy.deepcopy(current))

    monkeypatch.setattr(character_manager, "save", save_recovered)
    assert asyncio.run(world_state.recover_pending_world_state_transaction()) is True
    assert asyncio.run(world_state.recover_pending_world_state_transaction()) is False
    recovered_record = json.loads(journal_path.read_text(encoding="utf-8"))
    assert recovered_record == {}
    assert len(recovered_sheets) == 1
    assert recovered_sheets[0]["inventory"] == []
    assert recovered_sheets[0]["xp"] == 550
    assert recovered_sheets[0]["reputation"] == 25
    assert json.loads(state_path.read_text(encoding="utf-8"))["fishing_water_tainted"] is False


def test_unknown_world_transaction_version_fails_closed(monkeypatch, tmp_path):
    _, journal_path, _ = _isolated_world_state(monkeypatch, tmp_path)
    journal_path.write_text(json.dumps({
        "version": 99,
        "transaction_id": "unknown-version",
        "world_state": {},
        "character_sheet": {"user_id": "alice"},
    }), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unknown pending"):
        asyncio.run(world_state.recover_pending_world_state_transaction())
    assert json.loads(journal_path.read_text(encoding="utf-8"))["transaction_id"] == "unknown-version"


def test_rejected_world_action_does_not_persist_either_file(monkeypatch, tmp_path):
    state_path, journal_path, saved_sheets = _isolated_world_state(monkeypatch, tmp_path)
    initial = {**world_state.DEFAULT_STATE, "town_fund": 10}
    world_state.save_world_state(initial)
    sheet = {"user_id": "alice", "character_name": "Alice", "gil": 5}

    def rejected(current_sheet, state):
        return False, "rejected"

    assert asyncio.run(world_state.mutate_world_state(rejected, sheet)) == "rejected"
    assert json.loads(state_path.read_text(encoding="utf-8"))["town_fund"] == 10
    assert not journal_path.exists()
    assert saved_sheets == []
