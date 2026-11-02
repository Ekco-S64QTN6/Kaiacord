"""An expired button is one quiet line; any other failure keeps its traceback."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import discord
import pytest

from utils.commands.stale_view import StaleSafeView


def _not_found(code: int) -> discord.NotFound:
    response = SimpleNamespace(status=404, reason="Not Found")
    return discord.NotFound(response, {"code": code, "message": "Unknown interaction"})


@pytest.mark.parametrize("code", [10015, 10062])
def test_an_expired_interaction_is_not_an_error(code):
    async def run():
        view = StaleSafeView()
        with patch("utils.commands.stale_view.log_error") as err:
            await view.on_error(None, _not_found(code), None)
        err.assert_not_called()
    asyncio.run(run())


def test_any_other_failure_is_logged_with_its_traceback():
    async def run():
        view = StaleSafeView()
        with patch("utils.commands.stale_view.log_error") as err:
            await view.on_error(None, ValueError("boom"), None)
        err.assert_called_once()
        assert "boom" in err.call_args.args[0]
    asyncio.run(run())


def test_rpg_and_fishing_views_use_it():
    from utils.commands import fishing_handler
    from utils.ttrpg import rpg_views
    for cls in (rpg_views.RPGFullLocationView, rpg_views.RPGCombatView, rpg_views.DungeonView,
                fishing_handler.FishingMenuView, fishing_handler.BiteView, fishing_handler.FishingShopView):
        assert issubclass(cls, StaleSafeView), cls
