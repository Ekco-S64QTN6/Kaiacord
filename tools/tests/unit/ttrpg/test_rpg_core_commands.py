"""!rpg commands answering what was asked, checked against the real
discord.py send signature."""
import asyncio
import inspect
import types
from unittest.mock import AsyncMock

import discord

import utils.ttrpg.rpg_core_handler as cor

_SEND = inspect.signature(discord.abc.Messageable.send)


def _msg(sent):
    async def send(*a, **k):
        _SEND.bind(None, *a, **k)          # a keyword discord.py does not take raises here as it does there
        sent.append(k.get("embed"))
    return types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=send), mentions=[])


def _ctx():
    return types.SimpleNamespace()


def test_pray_refuses_without_crashing(monkeypatch):
    """Every refusal passed ephemeral=True to channel.send, which has no such
    parameter: a typed !rpg pray away from the shrine raised TypeError."""
    sheet = {"user_id": "42", "character_name": "P", "location": "oakhaven", "hp": {"current": 5, "max": 10}}
    monkeypatch.setattr(cor, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr("utils.ttrpg.housing.load_housing_async", AsyncMock(return_value=None))
    sent = []
    asyncio.run(cor._handle_pray(_ctx(), _msg(sent), None, "", "42", "p", False))
    assert "Shrine" in sent[0].description
    monkeypatch.setattr(cor, "load", AsyncMock(return_value=None))
    asyncio.run(cor._handle_pray(_ctx(), _msg(sent), None, "", "42", "p", False))
    assert len(sent) == 2

