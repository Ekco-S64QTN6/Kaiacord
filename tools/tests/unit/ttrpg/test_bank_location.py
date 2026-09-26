"""Banking happens at the Oakhaven Bank, or at home with the Ironbound Vault
Chest. It worked everywhere, which left the chest with nothing to add."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.ttrpg import rpg_core_handler as core


def _run(location, housing=None, handler=core._handle_bank_deposit):
    sheet = {"location": location, "gil": 100, "bank_balance": 50}
    msg = MagicMock()
    msg.channel.send = AsyncMock()
    async def go():
        with patch.object(core, "load", AsyncMock(return_value=sheet)), \
             patch("utils.ttrpg.housing.load_housing_async", AsyncMock(return_value=housing)), \
             patch.object(core, "_make_status_btn", lambda *a: __import__("discord").ui.Button(label="s")):
            await handler(None, msg, None, "", "1", "u", False)
    asyncio.run(go())
    kw = msg.channel.send.await_args.kwargs
    return kw["embed"].description, kw.get("view")


@pytest.mark.parametrize("handler", [core._handle_bank_deposit, core._handle_bank_withdraw])
def test_away_from_the_bank_you_are_sent_there(handler):
    text, view = _run("whisperwood_deep", handler=handler)
    assert "Oakhaven Bank" in text and view is None


def test_at_the_bank_it_opens():
    text, view = _run("oakhaven_bank")
    assert view is not None


def test_at_home_the_vault_chest_opens_it():
    assert _run("housing_district", {"furniture": ["vault_chest"]})[1] is not None
    assert _run("housing_district", {"furniture": ["straw_bed"]})[1] is None
