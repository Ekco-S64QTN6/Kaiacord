"""The dungeon combat entry point coordinates context, exchange and outcomes."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_combat_handler as combat


@pytest.mark.parametrize(
    ("result", "selected"),
    [
        ({"monster_defeated": True, "player_alive": True}, "_finish_dungeon_victory"),
        ({"monster_defeated": False, "player_alive": False}, "_finish_dungeon_defeat"),
        ({"monster_defeated": False, "player_alive": True}, "_continue_dungeon_combat_round"),
    ],
)
def test_dungeon_round_dispatches_to_exactly_one_outcome(monkeypatch, result, selected):
    encounter = {"active": True}
    round_data = {"res": result}
    monkeypatch.setattr(
        combat, "_load_dungeon_combat_context", AsyncMock(return_value=encounter)
    )
    monkeypatch.setattr(
        combat, "_resolve_dungeon_combat_exchange", AsyncMock(return_value=round_data)
    )
    handlers = {
        name: AsyncMock()
        for name in (
            "_finish_dungeon_victory",
            "_finish_dungeon_defeat",
            "_continue_dungeon_combat_round",
        )
    }
    for name, handler in handlers.items():
        monkeypatch.setattr(combat, name, handler)

    # The serializer has its own independent concurrency tests. Exercise the
    # wrapped handler body here so this test isolates branch dispatch.
    asyncio.run(
        combat._dungeon_combat_round.__wrapped__(
            None, SimpleNamespace(), "u1", "Ash", False
        )
    )

    for name, handler in handlers.items():
        assert handler.await_count == (1 if name == selected else 0), name
    combat._resolve_dungeon_combat_exchange.assert_awaited_once_with(encounter)


def test_dungeon_round_with_no_active_encounter_sends_ephemeral_notice(monkeypatch):
    followup = SimpleNamespace(send=AsyncMock())
    interaction = SimpleNamespace(followup=followup)
    monkeypatch.setattr(
        combat, "_load_dungeon_combat_context", AsyncMock(return_value={"active": False})
    )
    resolve = AsyncMock()
    monkeypatch.setattr(combat, "_resolve_dungeon_combat_exchange", resolve)

    asyncio.run(
        combat._dungeon_combat_round.__wrapped__(
            None, interaction, "u1", "Ash", False
        )
    )

    followup.send.assert_awaited_once_with("No active combat.", ephemeral=True)
    resolve.assert_not_awaited()


def test_context_persists_a_stable_combat_id_before_first_round(monkeypatch):
    from utils.ttrpg import dungeon

    sheet = {"user_id": "u1", "location": "whisperwood_deep"}
    state = {
        "active_combat": {
            "monster": {"name": "Wight"},
            "monster_key": "wight",
            "room_key": "0,0",
        }
    }
    saved = []

    async def save_dungeon(uid, saved_state):
        saved.append((uid, saved_state))

    monkeypatch.setattr(combat, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(combat, "_recover_pending_combat_outcomes", AsyncMock())
    monkeypatch.setattr(dungeon, "load_dungeon", AsyncMock(return_value=state))
    monkeypatch.setattr(dungeon, "save_dungeon", save_dungeon)

    encounter = asyncio.run(combat._load_dungeon_combat_context("u1"))

    assert encounter["active"] is True
    assert encounter["combat_id"]
    assert state["active_combat"]["combat_id"] == encounter["combat_id"]
    assert saved == [("u1", state)]
