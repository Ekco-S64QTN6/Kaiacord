"""Seed-shop view callbacks revalidate the character's current location."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from utils.ttrpg import rpg_housing_handler as housing
from utils.ttrpg.farming import CROPS


def _message():
    sent = []

    async def send(*args, embed=None, view=None, **kwargs):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def _interaction(seed_key):
    return SimpleNamespace(
        user=SimpleNamespace(id=42),
        data={"values": [seed_key]},
        response=SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


def _prepare_seed_shop(monkeypatch, store, saves):
    async def load(uid):
        assert str(uid) == "42"
        return copy.deepcopy(store["42"])

    async def save(sheet):
        saves.append(copy.deepcopy(sheet))
        store[str(sheet["user_id"])] = copy.deepcopy(sheet)

    monkeypatch.setattr(housing, "load", load)
    monkeypatch.setattr(housing, "save", save)
    monkeypatch.setattr(
        housing, "_make_status_btn",
        lambda *args: discord.ui.Button(label="Status"),
    )
    monkeypatch.setattr(
        housing.turn_buttons, "buttons_for",
        AsyncMock(return_value=None),
    )


def test_stale_seed_shop_selector_refuses_purchase_after_leaving_hut(monkeypatch):
    store = {
        "42": {
            "user_id": "42",
            "location": "herbalists_hut",
            "gil": 100,
            "inventory": [],
        }
    }
    saves = []
    _prepare_seed_shop(monkeypatch, store, saves)
    msg, sent = _message()
    seed_key = next(iter(CROPS))

    async def run():
        await housing._handle_seed_shop(None, msg, None, "", "42", "Ash", False)
        view = sent[0][1]
        selector = next(child for child in view.children if isinstance(child, discord.ui.Select))
        store["42"]["location"] = "stone_hearth"
        interaction = _interaction(seed_key)
        await selector.callback(interaction)
        return interaction

    interaction = asyncio.run(run())

    assert store["42"]["location"] == "stone_hearth"
    assert store["42"]["gil"] == 100
    assert store["42"]["inventory"] == []
    assert saves == []
    interaction.response.defer.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert "Herbalist's Hut" in interaction.followup.send.await_args.kwargs["embed"].description


def test_seed_shop_still_purchases_at_the_herbalists_hut(monkeypatch):
    store = {
        "42": {
            "user_id": "42",
            "location": "herbalists_hut",
            "gil": 100,
            "inventory": [],
        }
    }
    saves = []
    _prepare_seed_shop(monkeypatch, store, saves)
    msg, sent = _message()
    seed_key = next(iter(CROPS))
    cost = CROPS[seed_key]["seed_cost"]

    async def run():
        await housing._handle_seed_shop(None, msg, None, "", "42", "Ash", False)
        view = sent[0][1]
        selector = next(child for child in view.children if isinstance(child, discord.ui.Select))
        interaction = _interaction(seed_key)
        await selector.callback(interaction)
        return interaction

    interaction = asyncio.run(run())

    assert store["42"]["location"] == "herbalists_hut"
    assert store["42"]["gil"] == 100 - cost
    assert seed_key in store["42"]["inventory"]
    assert len(saves) == 1
    interaction.followup.send.assert_awaited_once()
    assert "Purchased" in interaction.followup.send.await_args.kwargs["embed"].description
