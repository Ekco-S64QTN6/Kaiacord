"""Read-only RPG reference commands live outside the core handler."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_reference_handler as reference


@pytest.mark.parametrize(
    "name",
    ["_handle_roll", "_handle_bestiary", "_handle_xp", "_handle_rpg_help"],
)
def test_core_reference_adapters_forward_the_original_command_arguments(monkeypatch, name):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(reference, name, replacement)
    args = (object(), object(), AsyncMock(), "d20", "u1", "Ash", True)

    assert asyncio.run(getattr(core, name)(*args)) == "forwarded"
    assert calls == [(args, {})]


def test_leaderboard_adapter_forwards_core_data_and_view_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(reference, "_handle_leaderboard", replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)

    assert asyncio.run(core._handle_leaderboard(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["location_data"] is core.LOCATION_DATA
    assert kwargs["class_icons"] is core.CLASS_ICONS
    assert kwargs["location_icons"] is core.LOCATION_ICONS
    assert kwargs["get_title_fn"] is core.get_title
    assert kwargs["make_status_view"] is core._make_status_view


def test_roll_command_uses_the_dice_engine_and_sends_the_breakdown(monkeypatch):
    from utils.ttrpg import dice_engine

    monkeypatch.setattr(dice_engine, "roll", lambda expression: (12, "🎲 2d6 = 12"))
    sent = []

    async def send(**kwargs):
        sent.append(kwargs["embed"])

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(core._handle_roll(None, msg, None, "2d6", "u1", "Ash", False))

    assert sent[0].description == "🎲 **Ash** rolled `2d6`: 🎲 2d6 = 12"


def test_bestiary_remains_owner_only_and_uses_the_send_adapter(monkeypatch):
    from utils.ttrpg import monster_registry

    monkeypatch.setattr(monster_registry, "format_bestiary", lambda: "bestiary text")
    send = AsyncMock()
    msg = SimpleNamespace(channel=object())

    asyncio.run(core._handle_bestiary(None, msg, send, "", "u1", "Ash", False))
    send.assert_not_awaited()

    asyncio.run(core._handle_bestiary(None, msg, send, "", "u1", "Ash", True))
    send.assert_awaited_once_with(msg.channel, "bestiary text", use_code_block=False)


def test_xp_command_keeps_its_developer_only_guard():
    sent = []

    async def send(**kwargs):
        sent.append(kwargs["embed"])

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(core._handle_xp(None, msg, None, "", "u1", "Ash", False))
    assert sent == []

    asyncio.run(core._handle_xp(None, msg, None, "", "u1", "Ash", True))
    assert len(sent) == 1
    assert "Developer override required" in sent[0].description


def test_leaderboard_renders_ranked_records_and_incomplete_scan(monkeypatch):
    from utils.ttrpg import character_manager

    monkeypatch.setattr(
        character_manager,
        "load_all_report",
        AsyncMock(return_value=SimpleNamespace(
            records=[
                {
                    "character_name": "Ash",
                    "class": "Warrior",
                    "advanced_class": "",
                    "race": "Human",
                    "level": 4,
                    "xp": 900,
                    "deaths": 1,
                    "location": "oakhaven",
                },
                {
                    "character_name": "Mira",
                    "class": "Mage",
                    "advanced_class": "",
                    "race": "Elf",
                    "level": 2,
                    "xp": 300,
                    "deaths": 0,
                    "location": "shrine",
                },
            ],
            failures=[{"owner": "broken"}],
        )),
    )
    monkeypatch.setattr(core, "LOCATION_DATA", {
        "oakhaven": {"name": "Oakhaven"},
        "shrine": {"name": "Shrine"},
    })
    monkeypatch.setattr(core, "CLASS_ICONS", {"Warrior": "⚔️", "Mage": "🔮"})
    monkeypatch.setattr(core, "LOCATION_ICONS", {"oakhaven": "🏘️", "shrine": "⛩️"})
    monkeypatch.setattr(core, "get_title", lambda sheet: "Adventurer")
    monkeypatch.setattr(core, "_make_status_view", lambda *args: "status-view")

    sent = []

    async def send(**kwargs):
        sent.append((kwargs["embed"], kwargs.get("view")))

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(core._handle_leaderboard(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.title == "🏆  AETHELGARD LEADERBOARD"
    assert embed.description.index("Ash") < embed.description.index("Mira")
    assert "incomplete scan: 1 unreadable record" in embed.footer.text
    assert view == "status-view"


def test_rpg_help_guide_still_lists_core_command_groups():
    sent = []

    async def send(**kwargs):
        sent.append(kwargs["embed"])

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(core._handle_rpg_help(None, msg, None, "", "u1", "Ash", False))

    embed = sent[0]
    names = [field.name for field in embed.fields]
    assert "⚔️ World" in names
    assert "🏦 Oakhaven" in names
    assert "⛩️ Shrine" in names
    assert "!rpg bank` — balance; deposit/withdraw at the bank" in next(field.value for field in embed.fields if field.name == "🏦 Oakhaven")
