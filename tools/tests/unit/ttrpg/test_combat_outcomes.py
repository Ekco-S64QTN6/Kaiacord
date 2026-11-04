"""Fault-injection tests for durable, idempotent combat outcome commits."""
import asyncio
from copy import deepcopy

import pytest

from utils.ttrpg.combat_outcomes import commit_outcome, recover_pending_outcomes


def test_dungeon_victory_recovers_when_character_write_precedes_dungeon_write():
    persisted_sheet = {}
    persisted_dungeon = {"active_combat": {"combat_id": "fight-1"}}
    writes = {"sheet": 0, "dungeon": 0}

    async def save_sheet(sheet):
        writes["sheet"] += 1
        persisted_sheet.clear()
        persisted_sheet.update(deepcopy(sheet))

    async def save_dungeon(outcome):
        writes["dungeon"] += 1
        if writes["dungeon"] == 1:
            raise OSError("simulated crash between character and dungeon writes")
        persisted_dungeon.clear()
        persisted_dungeon.update(deepcopy(outcome["state_after"]))

    sheet = {"user_id": "42", "xp": 125, "gil": 75}
    outcome = {
        "outcome_id": "dungeon:42:fight-1:victory",
        "kind": "dungeon",
        "result": "victory",
        "combat_id": "fight-1",
        "state_after": {
            "rooms": {"room_1": {"cleared": True}},
            "xp_gained": 100,
            "gil_gained": 50,
        },
    }

    with pytest.raises(OSError):
        asyncio.run(commit_outcome(
            sheet,
            outcome,
            save_sheet=save_sheet,
            persist_encounter=save_dungeon,
        ))

    # The character reward and recovery payload are durable, while the old
    # encounter still exists: this is the exact crash window being repaired.
    assert persisted_sheet["xp"] == 125
    assert outcome["outcome_id"] in persisted_sheet["pending_combat_outcomes"]
    assert persisted_dungeon["active_combat"]["combat_id"] == "fight-1"

    recovered_sheet = deepcopy(persisted_sheet)
    recovered = asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"dungeon": save_dungeon},
    ))

    assert recovered == 1
    assert persisted_sheet["xp"] == 125
    assert "pending_combat_outcomes" not in persisted_sheet
    assert persisted_dungeon == outcome["state_after"]

    # A second boot/recovery does not reapply the reward or rewrite the outcome.
    second = asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"dungeon": save_dungeon},
    ))
    assert second == 0
    assert persisted_sheet["xp"] == 125
    assert writes["dungeon"] == 2


def test_dungeon_defeat_recovers_clear_after_character_penalty_write():
    persisted_sheet = {}
    dungeon_exists = {"value": True}
    writes = {"clear": 0}

    async def save_sheet(sheet):
        persisted_sheet.clear()
        persisted_sheet.update(deepcopy(sheet))

    async def clear_dungeon(_outcome):
        writes["clear"] += 1
        if writes["clear"] == 1:
            raise OSError("simulated crash before dungeon clear")
        dungeon_exists["value"] = False

    sheet = {
        "user_id": "42",
        "xp": 900,
        "gil": 190,
        "deaths": 1,
        "location": "shrine",
        "hp": {"current": 1, "max": 30},
    }
    outcome = {
        "outcome_id": "dungeon:42:fight-2:defeat",
        "kind": "dungeon",
        "result": "defeat",
        "combat_id": "fight-2",
        "clear_encounter": True,
        "state_after": None,
    }

    with pytest.raises(OSError):
        asyncio.run(commit_outcome(
            sheet,
            outcome,
            save_sheet=save_sheet,
            persist_encounter=clear_dungeon,
        ))

    assert persisted_sheet["xp"] == 900
    assert persisted_sheet["gil"] == 190
    assert persisted_sheet["deaths"] == 1
    assert dungeon_exists["value"] is True
    assert outcome["outcome_id"] in persisted_sheet["pending_combat_outcomes"]

    recovered_sheet = deepcopy(persisted_sheet)
    recovered = asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"dungeon": clear_dungeon},
    ))

    assert recovered == 1
    assert dungeon_exists["value"] is False
    assert persisted_sheet["deaths"] == 1
    assert persisted_sheet["xp"] == 900
    assert "pending_combat_outcomes" not in persisted_sheet
    assert asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"dungeon": clear_dungeon},
    )) == 0
    assert writes["clear"] == 2


