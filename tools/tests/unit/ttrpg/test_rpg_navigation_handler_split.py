"""Navigation handlers can move without changing the command/view surface."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_navigation_handler as navigation


@pytest.mark.parametrize(
    ("name", "needs_save"),
    [("_handle_go", True), ("_handle_look", True), ("_handle_map", False)],
)
def test_core_navigation_adapters_forward_the_core_load_save_functions(
    monkeypatch, name, needs_save
):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(navigation, name, replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)
    wrapper = getattr(core, name)
    # Go remains user-serialized at the stable core entry point. Its inner
    # adapter is exercised here so this test isolates dependency forwarding.
    call = wrapper.__wrapped__ if name == "_handle_go" else wrapper
    result = asyncio.run(call(*args))

    assert result == "forwarded"
    called_args, called_kwargs = calls[0]
    assert called_args == args
    assert called_kwargs["load_character"] is core.load
    if needs_save:
        assert called_kwargs["save_character"] is core.save
    else:
        assert "save_character" not in called_kwargs


def test_go_entry_point_keeps_its_user_action_lock():
    assert getattr(core._handle_go, "_serialized", False) is True


def test_map_handler_renders_the_current_locations_exits(monkeypatch):
    from utils.ttrpg import world

    monkeypatch.setattr(world, "LOCATION_DATA", {
        "oakhaven": {"name": "Oakhaven", "exits": ["whisperwood_edge"]},
        "whisperwood_edge": {
            "name": "Whisperwood Edge",
            "hunting": True,
            "recommended_level": 3,
            "exits": ["oakhaven"],
        },
    })
    monkeypatch.setattr(
        navigation,
        "RPGFullLocationView",
        lambda *args: "location-view",
    )

    async def load_character(uid):
        assert uid == "u1"
        return {"location": "oakhaven"}

    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(
        navigation._handle_map(
            None, msg, None, "", "u1", "Ash", False,
            load_character=load_character,
        )
    )

    (embed, view), = sent
    assert embed.title == "🗺️ From Oakhaven"
    assert "Whisperwood Edge" in embed.description
    assert "⚔️" in embed.description
    assert "Lv.3+" in embed.description
    assert view == "location-view"


def test_navigation_name_matcher_uses_whole_word_phrase_boundaries():
    assert navigation._names("offering bowl", "the offering bowl")
    assert not navigation._names("offering bowl", "the offerings bowl")
    assert not navigation._names("flame", "flamethrower")


def test_public_look_handler_resolves_a_partial_multiword_target(monkeypatch):
    from utils.ttrpg import look_targets

    sheet = {
        "user_id": "42",
        "character_name": "Ash",
        "location": "oakhaven",
        "inventory": [],
    }
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    save = AsyncMock()
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(
        look_targets,
        "LOCATION_LOOK_TARGETS",
        {"oakhaven": {"offering bowl": "A silver bowl rests beside the hearth."}},
    )

    sent = []

    async def send(*, embed=None, view=None):
        sent.append(embed)

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(
        core._handle_look(
            object(), msg, None, "at offering", "42", "Ash", False
        )
    )

    assert len(sent) == 1
    assert sent[0].description == "A silver bowl rests beside the hearth."
    save.assert_not_awaited()
