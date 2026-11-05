"""Inventory/equipment handlers retain their core entry points and lock rules."""
import asyncio
from types import SimpleNamespace

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_inventory_handler as inventory


@pytest.mark.parametrize(
    ("name", "expected_dependencies", "serialized"),
    [
        (
            "_handle_inventory",
            (
                "load_character",
                "no_character_handler",
                "make_status_view",
                "make_inventory_view",
                "get_class_abbr_string",
                "get_item_effect_string",
            ),
            False,
        ),
        (
            "_handle_equip",
            ("load_character", "save_character", "no_character_handler"),
            True,
        ),
        (
            "_handle_unequip",
            (
                "load_character",
                "save_character",
                "no_character_handler",
                "player_locked_decorator",
                "interaction_msg_factory",
                "interaction_send_factory",
                "status_btn_factory",
            ),
            False,
        ),
    ],
)
def test_core_inventory_adapters_forward_patchable_dependencies(
    monkeypatch, name, expected_dependencies, serialized
):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(inventory, name, replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)
    wrapper = getattr(core, name)
    call = wrapper.__wrapped__ if serialized else wrapper

    assert asyncio.run(call(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    for dependency in expected_dependencies:
        assert dependency in kwargs
    assert kwargs["load_character"] is core.load
    assert kwargs["no_character_handler"] is core.no_character
    if "save_character" in expected_dependencies:
        assert kwargs["save_character"] is core.save


def test_equipping_keeps_its_serialized_core_entry_point():
    assert getattr(core._handle_equip, "_serialized", False) is True


def test_inventory_adapter_renders_the_empty_backpack(monkeypatch):
    sheet = {
        "user_id": "u1",
        "character_name": "Ash",
        "inventory": [],
        "equipment": {},
    }
    monkeypatch.setattr(core, "load", lambda uid: _loaded(sheet, uid))
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")

    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(core._handle_inventory(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.title == "🎒 Inventory"
    assert "Backpack is empty" in embed.description
    assert view == "status-view"


async def _loaded(sheet, uid):
    assert uid == "u1"
    return sheet
