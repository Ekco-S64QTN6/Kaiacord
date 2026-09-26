"""The shrine puzzle: study the flame and the altar and the seal is yours.
"look at the flame" showed the flame — "Acquired: Flame-mark" — and recorded
nothing, so only the bare word "flame" counted."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from utils.ttrpg import rpg_core_handler as core


def test_natural_phrasing_solves_the_shrine_puzzle():
    sheet = {"character_name": "Ekco", "location": "shrine", "inventory": []}
    msg = MagicMock()
    msg.channel.send = AsyncMock()
    async def go():
        with patch.object(core, "load", AsyncMock(return_value=sheet)), \
             patch.object(core, "save", AsyncMock()):
            for words in ("at the flame", "at the altar"):
                await core._handle_look(None, msg, None, words, "1", "Ekco", False)
    asyncio.run(go())
    assert {"look_flame", "look_altar"} <= set(sheet["secrets"])
    assert "symbol_of_the_silent_ones" in sheet["inventory"]
