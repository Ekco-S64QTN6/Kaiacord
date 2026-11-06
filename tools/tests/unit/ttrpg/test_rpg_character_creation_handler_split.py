"""Character creation can move without changing the command entry point."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_character_creation_handler as creation


def _message():
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def test_core_creation_adapter_forwards_existing_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(creation, "_handle_new", replacement)
    args = (object(), object(), None, "Ash Human Warrior", "42", "Ash", False)

    assert asyncio.run(core._handle_new(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["create_character"] is core.create
    assert kwargs["roll_fn"] is core.dice_engine.roll
    assert kwargs["class_registry"] is core.dice_engine.CLASSES


def test_new_character_rolls_four_d6_drop_lowest_then_applies_race_bonuses(monkeypatch):
    create = AsyncMock(return_value={})
    roll_calls = []

    def roll(expression):
        roll_calls.append(expression)
        return (4, "4")

    monkeypatch.setattr(core, "load", AsyncMock(return_value=None))
    monkeypatch.setattr(core, "create", create)
    monkeypatch.setattr(core.dice_engine, "roll", roll)
    monkeypatch.setattr(core.dice_engine, "CLASSES", {"Warrior": {}})
    msg, sent = _message()

    asyncio.run(core._handle_new(None, msg, None, "Ash Elf Warrior", "42", "Ash", False))

    assert roll_calls == ["d6"] * 24
    create.assert_awaited_once_with(
        "42",
        "Ash",
        "Ash",
        "Elf",
        "Warrior",
        {
            "str": 12,
            "dex": 14,
            "con": 12,
            "int": 13,
            "wis": 13,
            "cha": 12,
        },
    )
    (embed, view), = sent
    assert embed.title == "✨ New Adventurer Registered"
    assert "Ash, the Elf Warrior" in embed.description
    assert view is None


def test_new_character_rejects_an_unknown_race_before_rolling_or_creating(monkeypatch):
    create = AsyncMock()
    roll = AsyncMock()
    monkeypatch.setattr(core, "load", AsyncMock(return_value=None))
    monkeypatch.setattr(core, "create", create)
    monkeypatch.setattr(core.dice_engine, "roll", roll)
    monkeypatch.setattr(core.dice_engine, "CLASSES", {"Warrior": {}})
    msg, sent = _message()

    asyncio.run(core._handle_new(None, msg, None, "Ash Orc Warrior", "42", "Ash", False))

    create.assert_not_awaited()
    roll.assert_not_awaited()
    (embed, _view), = sent
    assert "Unknown race: **Orc**" in embed.description


def test_new_character_does_not_overwrite_an_existing_sheet(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(
        core,
        "load",
        AsyncMock(return_value={"character_name": "Existing"}),
    )
    monkeypatch.setattr(core, "create", create)
    msg, sent = _message()

    asyncio.run(core._handle_new(None, msg, None, "New Human Warrior", "42", "Ash", False))

    create.assert_not_awaited()
    (embed, _view), = sent
    assert "You already have a character: **Existing**" in embed.description
