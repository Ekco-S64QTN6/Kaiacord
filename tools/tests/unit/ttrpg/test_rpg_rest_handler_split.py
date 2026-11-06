"""Stone Hearth rest shares the recovery module without changing its core API."""
import asyncio
import copy
from unittest.mock import AsyncMock
from types import SimpleNamespace

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_recovery_handler as recovery


def _message():
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def test_core_rest_adapter_forwards_persistence_and_view_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(recovery, "_handle_rest", replacement)
    args = (object(), object(), None, "", "42", "Ash", False)

    assert asyncio.run(core._handle_rest(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["save_character"] is core.save
    assert kwargs["no_character_handler"] is core.no_character
    assert kwargs["status_view_factory"] is core._make_status_view


def test_rest_removes_ale_temp_hp_before_healing_and_charging(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "stone_hearth",
        "gil": 20,
        "hp": {"current": 8, "max": 13},
        "conditions": ["ale_warmth", "blessed"],
    }
    saves = []

    async def load(_uid):
        return sheet

    async def save(value):
        saves.append(copy.deepcopy(value))

    monkeypatch.setattr(core, "load", load)
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")
    monkeypatch.setattr("utils.ttrpg.calendar.get_special_day", lambda: None)
    msg, sent = _message()

    asyncio.run(core._handle_rest(None, msg, None, "", "42", "Ash", False))

    assert sheet["hp"] == {"current": 10, "max": 10}
    assert sheet["conditions"] == ["blessed"]
    assert sheet["gil"] == 15
    assert sheet["inn_rest_pending"] is True
    assert saves == [sheet]
    (embed, view), = sent
    assert "HP restored: **+2**" in embed.description
    assert "(-5 gil)" in embed.description
    assert view == "status-view"


def test_hearthday_rest_is_free_even_with_no_gil(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "stone_hearth",
        "gil": 0,
        "hp": {"current": 2, "max": 10},
        "conditions": [],
    }
    saves = []

    async def save(value):
        saves.append(copy.deepcopy(value))

    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")
    monkeypatch.setattr(
        "utils.ttrpg.calendar.get_special_day",
        lambda: {"buff": "hearthday_warmth"},
    )
    msg, sent = _message()

    asyncio.run(core._handle_rest(None, msg, None, "", "42", "Ash", False))

    assert sheet["hp"]["current"] == 10
    assert sheet["gil"] == 0
    assert sheet["inn_rest_pending"] is True
    assert saves == [sheet]
    (embed, view), = sent
    assert "(-0 gil)" in embed.description
    assert "rest is free today" in embed.description
    assert view == "status-view"


def test_full_health_without_ale_does_not_charge_or_save(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "stone_hearth",
        "gil": 20,
        "hp": {"current": 10, "max": 10},
        "conditions": [],
    }
    save = AsyncMock()
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr("utils.ttrpg.calendar.get_special_day", lambda: None)
    msg, sent = _message()

    asyncio.run(core._handle_rest(None, msg, None, "", "42", "Ash", False))

    save.assert_not_awaited()
    assert sheet["gil"] == 20
    (embed, view), = sent
    assert "already at maximum health" in embed.description
    assert view is None