def test_overworld_victory_recovery_removes_only_resolved_monster():
    persisted_sheet = {}
    session = {
        "channel_id": "123",
        "combat_active": True,
        "monsters": [
            {"id": "resolved-1", "aggro_uid": "42", "key": "goblin"},
            {"id": "another-player", "aggro_uid": "99", "key": "wolf"},
            {"id": "same-owner-other-fight", "aggro_uid": "42", "key": "slime"},
        ],
    }
    writes = {"session": 0}

    async def save_sheet(sheet):
        persisted_sheet.clear()
        persisted_sheet.update(deepcopy(sheet))

    async def save_session(outcome):
        writes["session"] += 1
        if writes["session"] == 1:
            raise OSError("simulated crash before shared session write")
        session["monsters"] = [
            m for m in session["monsters"]
            if not (
                str(m.get("aggro_uid")) == str(outcome["owner_id"])
                and str(m.get("id")) == str(outcome["monster_id"])
            )
        ]
        session["combat_active"] = bool(session["monsters"])

    sheet = {"user_id": "42", "xp": 440, "gil": 95, "inventory": ["rare_drop"]}
    outcome = {
        "outcome_id": "overworld:42:123:resolved-1:victory",
        "kind": "overworld",
        "result": "victory",
        "channel_id": "123",
        "owner_id": "42",
        "monster_id": "resolved-1",
    }

    with pytest.raises(OSError):
        asyncio.run(commit_outcome(
            sheet,
            outcome,
            save_sheet=save_sheet,
            persist_encounter=save_session,
        ))

    assert persisted_sheet["xp"] == 440
    assert persisted_sheet["inventory"] == ["rare_drop"]
    assert "pending_combat_outcomes" in persisted_sheet
    assert any(m["id"] == "resolved-1" for m in session["monsters"])

    recovered_sheet = deepcopy(persisted_sheet)

    async def recover_overworld(pending):
        await save_session(pending)

    recovered = asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"overworld": recover_overworld},
    ))

    assert recovered == 1
    assert [m["id"] for m in session["monsters"]] == [
        "another-player", "same-owner-other-fight"
    ]
    assert session["combat_active"] is True
    assert persisted_sheet["xp"] == 440
    assert persisted_sheet["inventory"] == ["rare_drop"]
    assert "pending_combat_outcomes" not in persisted_sheet

    # Recovery replay after a crash between session write and journal cleanup
    # is also safe: the monster ID is already absent, and no other player's
    # monster is removed.
    session["monsters"].append(
        {"id": "resolved-1", "aggro_uid": "42", "key": "goblin"}
    )
    recovered_sheet["pending_combat_outcomes"] = {
        outcome["outcome_id"]: outcome
    }
    asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"overworld": recover_overworld},
    ))
    assert [m["id"] for m in session["monsters"]] == [
        "another-player", "same-owner-other-fight"
    ]
    assert persisted_sheet["xp"] == 440


