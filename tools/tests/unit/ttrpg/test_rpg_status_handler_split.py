"""The Aethelgard HUD retains its core entry point and level-up callback dependencies."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_status_handler as status


def test_core_status_adapter_forwards_all_patchable_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(status, "_handle_status", replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)

    assert asyncio.run(core._handle_status(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    expected = {
        "load_character": core.load,
        "save_character": core.save,
        "show_stat_choice_handler": core._show_stat_choice,
        "load_session_fn": core.load_session,
        "load_dungeon_fn": core.load_dungeon,
        "get_current_state_fn": core.get_current_state,
        "xp_to_next_level_fn": core.xp_to_next_level,
        "xp_thresholds": core.XP_THRESHOLDS,
        "colored_bar_fn": core.colored_bar,
        "ansi_green": core.ANSI_GREEN,
        "ansi_reset": core.ANSI_RESET,
        "hp_label_fn": core.hp_label,
        "hunts_remaining_fn": core.hunts_remaining,
        "get_max_hunts_fn": core.get_max_hunts,
        "get_title_fn": core.get_title,
        "class_icons": core.CLASS_ICONS,
        "location_icons": core.LOCATION_ICONS,
        "player_locked_decorator": core.player_locked,
        "location_view_factory": core.RPGLocationView,
        "stale_view_factory": core.StaleSafeView,
    }
    assert kwargs == expected


def test_status_keeps_the_no_character_message(monkeypatch):
    monkeypatch.setattr(core, "load", AsyncMock(return_value=None))
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(channel=SimpleNamespace(send=send))
    asyncio.run(core._handle_status(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert "You do not exist in Aethelgard" in embed.description
    assert view is None


def test_status_routes_pending_stat_choice_to_existing_helper(monkeypatch):
    monkeypatch.setattr(
        core, "load",
        AsyncMock(return_value={"_stat_choice_pending": True}),
    )
    show = AsyncMock()
    monkeypatch.setattr(core, "_show_stat_choice", show)
    msg = SimpleNamespace(channel=SimpleNamespace(send=AsyncMock()))

    asyncio.run(core._handle_status(None, msg, None, "", "u1", "Ash", False))

    show.assert_awaited_once_with(
        None, msg, None, {"_stat_choice_pending": True}, "u1", "Ash", False
    )
    msg.channel.send.assert_not_awaited()


def test_status_renders_the_hud_with_current_combat_and_progression_data(monkeypatch):
    from utils.ttrpg import calendar

    sheet = {
        "user_id": "u1",
        "character_name": "Ash",
        "class": "Warrior",
        "level": 1,
        "xp": 50,
        "gil": 12,
        "hp": {"current": 8, "max": 10},
        "location": "oakhaven",
        "equipment": {},
        "conditions": [],
    }
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "load_session", AsyncMock(return_value=None))
    monkeypatch.setattr(core, "load_dungeon", AsyncMock(return_value=None))
    monkeypatch.setattr(core, "get_current_state", lambda: {"event": "none"})
    monkeypatch.setattr(core, "xp_to_next_level", lambda level: 100)
    monkeypatch.setattr(core, "XP_THRESHOLDS", {1: 0})
    monkeypatch.setattr(core, "colored_bar", lambda value, maximum, width: "BAR")
    monkeypatch.setattr(core, "hp_label", lambda current, maximum: f"{current}/{maximum}")
    monkeypatch.setattr(core, "hunts_remaining", lambda _sheet: 4)
    monkeypatch.setattr(core, "get_max_hunts", lambda _sheet: 5)
    monkeypatch.setattr(core, "get_title", lambda _sheet: "Adventurer")
    monkeypatch.setattr(core, "CLASS_ICONS", {"Warrior": "⚔️"})
    monkeypatch.setattr(core, "LOCATION_ICONS", {"oakhaven": "🏘️"})
    monkeypatch.setattr(core, "RPGLocationView", lambda *args: "location-view")
    monkeypatch.setattr(
        calendar, "get_weather",
        lambda: {"emoji": "☀️", "name": "Clear", "desc": "Clear skies."},
    )

    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(
        channel=SimpleNamespace(id=123, send=send),
    )
    asyncio.run(core._handle_status(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.title.startswith("⚔️  ASH")
    assert "Clear skies" in embed.description
    assert "8/10" in embed.fields[0].value
    assert "4/5 hunts" in embed.fields[4].value
    assert view == "location-view"



def test_stat_choice_rejects_a_different_user_without_loading(monkeypatch):
    from utils.ttrpg import rpg_views

    load = AsyncMock()
    save = AsyncMock()
    monkeypatch.setattr(rpg_views, "load", load)
    monkeypatch.setattr(rpg_views, "save", save)

    view = rpg_views.StatChoiceView(None, "42", "Ash", False, "str")
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=99),
        response=SimpleNamespace(
            send_message=AsyncMock(),
            edit_message=AsyncMock(),
        ),
    )

    asyncio.run(view._process_choice(interaction, {"str": 2}))

    load.assert_not_awaited()
    save.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "This is not your choice to make.", ephemeral=True
    )


def test_stat_choice_duplicate_click_saves_exactly_once(monkeypatch):
    from utils.ttrpg import rpg_views, session_manager

    monkeypatch.setattr(session_manager, "_action_locks", {})
    monkeypatch.setattr(session_manager, "_chan_global_lock", asyncio.Lock())
    sheet = {
        "user_id": "42",
        "level": 2,
        "_stat_choice_pending": True,
        "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        "hp": {"current": 12, "max": 12},
    }
    load = AsyncMock(return_value=sheet)
    saved = []

    async def save(value):
        saved.append({
            "stats": dict(value["stats"]),
            "pending": value.get("_stat_choice_pending", False),
        })

    monkeypatch.setattr(rpg_views, "load", load)
    monkeypatch.setattr(rpg_views, "save", save)

    view = rpg_views.StatChoiceView(None, "42", "Ash", False, "str")

    def interaction():
        return SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(
                send_message=AsyncMock(),
                edit_message=AsyncMock(),
            ),
        )

    first, second = interaction(), interaction()

    async def run():
        await asyncio.gather(
            view._process_choice(first, {"str": 2}),
            view._process_choice(second, {"str": 2}),
        )

    asyncio.run(run())

    assert load.await_count == 2
    assert len(saved) == 1
    assert saved[0]["stats"]["str"] == 12
    assert saved[0]["pending"] is False
    assert (
        first.response.edit_message.await_count
        + second.response.edit_message.await_count
    ) == 1
    assert (
        first.response.send_message.await_count
        + second.response.send_message.await_count
    ) == 1
    rejected = (
        first if first.response.send_message.await_count
        else second
    )
    rejected.response.send_message.assert_awaited_once_with(
        "No stat choice is currently pending for your character.", ephemeral=True
    )


def test_stat_choice_with_stale_pending_state_does_not_save(monkeypatch):
    from utils.ttrpg import rpg_views, session_manager

    monkeypatch.setattr(session_manager, "_action_locks", {})
    monkeypatch.setattr(session_manager, "_chan_global_lock", asyncio.Lock())
    load = AsyncMock(return_value={"_stat_choice_pending": False})
    save = AsyncMock()
    monkeypatch.setattr(rpg_views, "load", load)
    monkeypatch.setattr(rpg_views, "save", save)

    view = rpg_views.StatChoiceView(None, "42", "Ash", False, "str")
    interaction = SimpleNamespace(
        user=SimpleNamespace(id=42),
        response=SimpleNamespace(
            send_message=AsyncMock(),
            edit_message=AsyncMock(),
        ),
    )

    asyncio.run(view._process_choice(interaction, {"str": 2}))

    load.assert_awaited_once_with("42")
    save.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once_with(
        "No stat choice is currently pending for your character.", ephemeral=True
    )
    interaction.response.edit_message.assert_not_awaited()
