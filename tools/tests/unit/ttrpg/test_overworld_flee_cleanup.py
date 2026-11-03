"""Overworld flee must persist removal of encounter-scoped consumable buffs."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from utils.ttrpg import rpg_combat_handler as combat


def test_overworld_flee_saves_buff_cleanup_with_hunt_cost(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "P",
        "hunts_today": 1,
        "conditions": ["embered", "fortified", "poisoned", "ale_warmth"],
    }
    session = {
        "channel_id": "123",
        "combat_active": True,
        "monsters": [{"key": "blood_slime", "name": "Blood Slime", "aggro_uid": "42"}],
    }
    saved_sheets = []
    saved_sessions = []

    async def load_sheet(uid):
        return sheet

    async def save_sheet(value):
        saved_sheets.append({
            "hunts_today": value["hunts_today"],
            "conditions": list(value["conditions"]),
        })

    async def load_channel_session(channel_id):
        return session

    async def save_channel_session(value):
        saved_sessions.append(value)

    monkeypatch.setattr(combat, "load", load_sheet)
    monkeypatch.setattr(combat, "save", save_sheet)
    monkeypatch.setattr(combat, "load_session", load_channel_session)
    monkeypatch.setattr(combat, "save_session", save_channel_session)
    monkeypatch.setattr(combat, "_make_hunt_status_view", lambda *args, **kwargs: None)

    from utils.ttrpg import outing
    monkeypatch.setattr(outing, "note", AsyncMock())

    channel = MagicMock()
    channel.send = AsyncMock()
    msg = MagicMock()
    msg.channel = channel

    asyncio.run(combat._handle_flee.__wrapped__(
        None, msg, None, "", "42", "P", False
    ))

    assert saved_sheets == [{
        "hunts_today": 2,
        "conditions": ["poisoned", "ale_warmth"],
    }]
    assert session["monsters"] == []
    assert session["combat_active"] is False
    assert saved_sessions == [session]


def test_overworld_flee_handles_missing_character_without_attribute_error(monkeypatch):
    monkeypatch.setattr(combat, "load", AsyncMock(return_value=None))
    monkeypatch.setattr(combat, "load_session", AsyncMock(return_value={
        "combat_active": True,
        "monsters": [{"key": "blood_slime", "aggro_uid": "42"}],
    }))
    msg = MagicMock()
    msg.channel.send = AsyncMock()
    monkeypatch.setattr(combat, "no_character", AsyncMock())

    asyncio.run(combat._handle_flee.__wrapped__(
        None, msg, None, "", "42", "P", False
    ))

    combat.no_character.assert_awaited_once_with(msg)
