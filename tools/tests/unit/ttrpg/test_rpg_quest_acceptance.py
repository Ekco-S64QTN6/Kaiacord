"""Quest acceptance must revalidate current persistent progress, not the NPC menu snapshot."""
import asyncio
import copy
from unittest.mock import AsyncMock

from utils.ttrpg import rpg_social_handler as social


QUEST = {
    "id": "arrival",
    "name": "A Stranger in the Mud",
    "requirements": {"level": 1},
    "tasks": ["talk_barkeep", "talk_hemlock", "talk_elara"],
}


def test_completed_quest_cannot_be_reaccepted_from_a_stale_npc_button(monkeypatch):
    sheet = {
        "user_id": "42",
        "level": 5,
        "active_quests": [],
        "completed_quests": ["arrival"],
    }
    save = AsyncMock()
    monkeypatch.setattr(social, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(social, "save", save)

    accepted, error = asyncio.run(social._accept_quest_for_player("42", QUEST))

    assert not accepted
    assert "already completed" in error.lower()
    assert sheet["active_quests"] == []
    save.assert_not_awaited()


def test_concurrent_stale_quest_buttons_only_accept_once(monkeypatch):
    persisted = {
        "user_id": "42",
        "level": 5,
        "active_quests": [],
        "completed_quests": [],
    }
    saves = []

    async def load(uid):
        return copy.deepcopy(persisted)

    async def save(sheet):
        persisted.update(copy.deepcopy(sheet))
        saves.append(copy.deepcopy(sheet))

    monkeypatch.setattr(social, "load", load)
    monkeypatch.setattr(social, "save", save)

    async def go():
        return await asyncio.gather(
            social._accept_quest_for_player("42", QUEST),
            social._accept_quest_for_player("42", QUEST),
        )

    results = asyncio.run(go())

    assert sum(1 for accepted, _ in results if accepted) == 1
    assert persisted["active_quests"] == ["arrival"]
    assert len(saves) == 1


def test_quest_acceptance_rechecks_level_against_fresh_sheet():
    sheet = {
        "level": 2,
        "active_quests": [],
        "completed_quests": [],
    }
    quest = {**QUEST, "requirements": {"level": 3}}
    accepted, error = social._accept_quest_on_sheet(sheet, quest)
    assert not accepted
    assert "level 3" in error
    assert sheet["active_quests"] == []
