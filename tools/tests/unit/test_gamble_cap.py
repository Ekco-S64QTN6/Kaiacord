"""A Trickster's two dice make the Stone Hearth table worth +1.6 gil a roll,
with no limit on rolls. What anyone can win there in a day is capped."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from utils.ttrpg import rpg_core_handler as core


def _play(sheet, rolls):
    msg = MagicMock()
    msg.channel.send = AsyncMock()
    async def go():
        with patch.object(core, "load", AsyncMock(return_value=sheet)), \
             patch.object(core, "save", AsyncMock()), \
             patch.object(core, "_make_status_btn", lambda *a: discord.ui.Button(label="s")), \
             patch.object(core.secrets, "randbelow", side_effect=rolls), \
             patch("utils.ttrpg.calendar.get_special_day", return_value=None):
            for _ in range(40):
                await core._handle_gamble(None, msg, None, "", "1", "u", False)
    asyncio.run(go())
    return msg


def test_a_lucky_trickster_is_sent_home_at_the_cap():
    sheet = {"location": "stone_hearth", "gil": 1000, "advanced_class": "Trickster"}
    # player dice 6,6 then house 1: every roll a win
    rolls = iter([5, 5, 0] * 100)
    msg = _play(sheet, lambda n: next(rolls))
    assert sheet["gil"] == 1000 + core.GAMBLE_DAILY_WIN_CAP
    assert "Come back tomorrow" in msg.channel.send.await_args.kwargs["embed"].description


def test_losses_count_against_the_day():
    sheet = {"location": "stone_hearth", "gil": 1000, "advanced_class": "", "gamble_net": 0}
    rolls = iter([0, 5] * 100)          # player 1, house 6: every roll a loss
    _play(sheet, lambda n: next(rolls))
    assert sheet["gamble_net"] == -400 and sheet["gil"] == 600
