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


def _look(monkeypatch, target):
    sheet = {"user_id": "42", "character_name": "P", "location": "shrine", "inventory": [], "secrets": []}
    monkeypatch.setattr(cor, "load", AsyncMock(return_value=sheet))
    save = AsyncMock()
    monkeypatch.setattr(cor, "save", save)
    sent = []
    asyncio.run(cor._handle_look(_ctx(), _msg(sent), None, target, "42", "p", False))
    return sheet, sent


def test_look_at_matches_whole_words(monkeypatch):
    """'look at l' matched 'flame' as a substring and recorded a piece of the
    shrine puzzle."""
    sheet, sent = _look(monkeypatch, "at l")
    assert sheet["secrets"] == [] and "Nothing unusual" in sent[0].description
    sheet, _ = _look(monkeypatch, "at the flame")
    assert sheet["secrets"] == ["look_flame"]



def test_admin_give_strips_mentioned_recipient_before_item_lookup(monkeypatch):
    """!rpg give @player tonic must resolve tonic, not the mention token."""
    sheet = {"user_id": "99", "character_name": "Target", "inventory": []}
    loaded = []
    saved = []

    async def load(uid):
        loaded.append(str(uid))
        return sheet

    async def save(value):
        saved.append(dict(value))

    sent = []
    msg = types.SimpleNamespace(
        mentions=[types.SimpleNamespace(id=99)],
        channel=types.SimpleNamespace(send=AsyncMock(side_effect=lambda **kw: sent.append(kw["embed"])))
    )
    monkeypatch.setattr(cor, "load", load)
    monkeypatch.setattr(cor, "save", save)

    asyncio.run(cor._handle_give(_ctx(), msg, None, "<@99> tonic", "42", "Admin", True))

    assert loaded == ["99"]
    assert sheet["inventory"] == ["tonic"]
    assert saved and "tonic" in sent[0].description


def test_admin_mutations_hold_target_lock_but_do_not_reacquire_self_lock(monkeypatch):
    from utils.ttrpg.session_manager import get_action_lock

    target = {"user_id": "99", "character_name": "Target", "inventory": [],
              "hp": {"current": 2, "max": 20}}
    caller = {"user_id": "42", "character_name": "Admin", "inventory": [],
              "hp": {"current": 1, "max": 10}}
    lock_observations = []

    async def load(uid):
        return target if str(uid) == "99" else caller

    async def save(sheet):
        lock = await get_action_lock(f"user:{sheet['user_id']}")
        lock_observations.append((sheet["user_id"], lock.locked()))

    async def channel_send(*args, **kwargs):
        return None

    monkeypatch.setattr(cor, "load", load)
    monkeypatch.setattr(cor, "save", save)
    msg = types.SimpleNamespace(mentions=[types.SimpleNamespace(id=99)],
                               channel=types.SimpleNamespace(send=channel_send))

    async def go():
        target_lock = await get_action_lock("user:99")
        await cor._handle_give(_ctx(), msg, None, "<@99> tonic", "42", "Admin", True)
        assert lock_observations[-1] == ("99", True)

        caller_lock = await get_action_lock("user:42")
        async with caller_lock:
            self_msg = types.SimpleNamespace(mentions=[], channel=types.SimpleNamespace(send=channel_send))
            await asyncio.wait_for(
                cor._handle_heal(_ctx(), self_msg, None, "", "42", "Admin", True),
                timeout=2
            )
        assert lock_observations[-1] == ("42", True)

    asyncio.run(go())
    assert target["inventory"] == ["tonic"]
    assert target["hp"]["current"] == 2
    assert caller["hp"]["current"] == 10
