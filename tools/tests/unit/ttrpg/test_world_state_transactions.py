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
    monkeypatch.setattr(world_state, "_cache", None)
    monkeypatch.setattr(world_state, "_cache_date", 0.0)
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
        "fishing_water_tainted_expiry": 4_000_000_000,
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
    assert results[0] != results[1]
    winner, loser = (alice, bob) if results[0] else (bob, alice)
    assert winner["inventory"] == []
    assert loser["inventory"] in (["tonic"], ["healing_herb"])
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


@pytest.mark.parametrize("journal_owner", ["bob", None])
def test_pending_world_transaction_owner_mismatch_fails_closed_and_is_preserved(
    monkeypatch, tmp_path, journal_owner
):
    state_path, journal_path, saved_sheets = _isolated_world_state(monkeypatch, tmp_path)
    record = {
        "version": 1,
        "transaction_id": "alice:123",
        "user_id": journal_owner,
        "world_state": {**world_state.DEFAULT_STATE, "town_fund": 50_000},
        "character_sheet": {"user_id": "alice", "gil": 10},
    }
    journal_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(RuntimeError, match="owner mismatch"):
        asyncio.run(world_state.recover_pending_world_state_transaction())

    # A corrupt journal must not write either snapshot or be cleared to get
    # past the recovery error; preserve it for diagnosis and repair.
    assert not state_path.exists()
    assert saved_sheets == []
    assert json.loads(journal_path.read_text(encoding="utf-8")) == record


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


def test_pending_world_transaction_recovers_after_world_state_save_failure(
    monkeypatch, tmp_path
):
    state_path, journal_path, _ = _isolated_world_state(monkeypatch, tmp_path)
    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "fishing_water_tainted": True,
        "fishing_water_tainted_expiry": 4_000_000_000,
    })
    sheet = {
        "user_id": "alice",
        "character_name": "Alice",
        "inventory": ["aeridor_shard"],
        "xp": 500,
        "reputation": 10,
    }
    original_write = world_state._write_world_state
    write_calls = []

    def fail_first_world_write(state, serialized):
        write_calls.append(copy.deepcopy(state))
        if len(write_calls) == 1:
            raise OSError("simulated world-state disk failure")
        return original_write(state, serialized)

    monkeypatch.setattr(world_state, "_write_world_state", fail_first_world_write)

    with pytest.raises(OSError, match="simulated world-state"):
        asyncio.run(world_state.mutate_world_state(_purify, sheet))

    # The atomic world-state file is still old, while the journal holds both
    # intended snapshots. Recovery must finish the same purification.
    assert json.loads(state_path.read_text(encoding="utf-8"))["fishing_water_tainted"] is True
    record = json.loads(journal_path.read_text(encoding="utf-8"))
    assert record["world_state"]["fishing_water_tainted"] is False
    assert record["character_sheet"]["inventory"] == []
    assert record["character_sheet"]["xp"] == 550
    assert record["character_sheet"]["reputation"] == 25

    recovered_sheets = []

    async def save_recovered(current):
        recovered_sheets.append(copy.deepcopy(current))

    monkeypatch.setattr(character_manager, "save", save_recovered)

    assert asyncio.run(world_state.recover_pending_world_state_transaction()) is True
    assert asyncio.run(world_state.recover_pending_world_state_transaction()) is False
    assert json.loads(state_path.read_text(encoding="utf-8"))["fishing_water_tainted"] is False
    assert json.loads(journal_path.read_text(encoding="utf-8")) == {}
    assert recovered_sheets == [record["character_sheet"]]


def test_world_only_outcome_mutation_recovers_after_world_file_failure(monkeypatch, tmp_path):
    state_path, _, _ = _isolated_world_state(monkeypatch, tmp_path)
    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "blockade_active": True,
        "shop_price_mult": 1.35,
        "shop_price_mult_expiry": 4_000_000_000,
        "town_fund": 12_345,
    })
    original_write = world_state._write_world_state
    calls = []

    def fail_first_write(state, serialized):
        calls.append(copy.deepcopy(state))
        if len(calls) == 1:
            raise OSError("simulated blockade persistence failure")
        return original_write(state, serialized)

    monkeypatch.setattr(world_state, "_write_world_state", fail_first_write)

    def clear_blockade(state):
        changed = (
            state.get("blockade_active") is not False
            or state.get("shop_price_mult") != 1.0
            or state.get("shop_price_mult_expiry") != 0
        )
        state["blockade_active"] = False
        state["shop_price_mult"] = 1.0
        state["shop_price_mult_expiry"] = 0
        return changed

    with pytest.raises(OSError, match="blockade persistence"):
        asyncio.run(world_state.mutate_world_state_only(clear_blockade))

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["blockade_active"] is True
    assert persisted["town_fund"] == 12_345

    assert asyncio.run(world_state.mutate_world_state_only(clear_blockade)) is True
    assert asyncio.run(world_state.mutate_world_state_only(clear_blockade)) is False
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["blockade_active"] is False
    assert persisted["shop_price_mult"] == 1.0
    assert persisted["shop_price_mult_expiry"] == 0
    assert persisted["town_fund"] == 12_345
    assert len(calls) == 2


