"""!nightshift is a control panel: every button runs the handler its typed
command does, with the same text."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from utils.commands import nightshift, registry  # noqa: F401  (registry imports every handler)


def test_every_button_reaches_its_handler():
    handlers = nightshift._handlers()
    calls = []

    async def run():
        fakes = {k: AsyncMock(side_effect=lambda ctx, msg, _k=k: calls.append((_k, msg.content)))
                 for k in handlers}
        with patch.object(nightshift, "_handlers", return_value=fakes):
            view = nightshift.panel_view(None)
            for button in view.children:
                inter = NS(user=NS(), guild=NS(id=1), channel=NS(),
                           response=NS(defer=AsyncMock()), followup=NS(send=AsyncMock()))
                await button.callback(inter)
        return view
    view = asyncio.run(run())
    assert len(view.children) == len(nightshift.BUTTONS)
    assert ("buzzer", "!buzzer") in calls and ("radio", "!radio hfgcs") in calls
    assert ("scanner", "!scanner") in calls and ("radio", "!radio off") in calls


def test_the_old_index_is_still_one_word_away():
    msg = NS(content="!nightshift list", channel=NS(send=AsyncMock()))
    asyncio.run(nightshift.handle_nightshift_command(None, msg))
    assert "view" not in msg.channel.send.await_args.kwargs
