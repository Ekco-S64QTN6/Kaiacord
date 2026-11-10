"""Overworld attacks stay with the encounter owner and origin location."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from utils.ttrpg import rpg_combat_handler as combat


MONSTERS = [
    {"id": "a-goblin", "key": "goblin", "aggro_uid": "A", "origin_location": "trade_road"},
    {"id": "b-goblin", "key": "goblin", "aggro_uid": "B", "origin_location": "trade_road"},
    {"id": "b-wolf", "key": "dire_wolf", "aggro_uid": "B", "origin_location": "trade_road"},
    {"id": "c-wolf", "key": "dire_wolf", "aggro_uid": "C", "origin_location": "whisperwood_edge"},
    {"id": "c-shadow", "key": "shadow_hound", "aggro_uid": "C", "origin_location": "trade_road"},
]


def _id(uid, name, location):
    got = combat.pick_target(MONSTERS, uid, name, location)
    return got[1]["id"] if got else None


def test_naming_a_monster_selects_the_callers_own_encounter():
    assert _id("B", "goblin", "trade_road") == "b-goblin"


def test_no_name_selects_only_the_callers_own_encounter():
    assert _id("B", "", "trade_road") == "b-goblin"


def test_same_location_cross_player_assist_is_denied():
    # Both players and the monster are at Trade Road; ownership still wins.
    assert _id("A", "dire", "trade_road") is None


def test_different_location_cross_player_attack_is_denied():
    assert _id("D", "wolf", "trade_road") is None


def test_owner_cannot_attack_an_old_encounter_from_another_location():
    assert _id("A", "goblin", "whisperwood_edge") is None


def test_explicit_foreign_target_does_not_fall_back_to_another_own_fight():
    # B owns a goblin and a dire wolf, but the named Shadow Hound belongs to C.
    assert _id("B", "shadow", "trade_road") is None


def test_legacy_monster_without_origin_location_fails_closed():
    legacy = [{"id": "legacy", "key": "goblin", "aggro_uid": "A"}]
    assert combat.pick_target(legacy, "A", "goblin", "trade_road") is None


def test_owner_id_type_is_normalized_across_spawn_and_attack_paths():
    string_owned = [{
        "id": "string-owned",
        "key": "slime",
        "aggro_uid": "42",
        "origin_location": "oakhaven",
    }]
    picked = combat.pick_target(string_owned, 42, "slime", "oakhaven")
    assert picked is not None
    assert picked[1]["id"] == "string-owned"


def test_attack_denies_same_location_foreign_monster_before_reward_pipeline(monkeypatch):
    sheet = {
        "user_id": "A",
        "character_name": "Attacker",
        "location": "trade_road",
        "hp": {"current": 25, "max": 25},
    }
    session = {
        "channel_id": "123",
        "combat_active": True,
        "monsters": [
            {
                "id": "b-goblin",
                "key": "goblin",
                "name": "Goblin",
                "aggro_uid": "B",
                "origin_location": "trade_road",
                "hp": {"current": 1, "max": 1},
            }
        ],
    }
    save = AsyncMock()
    monkeypatch.setattr(combat, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(combat, "load_session", AsyncMock(return_value=session))
    monkeypatch.setattr(combat, "save", save)

    from utils.ttrpg import combat_engine
    resolve = AsyncMock()
    monkeypatch.setattr(combat_engine, "_resolve_combat", resolve)

    channel = MagicMock()
    channel.send = AsyncMock()
    msg = MagicMock()
    msg.channel = channel

    asyncio.run(combat._handle_attack.__wrapped__(
        None, msg, None, "goblin", "A", "Attacker", False
    ))

    channel.send.assert_awaited_once()
    embed = channel.send.await_args.kwargs["embed"]
    assert "Overworld assists are disabled" in embed.description
    save.assert_not_awaited()
    resolve.assert_not_awaited()
    assert session["monsters"][0]["hp"]["current"] == 1


def test_attack_denies_different_location_foreign_monster_before_reward_pipeline(monkeypatch):
    sheet = {
        "user_id": "A",
        "character_name": "Attacker",
        "location": "trade_road",
        "hp": {"current": 25, "max": 25},
    }
    session = {
        "channel_id": "123",
        "combat_active": True,
        "monsters": [
            {
                "id": "b-goblin",
                "key": "goblin",
                "name": "Goblin",
                "aggro_uid": "B",
                "origin_location": "whisperwood_edge",
                "hp": {"current": 1, "max": 1},
            }
        ],
    }
    save = AsyncMock()
    monkeypatch.setattr(combat, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(combat, "load_session", AsyncMock(return_value=session))
    monkeypatch.setattr(combat, "save", save)

    from utils.ttrpg import combat_engine
    resolve = AsyncMock()
    monkeypatch.setattr(combat_engine, "_resolve_combat", resolve)

    channel = MagicMock()
    channel.send = AsyncMock()
    msg = MagicMock()
    msg.channel = channel

    asyncio.run(combat._handle_attack.__wrapped__(
        None, msg, None, "goblin", "A", "Attacker", False
    ))

    channel.send.assert_awaited_once()
    embed = channel.send.await_args.kwargs["embed"]
    assert "Overworld assists are disabled" in embed.description
    save.assert_not_awaited()
    resolve.assert_not_awaited()
    assert session["monsters"][0]["hp"]["current"] == 1


def _restore_active_overworld_view(monkeypatch, origin_location, current_location):
    from types import SimpleNamespace
    from utils.ttrpg import rpg_views, spine_dungeon

    sheet = {"user_id": "42", "location": current_location}
    monster = {
        "id": "old-wolf",
        "key": "dire_wolf",
        "aggro_uid": "42",
    }
    if origin_location is not None:
        monster["origin_location"] = origin_location
    session = {"combat_active": True, "monsters": [monster]}

    monkeypatch.setattr(rpg_views, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(rpg_views, "load_session", AsyncMock(return_value=session))
    monkeypatch.setattr(rpg_views, "load_dungeon", AsyncMock(return_value=None))
    monkeypatch.setattr(spine_dungeon, "load_spine_dungeon", AsyncMock(return_value=None))
    sentinel = object()
    monkeypatch.setattr(rpg_views, "RPGCombatView", lambda *args: sentinel)

    msg = SimpleNamespace(channel=SimpleNamespace(id=123))
    result = asyncio.run(
        rpg_views._get_active_view(None, msg, "42", "Player", False)
    )
    return result, sentinel


def test_active_view_restores_only_owned_encounter_at_current_location(monkeypatch):
    result, sentinel = _restore_active_overworld_view(
        monkeypatch, "trade_road", "trade_road"
    )
    assert result is sentinel


def test_active_view_does_not_restore_encounter_after_player_moves(monkeypatch):
    result, _ = _restore_active_overworld_view(
        monkeypatch, "trade_road", "whisperwood_edge"
    )
    assert result is None


def test_active_view_fails_closed_for_legacy_encounter_without_origin(monkeypatch):
    result, _ = _restore_active_overworld_view(
        monkeypatch, None, "trade_road"
    )
    assert result is None


def _dungeon_view_at(monkeypatch, location, *, spine=None, dungeon=None):
    from types import SimpleNamespace
    from utils.ttrpg import rpg_views, spine_dungeon, dungeon as dungeon_mod

    monkeypatch.setattr(rpg_views, "load", AsyncMock(return_value={"user_id": "42", "location": location}))
    monkeypatch.setattr(rpg_views, "load_session", AsyncMock(return_value=None))
    monkeypatch.setattr(spine_dungeon, "load_spine_dungeon", AsyncMock(return_value=spine))
    monkeypatch.setattr(dungeon_mod, "load_dungeon", AsyncMock(return_value=dungeon))
    monkeypatch.setattr(rpg_views, "DungeonView", lambda *a: ("dungeon", a[-1]))
    msg = SimpleNamespace(channel=SimpleNamespace(id=123))
    return asyncio.run(rpg_views._get_active_view(None, msg, "42", "Player", False))


def test_an_open_spine_run_gives_no_dungeon_buttons_away_from_the_ruins(monkeypatch):
    spine = {"active": True, "is_spine": True}
    assert _dungeon_view_at(monkeypatch, "trade_road", spine=spine) is None
    assert _dungeon_view_at(monkeypatch, "aeridor_ruins", spine=spine) == ("dungeon", spine)


def test_a_dungeon_gives_its_buttons_only_where_it_was_entered(monkeypatch):
    d = {"active": True, "location": "whisperwood_deep"}
    assert _dungeon_view_at(monkeypatch, "trade_road", dungeon=d) is None
    assert _dungeon_view_at(monkeypatch, "whisperwood_deep", dungeon=d) == ("dungeon", d)
