"""Shrine prayer and offering handlers retain their core command contracts."""
import asyncio
import copy
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_shrine_handler as shrine


@pytest.mark.parametrize(
    ("name", "dependencies"),
    [
        ("_handle_pray", ("load_character", "save_character", "status_view_factory")),
        ("_handle_offer", (
            "load_character", "save_character", "no_character_handler",
            "player_locked_decorator", "check_level_up_fn", "xp_to_next_level_fn",
            "status_btn_factory",
        )),
    ],
)
def test_core_shrine_adapters_forward_patchable_dependencies(monkeypatch, name, dependencies):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(shrine, name, replacement)
    args = (object(), object(), None, "", "42", "Ash", False)

    assert asyncio.run(getattr(core, name)(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["save_character"] is core.save
    if "no_character_handler" in dependencies:
        assert kwargs["no_character_handler"] is core.no_character
    if "status_view_factory" in dependencies:
        assert kwargs["status_view_factory"] is core._make_status_view
    if "player_locked_decorator" in dependencies:
        assert kwargs["player_locked_decorator"] is core.player_locked
    if "check_level_up_fn" in dependencies:
        assert kwargs["check_level_up_fn"] is core.check_level_up
    if "xp_to_next_level_fn" in dependencies:
        assert kwargs["xp_to_next_level_fn"] is core.xp_to_next_level
    if "status_btn_factory" in dependencies:
        assert kwargs["status_btn_factory"] is core._make_status_btn
    assert all(dependency in kwargs for dependency in dependencies)


def _sent_message():
    sent = []

    async def send(*args, embed=None, view=None, **kwargs):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(id=7, send=send)), sent


def _prepare_pray(monkeypatch, sheet, *, special=None, world_state=None):
    saves = []

    async def load(uid):
        assert str(uid) == "42"
        return sheet

    async def save(value):
        saves.append(copy.deepcopy(value))

    monkeypatch.setattr(core, "load", load)
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")
    monkeypatch.setattr(
        "utils.ttrpg.housing.load_housing_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "utils.ttrpg.calendar.get_special_day",
        lambda: special,
    )
    monkeypatch.setattr(
        "utils.ttrpg.world_state.load_world_state",
        lambda: world_state or {},
    )
    return saves


def test_pray_grants_daily_blessing_and_tracks_an_active_shrine_quest(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "shrine",
        "hp": {"current": 5, "max": 10},
        "active_quests": ["silent_prayer"],
        "quest_progress": {},
        "conditions": [],
    }
    monkeypatch.setattr(
        "utils.ttrpg.quest_registry.get_quest",
        lambda quest_id: {"tasks": ["pray_shrine"]} if quest_id == "silent_prayer" else None,
    )
    saves = _prepare_pray(monkeypatch, sheet)
    msg, sent = _sent_message()

    asyncio.run(core._handle_pray(None, msg, None, "", "42", "Ash", False))

    assert sheet["conditions"] == ["blessed"]
    assert sheet["last_pray_date"] == date.today().strftime("%Y-%m-%d")
    assert sheet["quest_progress"] == {"silent_prayer": ["pray_shrine"]}
    assert saves == [sheet]
    (embed, view), = sent
    assert "next hunt grants +2" in embed.description
    assert view == "status-view"


def test_pray_vigil_grants_five_hp_and_blessing(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "shrine",
        "hp": {"current": 5, "max": 10},
        "conditions": [],
    }
    saves = _prepare_pray(
        monkeypatch,
        sheet,
        world_state={"blessing_window_until": time.time() + 300},
    )
    msg, sent = _sent_message()

    asyncio.run(core._handle_pray(None, msg, None, "", "42", "Ash", False))

    assert sheet["hp"]["current"] == 10
    assert sheet["conditions"] == ["blessed"]
    assert saves == [sheet]
    (embed, view), = sent
    assert "+5 HP restored" in embed.description
    assert view == "status-view"


@pytest.mark.parametrize(
    ("special", "expected_xp", "cap_text"),
    [
        (None, 10, "20"),
        ({"buff": "solstice_blessing"}, 30, "60"),
    ],
)
def test_offer_button_applies_the_daily_cap_and_xp_multiplier_under_player_lock(
    monkeypatch, special, expected_xp, cap_text
):
    store = {
        "42": {
            "user_id": "42",
            "character_name": "Ash",
            "location": "shrine",
            "gil": 20,
            "xp": 100,
            "level": 3,
            "conditions": [],
            "offered_today": {},
        }
    }
    save_lock_states = []

    async def load(uid):
        assert str(uid) == "42"
        return copy.deepcopy(store["42"])

    async def save(sheet):
        from utils.ttrpg.session_manager import get_action_lock

        lock = await get_action_lock("user:42")
        save_lock_states.append(lock.locked())
        store[str(sheet["user_id"])] = copy.deepcopy(sheet)

    monkeypatch.setattr(core, "load", load)
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "check_level_up", lambda _sheet: (False, 3))
    monkeypatch.setattr(core, "xp_to_next_level", lambda _level: 1000)
    monkeypatch.setattr(core, "_make_status_btn", lambda *args: discord.ui.Button(label="Status"))
    monkeypatch.setattr("utils.ttrpg.calendar.get_special_day", lambda: special)
    monkeypatch.setattr("utils.ttrpg.world_state.load_world_state", lambda: {})

    msg, sent = _sent_message()

    async def run():
        await core._handle_offer(None, msg, None, "", "42", "Ash", False)
        embed, view = sent[0]
        assert cap_text in embed.description
        button = next(child for child in view.children if child.label == "10g")
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        await button.callback(interaction)
        return interaction

    interaction = asyncio.run(run())

    assert store["42"]["gil"] == 10
    assert store["42"]["xp"] == 100 + expected_xp
    assert store["42"]["offered_today"] == {
        date.today().strftime("%Y-%m-%d"): 10
    }
    assert save_lock_states == [True]
    interaction.response.send_message.assert_awaited_once()
    assert f"+{expected_xp} XP" in interaction.response.send_message.await_args.kwargs["embed"].description


def test_offer_refuses_when_the_daily_cap_is_already_used(monkeypatch):
    today = date.today().strftime("%Y-%m-%d")
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "shrine",
        "gil": 50,
        "xp": 100,
        "offered_today": {today: 20},
    }
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr("utils.ttrpg.calendar.get_special_day", lambda: None)
    msg, sent = _sent_message()

    asyncio.run(core._handle_offer(None, msg, None, "", "42", "Ash", False))

    (embed, view), = sent
    assert "reached today's offering limit" in embed.description
    assert view is None
