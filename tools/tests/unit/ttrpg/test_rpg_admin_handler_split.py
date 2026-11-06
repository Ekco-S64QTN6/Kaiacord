"""Owner-only Aethelgard commands retain their core adapters and target locking."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_admin_handler as admin
from utils.ttrpg import rpg_core_handler as core


@pytest.mark.parametrize("name", ["_handle_give", "_handle_heal"])
def test_core_admin_adapters_forward_patchable_dependencies(monkeypatch, name):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(admin, name, replacement)
    args = (object(), object(), None, "", "u1", "Ash", True)

    assert asyncio.run(getattr(core, name)(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs == {
        "load_character": core.load,
        "save_character": core.save,
        "no_character_handler": core.no_character,
        "with_target_action_lock_fn": core._with_target_action_lock,
    }


def test_admin_give_refuses_non_owner_without_loading_or_sending(monkeypatch):
    load = AsyncMock()
    save = AsyncMock()
    monkeypatch.setattr(core, "load", load)
    monkeypatch.setattr(core, "save", save)
    send = AsyncMock()
    msg = SimpleNamespace(mentions=[], channel=SimpleNamespace(send=send))

    asyncio.run(core._handle_give(None, msg, None, "tonic", "u1", "Ash", False))

    load.assert_not_awaited()
    save.assert_not_awaited()
    send.assert_not_awaited()


def test_admin_give_reports_inventory_capacity_without_saving(monkeypatch):
    from utils.ttrpg import inventory_capacity, shop
    from utils.ttrpg.character_manager import INVENTORY_LIMIT

    sheet = {"user_id": "u2", "character_name": "Target", "inventory": []}
    monkeypatch.setattr(shop, "find_item", lambda _query: {"key": "extra_item"})
    monkeypatch.setattr(inventory_capacity, "grant_item", lambda *_args: False)
    monkeypatch.setattr(inventory_capacity, "unique_item_type_count", lambda _items: INVENTORY_LIMIT)
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    save = AsyncMock()
    monkeypatch.setattr(core, "save", save)

    sent = []

    async def channel_send(*, embed=None):
        sent.append(embed)

    msg = SimpleNamespace(
        mentions=[],
        channel=SimpleNamespace(send=channel_send),
    )
    asyncio.run(core._handle_give(None, msg, None, "extra item", "u1", "Admin", True))

    save.assert_not_awaited()
    assert len(sent) == 1
    assert "inventory full" in sent[0].description
    assert f"{INVENTORY_LIMIT}/{INVENTORY_LIMIT} unique item types" in sent[0].description


def test_two_opposite_admin_targets_do_not_deadlock(monkeypatch):
    """Both owners must acquire the same two per-user locks in the same order."""
    from utils.ttrpg import session_manager

    monkeypatch.setattr(session_manager, "_action_locks", {})
    monkeypatch.setattr(session_manager, "_chan_global_lock", asyncio.Lock())

    async def run():
        completed = []

        async def operation(label):
            await asyncio.sleep(0)
            completed.append(label)

        await asyncio.wait_for(asyncio.gather(
            core._with_target_action_lock(
                "owner-b", "owner-a", lambda: operation("owner-a -> owner-b")
            ),
            core._with_target_action_lock(
                "owner-a", "owner-b", lambda: operation("owner-b -> owner-a")
            ),
        ), timeout=0.5)
        assert sorted(completed) == ["owner-a -> owner-b", "owner-b -> owner-a"]

    assert core._handle_give._serialized is True
    assert core._handle_heal._serialized is True
    asyncio.run(run())
