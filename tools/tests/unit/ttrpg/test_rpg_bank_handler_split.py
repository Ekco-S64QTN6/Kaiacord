"""Bank commands remain thin core adapters with per-player transaction locks."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_bank_handler as bank


@pytest.mark.parametrize(
    ("name", "dependencies"),
    [
        ("_handle_bank_deposit", (
            "load_character", "save_character", "no_character_handler",
            "player_locked_decorator", "status_btn_factory",
        )),
        ("_handle_bank_withdraw", (
            "load_character", "save_character", "no_character_handler",
            "player_locked_decorator", "status_btn_factory",
        )),
        ("_handle_bank", ("load_character", "no_character_handler")),
    ],
)
def test_core_bank_adapters_forward_patchable_dependencies(monkeypatch, name, dependencies):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(bank, name, replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)

    assert asyncio.run(getattr(core, name)(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["no_character_handler"] is core.no_character
    if "save_character" in dependencies:
        assert kwargs["save_character"] is core.save
    if "player_locked_decorator" in dependencies:
        assert kwargs["player_locked_decorator"] is core.player_locked
    if "status_btn_factory" in dependencies:
        assert kwargs["status_btn_factory"] is core._make_status_btn
    assert all(dep in kwargs for dep in dependencies)


def _message():
    sent = []

    async def send(*args, embed=None, view=None, **kwargs):
        sent.append((embed, view))

    return SimpleNamespace(channel=SimpleNamespace(send=send)), sent


def _interaction():
    response = SimpleNamespace(send_message=AsyncMock())
    return SimpleNamespace(user=SimpleNamespace(id=42), response=response)


@pytest.mark.parametrize(
    ("handler_name", "button_prefix", "expected_gil", "expected_bank"),
    [
        ("_handle_bank_deposit", "Deposit 25g", 75, 75),
        ("_handle_bank_withdraw", "Withdraw 25g", 125, 25),
    ],
)
def test_bank_transaction_buttons_update_the_latest_saved_balance(
    monkeypatch, handler_name, button_prefix, expected_gil, expected_bank
):
    store = {
        "42": {
            "user_id": "42",
            "location": "oakhaven_bank",
            "gil": 100,
            "bank_balance": 50,
        }
    }
    loads = []

    async def load(uid):
        loads.append(uid)
        return dict(store[str(uid)])

    async def save(sheet):
        store[str(sheet["user_id"])] = dict(sheet)

    monkeypatch.setattr(core, "load", load)
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_btn", lambda *args: __import__("discord").ui.Button(label="status"))

    msg, sent = _message()

    async def run():
        await getattr(core, handler_name)(None, msg, None, "", "42", "Ash", False)
        _embed, view = sent[0]
        button = next(child for child in view.children if child.label == button_prefix)
        await button.callback(_interaction())

    asyncio.run(run())

    assert store["42"]["gil"] == expected_gil
    assert store["42"]["bank_balance"] == expected_bank
    assert loads == ["42", "42"]


def test_bank_transaction_callbacks_hold_the_player_lock(monkeypatch):
    from utils.ttrpg.session_manager import get_action_lock

    store = {
        "42": {
            "user_id": "42",
            "location": "oakhaven_bank",
            "gil": 100,
            "bank_balance": 50,
        }
    }

    async def load(uid):
        return dict(store[str(uid)])

    async def save(sheet):
        store[str(sheet["user_id"])] = dict(sheet)

    monkeypatch.setattr(core, "load", load)
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "_make_status_btn", lambda *args: __import__("discord").ui.Button(label="status"))

    lock_observations = []

    def observing_player_locked(uid):
        from utils.ttrpg.session_manager import get_action_lock

        def decorate(fn):
            async def wrapped(*args, **kwargs):
                lock = await get_action_lock(f"user:{uid}")
                async with lock:
                    lock_observations.append(lock.locked())
                    return await fn(*args, **kwargs)
            return wrapped
        return decorate

    monkeypatch.setattr(core, "player_locked", observing_player_locked)
    msg, sent = _message()

    async def run():
        await core._handle_bank_deposit(None, msg, None, "", "42", "Ash", False)
        view = sent[0][1]
        button = next(child for child in view.children if child.label == "Deposit 10g")
        await button.callback(_interaction())

    asyncio.run(run())
    assert lock_observations == [True]
    assert store["42"]["gil"] == 90
    assert store["42"]["bank_balance"] == 60
