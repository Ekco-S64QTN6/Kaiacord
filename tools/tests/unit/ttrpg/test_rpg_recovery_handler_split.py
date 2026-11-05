"""Pond purification and player recovery actions live outside the core handler."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_recovery_handler as recovery


@pytest.mark.parametrize(
    ("name", "deps"),
    [
        ("_handle_purify", ("load_character", "no_character_handler")),
        ("_handle_drink", ("load_character", "save_character", "make_status_view",
                           "hunts_remaining_fn", "get_max_hunts_fn")),
        ("_handle_fountain", ("load_character", "save_character", "make_status_view")),
    ],
)
def test_core_recovery_adapters_forward_patchable_dependencies(monkeypatch, name, deps):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(recovery, name, replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)
    assert asyncio.run(getattr(core, name)(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["no_character_handler"] is core.no_character
    if "save_character" in deps:
        assert kwargs["save_character"] is core.save
    if "make_status_view" in deps:
        assert kwargs["make_status_view"] is core._make_status_view
    assert all(name in kwargs for name in deps)


def _message():
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def test_purify_applies_player_and_world_changes_as_one_mutation(monkeypatch):
    from utils.ttrpg import broadcast, progression, world_state

    sheet = {
        "user_id": "u1",
        "character_name": "Ash",
        "location": "tricklebrook_pond",
        "inventory": ["healing_herb"],
        "xp": 100,
        "reputation": 4,
    }
    water = {"fishing_water_tainted": True, "fishing_water_tainted_expiry": 123}
    mutations = []

    async def mutate(mutation, player_sheet):
        changed, result = mutation(player_sheet, water)
        mutations.append((changed, result))
        return result

    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(world_state, "mutate_world_state", mutate)
    monkeypatch.setattr(progression, "check_level_up", lambda _sheet: (False, 1))
    monkeypatch.setattr(broadcast, "log_world_event", AsyncMock())
    monkeypatch.setattr(broadcast, "broadcast_world_event", AsyncMock())
    msg, sent = _message()

    asyncio.run(core._handle_purify(None, msg, None, "", "u1", "Ash", False))

    assert mutations[0][0] is True
    assert mutations[0][1]["ok"] is True
    assert sheet["inventory"] == []
    assert sheet["xp"] == 150
    assert sheet["reputation"] == 19
    assert water == {
        "fishing_water_tainted": False,
        "fishing_water_tainted_expiry": 0,
    }
    (embed, _view), = sent
    assert embed.title == "🌊 Tricklebrook Pond Purified!"
    assert "Ash" in embed.description


def test_drink_applies_nonstacking_temporary_hp_and_saves(monkeypatch):
    sheet = {
        "user_id": "u1",
        "character_name": "Ash",
        "location": "stone_hearth",
        "gil": 5,
        "hp": {"current": 5, "max": 10},
        "conditions": [],
    }
    saves = []

    async def save(value):
        saves.append(dict(value))

    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")
    msg, sent = _message()

    asyncio.run(core._handle_drink(
        None, msg, None, "", "u1", "Ash", False
    ))

    assert sheet["gil"] == 3
    assert sheet["hp"] == {"current": 8, "max": 13}
    assert sheet["conditions"] == ["ale_warmth"]
    assert saves == [sheet]
    (embed, view), = sent
    assert "-2 gil" in embed.description
    assert view == "status-view"


def test_fountain_fully_heals_and_persists_once(monkeypatch):
    sheet = {
        "user_id": "u1",
        "character_name": "Ash",
        "location": "shrine",
        "hp": {"current": 2, "max": 17},
    }
    saves = []

    async def save(value):
        saves.append(dict(value))

    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")
    msg, sent = _message()

    asyncio.run(core._handle_fountain(
        None, msg, None, "", "u1", "Ash", False
    ))

    assert sheet["hp"]["current"] == 17
    assert sheet["last_fountain_date"]
    assert saves == [sheet]
    (embed, view), = sent
    assert "fully recovered" in embed.description
    assert view == "status-view"
