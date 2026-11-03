"""Overworld attacks stay with the encounter owner and origin location."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from utils.ttrpg import rpg_combat_handler as combat


MONSTERS = [
    {"id": "a-goblin", "key": "goblin", "aggro_uid": "A", "origin_location": "trade_road"},
    {"id": "b-goblin", "key": "goblin", "aggro_uid": "B", "origin_location": "trade_road"},
    {"id": "b-wolf", "key": "dire_wolf", "aggro_uid": "B", "origin_location": "trade_road"},
    {"id": "c-wolf", "key": "dire_wolf", "aggro_uid": "C", "origin_location": "whisperwood_edge"},
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
    # B owns a goblin, but naming a different monster must not attack it instead.
    assert _id("B", "dire", "trade_road") is None


def test_legacy_monster_without_origin_location_fails_closed():
    legacy = [{"id": "legacy", "key": "goblin", "aggro_uid": "A"}]
    assert combat.pick_target(legacy, "A", "goblin", "trade_road") is None


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
