"""Detailed character sheets live in a focused renderer behind the core API."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_sheet_handler as sheet


def test_core_sheet_adapter_forwards_patchable_load_and_view_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(sheet, "_handle_sheet", replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)

    assert asyncio.run(core._handle_sheet(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["location_icons"] is core.LOCATION_ICONS
    assert kwargs["location_view_factory"] is core.RPGLocationView
    assert kwargs["stale_view_factory"] is core.StaleSafeView
    assert kwargs["status_btn_factory"] is core._make_status_btn
    assert kwargs["hunts_remaining_fn"] is core.hunts_remaining
    assert kwargs["max_hunts_fn"] is core.get_max_hunts
    assert kwargs["xp_to_next_level_fn"] is core.xp_to_next_level


def test_sheet_adapter_keeps_character_not_found_response(monkeypatch):
    monkeypatch.setattr(core, "load", AsyncMock(return_value=None))
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(
        mentions=[],
        channel=SimpleNamespace(send=send),
    )

    asyncio.run(core._handle_sheet(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.description == "Character not found."
    assert view is None