def test_overworld_defeat_recovers_after_character_penalty_write():
    persisted_sheet = {}
    session = {
        "channel_id": "456",
        "combat_active": True,
        "monsters": [
            {"id": "fallen-monster", "aggro_uid": "42", "key": "dire_wolf"},
            {"id": "other-player", "aggro_uid": "99", "key": "goblin"},
        ],
    }
    writes = {"session": 0}

    async def save_sheet(sheet):
        persisted_sheet.clear()
        persisted_sheet.update(deepcopy(sheet))

    async def save_session(outcome):
        writes["session"] += 1
        if writes["session"] == 1:
            raise OSError("simulated crash before defeat session update")
        session["monsters"] = [
            monster for monster in session["monsters"]
            if not (
                str(monster.get("aggro_uid")) == str(outcome["owner_id"])
                and str(monster.get("id")) == str(outcome["monster_id"])
            )
        ]
        session["combat_active"] = bool(session["monsters"])

    # The terminal handler has already applied the normal knockout penalty.
    sheet = {
        "user_id": "42",
        "xp": 810,
        "gil": 190,
        "deaths": 2,
        "hp": {"current": 1, "max": 30},
        "location": "shrine",
        "hunt_streak": 0,
    }
    outcome = {
        "outcome_id": "overworld:42:456:fallen-monster:defeat",
        "kind": "overworld",
        "result": "defeat",
        "channel_id": "456",
        "owner_id": "42",
        "monster_id": "fallen-monster",
    }

    with pytest.raises(OSError):
        asyncio.run(commit_outcome(
            sheet,
            outcome,
            save_sheet=save_sheet,
            persist_encounter=save_session,
        ))

    assert persisted_sheet["xp"] == 810
    assert persisted_sheet["gil"] == 190
    assert persisted_sheet["deaths"] == 2
    assert persisted_sheet["location"] == "shrine"
    assert [monster["id"] for monster in session["monsters"]] == [
        "fallen-monster", "other-player"
    ]

    recovered_sheet = deepcopy(persisted_sheet)

    async def recover_overworld(pending):
        await save_session(pending)

    assert asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"overworld": recover_overworld},
    )) == 1

    assert [monster["id"] for monster in session["monsters"]] == ["other-player"]
    assert session["combat_active"] is True
    assert persisted_sheet["xp"] == 810
    assert persisted_sheet["gil"] == 190
    assert persisted_sheet["deaths"] == 2
    assert "pending_combat_outcomes" not in persisted_sheet
    assert asyncio.run(recover_pending_outcomes(
        recovered_sheet,
        save_sheet=save_sheet,
        recoverers={"overworld": recover_overworld},
    )) == 0
    assert writes["session"] == 2


def test_unknown_journal_kind_is_preserved_for_future_recovery():
    persisted_sheet = {}
    async def save_sheet(sheet):
        persisted_sheet.clear()
        persisted_sheet.update(deepcopy(sheet))

    sheet = {
        "user_id": "42",
        "pending_combat_outcomes": {
            "future-version": {"outcome_id": "future-version", "kind": "v9"}
        },
    }

    recovered = asyncio.run(recover_pending_outcomes(
        sheet,
        save_sheet=save_sheet,
        recoverers={},
    ))

    assert recovered == 0
    assert "future-version" in sheet["pending_combat_outcomes"]
    assert writes == []


def test_a_completed_outcome_id_rejects_duplicate_commit_calls():
    writes = []
    encounter_writes = []
    async def save_sheet(sheet):
        writes.append(deepcopy(sheet))

    async def persist(outcome):
        encounter_writes.append(outcome["outcome_id"])

    sheet = {"user_id": "42", "xp": 100}
    outcome = {
        "outcome_id": "overworld:42:123:monster-1:victory",
        "kind": "overworld",
        "result": "victory",
    }

    first = asyncio.run(commit_outcome(
        sheet, outcome, save_sheet=save_sheet, persist_encounter=persist
    ))
    second = asyncio.run(commit_outcome(
        sheet, outcome, save_sheet=save_sheet, persist_encounter=persist
    ))

    assert first is True
    assert second is False
    assert encounter_writes == [outcome["outcome_id"]]
    assert "pending_combat_outcomes" not in sheet
    assert sheet["completed_combat_outcomes"] == [outcome["outcome_id"]]