@pytest.mark.parametrize(
    "record",
    [
        None,
        [],
        "pending",
        {"world_state": {}, "character_sheet": {"user_id": "alice"}},
    ],
)
def test_malformed_world_transaction_journal_fails_closed_and_is_preserved(
    monkeypatch, tmp_path, record
):
    _, journal_path, _ = _isolated_world_state(monkeypatch, tmp_path)
    journal_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(RuntimeError, match="malformed"):
        asyncio.run(world_state.recover_pending_world_state_transaction())

    # Invalid records must remain available for diagnosis; never clear them.
    assert json.loads(journal_path.read_text(encoding="utf-8")) == record


def test_empty_world_transaction_journal_is_the_only_cleared_sentinel(
    monkeypatch, tmp_path
):
    _, journal_path, _ = _isolated_world_state(monkeypatch, tmp_path)
    journal_path.write_text("{}", encoding="utf-8")

    assert asyncio.run(world_state.recover_pending_world_state_transaction()) is False



def test_concurrent_world_only_updates_preserve_independent_keys(monkeypatch, tmp_path):
    state_path, _, _ = _isolated_world_state(monkeypatch, tmp_path)

    async def update(key):
        return await world_state.update_world_state(
            lambda state: state.update({key: "committed"})
        )

    async def run():
        return await asyncio.gather(update("writer_a"), update("writer_b"))

    results = asyncio.run(run())
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert results == [True, True]
    assert persisted["writer_a"] == "committed"
    assert persisted["writer_b"] == "committed"


def test_world_state_expiry_reads_do_not_write_outside_transaction(monkeypatch, tmp_path):
    state_path, _, _ = _isolated_world_state(monkeypatch, tmp_path)
    raw = {
        **world_state.DEFAULT_STATE,
        "atk_mod": 2,
        "atk_mod_expiry": 1,
        "shop_price_mult": 1.5,
        "shop_price_mult_expiry": 1,
        "blockade_active": True,
    }
    state_path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = world_state.load_world_state()
    assert loaded["atk_mod"] == 0
    assert loaded["atk_mod_expiry"] == 0
    assert loaded["shop_price_mult"] == 1.0
    assert loaded["blockade_active"] is False

    # The normalized view is in-memory only; the getter must not persist it.
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["atk_mod"] == 2
    assert on_disk["shop_price_mult"] == 1.5
    assert on_disk["blockade_active"] is True

    async def persist():
        await world_state.update_world_state(
            lambda state: state.update({"independent_update": True})
        )
    asyncio.run(persist())
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["atk_mod"] == 0
    assert persisted["shop_price_mult"] == 1.0
    assert persisted["blockade_active"] is False
    assert persisted["independent_update"] is True


def test_missing_person_world_event_and_character_reward_are_claimed_once(
    monkeypatch, tmp_path
):
    state_path, _, saved_sheets = _isolated_world_state(monkeypatch, tmp_path)
    from utils.ttrpg.forest_events import claim_missing_person

    world_state.save_world_state({
        **world_state.DEFAULT_STATE,
        "missing_person_name": "Mira",
        "missing_person_loc": "whisperwood_edge",
        "missing_person_expiry": 1_000_000,
    })
    alice = {
        "user_id": "alice", "location": "whisperwood_edge",
        "xp": 0, "gil": 0, "reputation": 0,
    }
    bob = {
        "user_id": "bob", "location": "whisperwood_edge",
        "xp": 0, "gil": 0, "reputation": 0,
    }

    def claim(sheet, state):
        name = claim_missing_person(state, sheet["location"], now=999_000)
        if name is None:
            return False, None
        sheet["xp"] += 100
        sheet["gil"] += 100
        sheet["reputation"] += 10
        return True, name

    async def run():
        return await asyncio.gather(
            world_state.mutate_world_state(claim, alice),
            world_state.mutate_world_state(claim, bob),
        )

    results = asyncio.run(run())
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert sorted(result is not None for result in results) == [False, True]
    assert [result for result in results if result is not None] == ["Mira"]
    assert persisted["missing_person_loc"] == ""
    assert persisted["missing_person_name"] == ""
    assert persisted["missing_person_expiry"] == 0
    assert len(saved_sheets) == 1
    assert saved_sheets[0]["xp"] == 100
    assert saved_sheets[0]["gil"] == 100
    assert saved_sheets[0]["reputation"] == 10



@pytest.mark.parametrize("payload", ["{not-json", "[]", "null", '"not-an-object"'])
def test_corrupt_world_state_fails_closed(monkeypatch, tmp_path, payload):
    state_path, _, _ = _isolated_world_state(monkeypatch, tmp_path)
    state_path.write_text(payload, encoding="utf-8")

    with pytest.raises(RuntimeError, match="Cannot safely load RPG world state"):
        world_state.load_world_state()


def test_nested_world_state_reads_do_not_mutate_cached_state(monkeypatch, tmp_path):
    state_path, _, _ = _isolated_world_state(monkeypatch, tmp_path)
    state_path.write_text(json.dumps({
        **world_state.DEFAULT_STATE,
        "special_item_sale": {"item": "lucky_charm", "price": 20},
    }), encoding="utf-8")

    first = world_state.load_world_state()
    first["special_item_sale"]["price"] = 0
    second = world_state.load_world_state()

    assert second["special_item_sale"] == {"item": "lucky_charm", "price": 20}
    assert json.loads(state_path.read_text(encoding="utf-8"))["special_item_sale"]["price"] == 20
