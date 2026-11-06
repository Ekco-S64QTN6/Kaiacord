"""Watchtower and Tactical War Map scouting remain behind the core command API."""
import asyncio
import copy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_scout_handler as scout


def test_core_scout_adapter_forwards_patchable_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(scout, "_handle_scout", replacement)
    args = (object(), object(), None, "", "42", "Ash", False)

    assert asyncio.run(core._handle_scout(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["save_character"] is core.save
    assert kwargs["status_view_factory"] is core._make_status_view
    assert kwargs["secrets_module"] is core.secrets


def _message():
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def _patch_scout_world(monkeypatch, *, weather=None, home_bonuses=None, watchtower_bonus=False):
    from utils.ttrpg import calendar, furniture, housing, monster_registry, world_state

    monsters = {
        "wolf": {"name": "Wolf", "tier": "easy", "xp": 12},
    }
    tables = {
        "whisperwood_edge": [("wolf", 1)],
        "whisperwood_deep": [("wolf", 1)],
        "aeridor_ruins": [("wolf", 1)],
        "trade_road": [("wolf", 1)],
    }
    monkeypatch.setattr(monster_registry, "MONSTERS", monsters)
    monkeypatch.setattr(monster_registry, "ENCOUNTER_TABLES", tables)
    monkeypatch.setattr(calendar, "get_weather", lambda: weather or {
        "emoji": "☀️", "name": "Clear", "effect": None,
    })
    monkeypatch.setattr(calendar, "get_season", lambda: "spring")
    monkeypatch.setattr(calendar, "SEASONAL_MONSTERS", {})
    monkeypatch.setattr(
        housing,
        "load_housing_async",
        AsyncMock(return_value={"fixture": True} if home_bonuses else None),
    )
    monkeypatch.setattr(
        furniture, "get_home_bonuses", lambda _housing: home_bonuses or {}
    )
    monkeypatch.setattr(
        world_state, "load_world_state",
        lambda: {"watchtower_bonus": watchtower_bonus},
    )
    monkeypatch.setattr(core.secrets, "randbelow", lambda _upper: 0)


def test_watchtower_scout_persists_daily_usage_and_spawn_preview(monkeypatch):
    today = date.today().strftime("%Y-%m-%d")
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "watchtower",
        "scout_date": today,
        "last_scout_date": today,
        "tower_scouts_today": 0,
        "home_scouts_today": 0,
        "scouted_spawns": {},
    }
    saves = []

    async def save(value):
        saves.append(copy.deepcopy(value))

    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")
    _patch_scout_world(monkeypatch)
    msg, sent = _message()

    asyncio.run(core._handle_scout(None, msg, None, "", "42", "Ash", False))

    assert sheet["tower_scouts_today"] == 1
    assert sheet["home_scouts_today"] == 0
    assert sheet["scout_date"] == today
    assert sheet["last_scout_date"] == today
    assert sheet["scouted_spawns"] == {
        "whisperwood_edge": ["wolf"],
        "whisperwood_deep": ["wolf"],
        "aeridor_ruins": ["wolf"],
        "trade_road": ["wolf"],
    }
    assert saves == [sheet]
    (embed, view), = sent
    assert "Scout Report" in embed.description
    assert "Wolf" in embed.description
    assert "Watchtower Intel (1/1 tower check used)" in embed.footer.text
    assert view == "status-view"


def test_scout_blocked_weather_does_not_consume_a_daily_check(monkeypatch):
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "watchtower",
        "scout_date": date.today().strftime("%Y-%m-%d"),
        "last_scout_date": date.today().strftime("%Y-%m-%d"),
        "tower_scouts_today": 0,
        "home_scouts_today": 0,
    }
    save = AsyncMock()
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    _patch_scout_world(
        monkeypatch,
        weather={
            "emoji": "🌫️",
            "name": "Blinding Fog",
            "effect": {"type": "scout_blocked", "desc": "The tower cannot see through the fog."},
        },
    )
    msg, sent = _message()

    asyncio.run(core._handle_scout(None, msg, None, "", "42", "Ash", False))

    save.assert_not_awaited()
    assert sheet["tower_scouts_today"] == 0
    (embed, view), = sent
    assert "Scouting Blocked" in embed.description
    assert view is None


def test_tactical_war_map_enforces_two_home_scans_per_day(monkeypatch):
    today = date.today().strftime("%Y-%m-%d")
    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "housing_district",
        "scout_date": today,
        "last_scout_date": today,
        "home_scouts_today": 2,
        "tower_scouts_today": 0,
    }
    save = AsyncMock()
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    _patch_scout_world(monkeypatch, home_bonuses={"home_scout": True})
    msg, sent = _message()

    asyncio.run(core._handle_scout(None, msg, None, "", "42", "Ash", False))

    save.assert_not_awaited()
    (embed, view), = sent
    assert "already studied your Tactical War Map twice today" in embed.description
    assert view is None
