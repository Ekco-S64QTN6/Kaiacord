"""Regression tests for every supported consumable use effect and retired items."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _prepare_use(monkeypatch, sheet, *, session=None):
    from utils.ttrpg import rpg_core_handler as core
    from utils.ttrpg import session_manager, outing, dungeon

    save = AsyncMock()
    save_session = AsyncMock()
    note = AsyncMock()
    send = AsyncMock()
    status_view = object()
    hunt_view = object()
    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(core, "save", save)
    monkeypatch.setattr(core, "load_session", AsyncMock(return_value=session))
    monkeypatch.setattr(dungeon, "load_dungeon", AsyncMock(return_value=None))
    monkeypatch.setattr(session_manager, "save_session", save_session)
    monkeypatch.setattr(outing, "note", note)
    monkeypatch.setattr(core, "_get_active_view", AsyncMock(return_value=None))
    monkeypatch.setattr(core, "_make_status_view", lambda *args: status_view)
    monkeypatch.setattr(core, "_make_hunt_status_view", lambda *args: hunt_view)
    channel = SimpleNamespace(id=987, send=send)
    msg = SimpleNamespace(channel=channel)

    async def run(item_key):
        await core._handle_use.__wrapped__(
            None, msg, None, item_key, "42", "Tester", False
        )

    return core, msg, save, save_session, note, status_view, hunt_view, run


def _sheet(item_key, *, conditions=None):
    return {
        "user_id": "42",
        "character_name": "Tester",
        "class": "Warrior",
        "level": 5,
        "location": "trade_road",
        "hp": {"current": 20, "max": 30},
        "xp": 1000,
        "gil": 500,
        "hunts_today": 2,
        "inventory": [item_key],
        "conditions": list(conditions or []),
    }


def test_use_healing_consumable_restores_hp_and_consumes_one(monkeypatch):
    sheet = _sheet("potion_standard")
    core, msg, save, _, note, status_view, _, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run("potion_standard"))

    assert sheet["hp"]["current"] == 30
    assert sheet["inventory"] == []
    save.assert_awaited_once_with(sheet)
    note.assert_awaited_once_with("42", "used", "Health Potion")
    assert msg.channel.send.await_args.kwargs["view"] is status_view
    assert "Restored 10 HP" in msg.channel.send.await_args.kwargs["embed"].description


def test_use_starter_kit_opens_its_contents(monkeypatch):
    sheet = _sheet("adventurers_pack")
    _, msg, save, _, note, _, _, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run("adventurers_pack"))

    assert sheet["inventory"] == ["bandage", "healing_herb", "torch"]
    save.assert_awaited_once_with(sheet)
    note.assert_awaited_once_with("42", "used", "Adventurer's Pack")
    assert "Bandage" in msg.channel.send.await_args.kwargs["embed"].description


def test_antidote_cures_poison_and_is_not_spent_when_unneeded(monkeypatch):
    poisoned = _sheet("antidote", conditions=["poisoned"])
    _, _, save, _, note, _, _, run = _prepare_use(monkeypatch, poisoned)
    asyncio.run(run("antidote"))
    assert "poisoned" not in poisoned["conditions"]
    assert poisoned["inventory"] == []
    save.assert_awaited_once_with(poisoned)
    note.assert_awaited_once_with("42", "used", "Antidote")

    clean = _sheet("antidote")
    _, msg, clean_save, _, clean_note, _, _, clean_run = _prepare_use(monkeypatch, clean)
    asyncio.run(clean_run("antidote"))
    assert clean["inventory"] == ["antidote"]
    clean_save.assert_not_awaited()
    clean_note.assert_not_awaited()
    assert "aren't poisoned" in msg.channel.send.await_args.kwargs["embed"].description


def test_lucky_charm_applies_next_hit_condition(monkeypatch):
    sheet = _sheet("lucky_charm")
    _, msg, save, _, note, _, status_view, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run("lucky_charm"))

    assert "lucky" in sheet["conditions"]
    assert sheet["inventory"] == []
    save.assert_awaited_once_with(sheet)
    note.assert_awaited_once_with("42", "used", "Lucky Charm")
    assert msg.channel.send.await_args.kwargs["view"] is status_view
    assert "+1 to next hit roll" in msg.channel.send.await_args.kwargs["embed"].description


def test_experience_tonic_applies_next_hunt_condition(monkeypatch):
    sheet = _sheet("xp_tonic")
    _, msg, save, _, note, _, status_view, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run("xp_tonic"))

    assert "xp_boosted" in sheet["conditions"]
    assert sheet["inventory"] == []
    save.assert_awaited_once_with(sheet)
    note.assert_awaited_once_with("42", "used", "Experience Tonic")
    assert msg.channel.send.await_args.kwargs["view"] is status_view
    assert "+25% XP on next hunt" in msg.channel.send.await_args.kwargs["embed"].description


def test_hunters_draught_grants_bonus_hunt_condition(monkeypatch):
    from utils.ttrpg import progression

    sheet = _sheet("hunters_draught")
    monkeypatch.setattr(progression, "hunts_remaining", lambda current: 4)
    monkeypatch.setattr(progression, "get_max_hunts", lambda current: 5)
    _, msg, save, _, note, _, status_view, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run("hunters_draught"))

    assert "hunt_bonus" in sheet["conditions"]
    assert sheet["inventory"] == []
    assert sheet["hunts_today"] == 2
    save.assert_awaited_once_with(sheet)
    note.assert_awaited_once_with("42", "used", "Hunter's Draught")
    assert msg.channel.send.await_args.kwargs["view"] is status_view
    assert "+1 bonus hunt today" in msg.channel.send.await_args.kwargs["embed"].description


@pytest.mark.parametrize(
    ("item_key", "condition", "effect_text"),
    [
        ("firebrew", "embered", "+2 ATK until next combat"),
        ("frenzy_draught", "embered", "+2 ATK until next combat"),
        ("ironbark_tonic", "fortified", "+2 DEF until next combat"),
        ("warding_salve", "fortified", "+2 DEF until next combat"),
    ],
)
def test_attack_and_defense_consumables_match_their_registered_effect(
    monkeypatch, item_key, condition, effect_text
):
    sheet = _sheet(item_key)
    _, msg, save, _, note, _, status_view, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run(item_key))

    assert condition in sheet["conditions"]
    assert sheet["inventory"] == []
    save.assert_awaited_once_with(sheet)
    note.assert_awaited_once()
    assert msg.channel.send.await_args.kwargs["view"] is status_view
    assert effect_text in msg.channel.send.await_args.kwargs["embed"].description


def test_smoke_bomb_escapes_only_the_owners_current_overworld_swarm(monkeypatch):
    from utils.ttrpg import outing

    sheet = _sheet("smoke_bomb", conditions=["embered", "fortified"])
    session = {
        "combat_active": True,
        "monsters": [
            {"id": "mine-1", "name": "Goblin", "aggro_uid": "42", "origin_location": "trade_road"},
            {"id": "mine-2", "name": "Dire Wolf", "aggro_uid": "42", "origin_location": "trade_road"},
            {"id": "other", "name": "Other Hunter's Goblin", "aggro_uid": "99", "origin_location": "trade_road"},
            {"id": "stale", "name": "Old Wolf", "aggro_uid": "42", "origin_location": "whisperwood_edge"},
        ],
    }
    _, msg, save, save_session, note, _, hunt_view, run = _prepare_use(
        monkeypatch, sheet, session=session
    )

    asyncio.run(run("smoke_bomb"))

    assert [m["id"] for m in session["monsters"]] == ["other", "stale"]
    assert session["combat_active"] is True
    assert sheet["inventory"] == []
    assert "embered" not in sheet["conditions"]
    assert "fortified" not in sheet["conditions"]
    assert sheet["hunts_today"] == 2
    assert sheet["xp"] == 1000
    assert sheet["gil"] == 500
    save_session.assert_awaited_once_with(session)
    save.assert_awaited_once_with(sheet)
    assert note.await_count == 2
    assert note.await_args_list[0].args == ("42", "fled", "smoke bomb: Goblin, Dire Wolf")
    assert note.await_args_list[1].args == ("42", "used", "Smoke Bomb")
    assert msg.channel.send.await_args.kwargs["view"] is hunt_view
    embed = msg.channel.send.await_args.kwargs["embed"]
    assert "Goblin, Dire Wolf" in embed.description
    assert "No hunt stamina" in embed.description


def test_smoke_bomb_is_not_consumed_without_an_owned_current_location_fight(monkeypatch):
    sheet = _sheet("smoke_bomb")
    session = {
        "combat_active": True,
        "monsters": [
            {"id": "other", "name": "Goblin", "aggro_uid": "99", "origin_location": "trade_road"},
        ],
    }
    _, msg, save, save_session, note, _, _, run = _prepare_use(monkeypatch, sheet, session=session)

    asyncio.run(run("smoke_bomb"))

    assert sheet["inventory"] == ["smoke_bomb"]
    save.assert_not_awaited()
    save_session.assert_not_awaited()
    note.assert_not_awaited()
    assert "Nothing was consumed" in msg.channel.send.await_args.kwargs["embed"].description


@pytest.mark.parametrize("item_key", ["eye_drops", "trap_kit"])
def test_smoke_bomb_is_not_an_alternative_dungeon_flee(monkeypatch):
    from utils.ttrpg import dungeon

    sheet = _sheet("smoke_bomb")
    session = {
        "combat_active": True,
        "monsters": [
            {"id": "mine", "name": "Goblin", "aggro_uid": "42", "origin_location": "trade_road"},
        ],
    }
    core, msg, save, save_session, note, _, _, run = _prepare_use(
        monkeypatch, sheet, session=session
    )
    monkeypatch.setattr(dungeon, "load_dungeon", AsyncMock(return_value={"active": True}))

    asyncio.run(run("smoke_bomb"))

    assert sheet["inventory"] == ["smoke_bomb"]
    assert session["monsters"][0]["id"] == "mine"
    save.assert_not_awaited()
    save_session.assert_not_awaited()
    note.assert_not_awaited()
    core.load_session.assert_not_awaited()
    assert "Use the dungeon Flee action" in msg.channel.send.await_args.kwargs["embed"].description


def test_retired_consumables_cannot_be_used_or_consumed(monkeypatch, item_key):
    sheet = _sheet(item_key)
    _, msg, save, _, note, _, _, run = _prepare_use(monkeypatch, sheet)

    asyncio.run(run(item_key))

    assert sheet["inventory"] == [item_key]
    save.assert_not_awaited()
    note.assert_not_awaited()
    assert "retired" in msg.channel.send.await_args.kwargs["embed"].description


def test_registry_routes_every_live_on_use_value_to_a_handler():
    from utils.ttrpg.equipment_registry import CONSUMABLES

    handled = {
        "starter_kit",
        "cure_poison",
        "luck_roll_bonus",
        "xp_boost",
        "hunt_bonus",
        "atk_boost",
        "def_boost",
        "smoke_bomb",
    }
    for item_key, item in CONSUMABLES.items():
        if item.get("deprecated"):
            assert "on_use" not in item, f"retired {item_key} still advertises an effect"
            continue
        if item.get("on_use"):
            assert item["on_use"] in handled, (
                f"{item_key} advertises unhandled on_use={item['on_use']!r}"
            )


def test_retired_items_are_not_craftable_or_purchasable(monkeypatch):
    from utils.ttrpg import alchemy, shop

    assert alchemy.get_recipe("trap_kit") is None
    assert all("trap_kit" not in keys for keys in alchemy.SECONDARY_DISCOVERS.values())

    for item_key in ("eye_drops", "trap_kit"):
        monkeypatch.setattr(shop, "_in_stock", lambda loc, key: True)
        before = _sheet(item_key)
        ok, message, after = shop.process_purchase(before, item_key)
        assert ok is False
        assert "retired" in message
        assert after["gil"] == 500
        assert after["inventory"] == [item_key]


def test_shop_hides_retired_consumables_but_keeps_smoke_bomb(monkeypatch):
    from utils.ttrpg import calendar, equipment_registry, shop, world_state

    monkeypatch.setattr(equipment_registry, "HEMLOCK_STOCK_CONSUMABLES",
                        ["smoke_bomb", "eye_drops", "trap_kit"])
    monkeypatch.setattr(calendar, "get_season", lambda: "test")
    monkeypatch.setattr(calendar, "SEASONAL_SHOP", {})
    monkeypatch.setattr(calendar, "get_special_day", lambda: None)
    monkeypatch.setattr(world_state, "load_world_state", lambda: {})

    consumables = shop.get_shop_inventory("hemlocks_store")[-1]
    assert "smoke_bomb" in consumables
    assert "eye_drops" not in consumables
    assert "trap_kit" not in consumables


def test_item_menu_helpers_advertise_smoke_bomb_only_for_overworld_combat():
    from utils.ttrpg.equipment_registry import CONSUMABLES
    from utils.ttrpg.rpg_views import (
        _get_item_effect_string,
        _is_combat_usable_item,
        _is_dungeon_combat_usable_item,
    )

    smoke = {"category": "consumable", **CONSUMABLES["smoke_bomb"]}
    assert _is_combat_usable_item(smoke) is True
    assert _is_dungeon_combat_usable_item(smoke) is False
    assert "no hunt cost" in _get_item_effect_string(smoke)

    for retired_key in ("eye_drops", "trap_kit"):
        retired = {"category": "consumable", **CONSUMABLES[retired_key]}
        assert _is_combat_usable_item(retired) is False
        assert "retired" in _get_item_effect_string(retired)
