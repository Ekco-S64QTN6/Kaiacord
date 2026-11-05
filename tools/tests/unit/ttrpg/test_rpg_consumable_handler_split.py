"""Combat consumable use lives in a focused module behind the serialized core API."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_consumable_handler as consumable


def test_core_use_adapter_forwards_all_patchable_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(consumable, "_handle_use", replacement)
    args = (object(), object(), None, "potion_standard", "u1", "Ash", False)

    assert asyncio.run(core._handle_use.__wrapped__(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["save_character"] is core.save
    assert kwargs["no_character_handler"] is core.no_character
    assert kwargs["load_session_fn"] is core.load_session
    assert kwargs["active_view_factory"] is core._get_active_view
    assert kwargs["status_view_factory"] is core._make_status_view
    assert kwargs["hunt_status_view_factory"] is core._make_hunt_status_view
    assert kwargs["secrets_module"] is core.secrets
    assert kwargs["uuid_module"] is core._uuid


def test_core_use_entry_point_keeps_the_combat_action_lock():
    assert getattr(core._handle_use, "_serialized", False) is True


def test_unavailable_character_keeps_the_original_no_character_response(monkeypatch):
    monkeypatch.setattr(core, "load", AsyncMock(return_value=None))
    no_character = AsyncMock()
    monkeypatch.setattr(core, "no_character", no_character)

    class DummyChannel:
        id = 1

    class DummyMessage:
        channel = DummyChannel()

    asyncio.run(
        core._handle_use.__wrapped__(
            None, DummyMessage(), None, "potion_standard", "u1", "Ash", False
        )
    )
    no_character.assert_awaited_once()
