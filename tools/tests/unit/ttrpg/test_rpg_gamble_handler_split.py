"""Stone Hearth gambling keeps the existing callback lock and core dependencies."""
import asyncio

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_gamble_handler as gamble


def test_core_gamble_adapter_forwards_patchable_persistence_and_callback_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(gamble, "_handle_gamble", replacement)
    args = (object(), object(), None, "", "42", "Ash", False)

    assert asyncio.run(core._handle_gamble(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["save_character"] is core.save
    assert kwargs["secrets_module"] is core.secrets
    assert kwargs["daily_win_cap"] == core.GAMBLE_DAILY_WIN_CAP
    assert kwargs["player_locked_decorator"] is core.player_locked
    assert kwargs["interaction_msg_factory"] is core._InteractionMsg
    assert kwargs["interaction_send_factory"] is core._make_interaction_send
    assert kwargs["status_btn_factory"] is core._make_status_btn
