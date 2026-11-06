"""Level-five advancement keeps its core API and one-shot choice dependencies."""
import asyncio

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_advancement_handler as advancement


def test_core_advancement_adapter_forwards_original_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(advancement, "_handle_advance", replacement)
    args = (object(), object(), None, "", "42", "Ash", False)

    assert asyncio.run(core._handle_advance(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["save_character"] is core.save
    assert kwargs["advanced_options_fn"] is core.get_advanced_options
    assert kwargs["apply_advanced_class_fn"] is core.apply_advanced_class_to_sheet
    assert kwargs["get_title_fn"] is core.get_title
    assert kwargs["player_locked_decorator"] is core.player_locked
    assert kwargs["log_world_event_fn"] is core._log_world_event
    assert kwargs["broadcast_world_event_fn"] is core._broadcast_world_event
