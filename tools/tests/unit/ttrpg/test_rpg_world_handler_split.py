"""World information commands live outside the core state handler."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_world_handler as world


@pytest.mark.parametrize("name", ["_handle_rumor", "_handle_calendar", "_handle_weather"])
def test_core_compatibility_entry_points_forward_to_world_handler(monkeypatch, name):
    called = []

    async def replacement(*args):
        called.append(args)
        return "forwarded"

    monkeypatch.setattr(world, name, replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)
    result = asyncio.run(getattr(core, name)(*args))

    assert result == "forwarded"
    assert called == [args]


def _message():
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def test_calendar_command_builds_embed_from_calendar_data(monkeypatch):
    from utils.ttrpg import calendar

    monkeypatch.setattr(calendar, "get_today_summary", lambda: {
        "season": "spring",
        "season_emoji": "🌱",
        "season_name": "Spring",
        "date": "5 Rainmoot",
        "season_flavor": "The woods wake.",
        "special_day": None,
    })
    monkeypatch.setattr(calendar, "SPECIAL_DAYS", {})
    monkeypatch.setattr(world, "_make_status_view", lambda *args: "status-view")
    msg, sent = _message()

    asyncio.run(world._handle_calendar(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.title == "🌱 Spring — 5 Rainmoot"
    assert "ordinary day" in embed.fields[0].value
    assert view == "status-view"


def test_weather_command_builds_embed_from_deterministic_weather(monkeypatch):
    from utils.ttrpg import calendar

    monkeypatch.setattr(calendar, "get_weather", lambda: {
        "key": "clear",
        "desc": "Clear skies over the Whisperwood.",
        "emoji": "☀️",
        "name": "Clear",
        "effect": None,
    })
    monkeypatch.setattr(calendar, "get_today_summary", lambda: {
        "date": "5 Rainmoot",
        "season_name": "Spring",
    })
    monkeypatch.setattr(world, "_make_status_view", lambda *args: "status-view")
    msg, sent = _message()

    asyncio.run(world._handle_weather(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.title == "☀️ Clear — 5 Rainmoot"
    assert "Clear skies" in embed.description
    assert view == "status-view"
