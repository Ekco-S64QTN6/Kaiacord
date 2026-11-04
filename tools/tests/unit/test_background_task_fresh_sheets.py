"""Background events must commit only event deltas to fresh character sheets."""
import asyncio
import copy
import random
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_moogle_festival_preserves_player_update_after_candidate_snapshot(monkeypatch):
    from utils.core import background_tasks
    from utils.ttrpg import broadcast, character_manager, session_manager

    user_id = "42001"
    stale_snapshot = {
        "user_id": user_id,
        "character_name": "Old Name",
        "location": "oakhaven",
        "gil": 200,
        "inventory": [],
        "conditions": [],
    }
    live_sheet = copy.deepcopy(stale_snapshot)

    async def load_all():
        # This is the detached candidate list used by the event for discovery.
        return [copy.deepcopy(stale_snapshot)]

    async def load(uid):
        return copy.deepcopy(live_sheet) if str(uid) == user_id else None

    async def save(sheet):
        live_sheet.clear()
        live_sheet.update(copy.deepcopy(sheet))

    monkeypatch.setattr(character_manager, "load_all", load_all)
    monkeypatch.setattr(character_manager, "load", load)
    monkeypatch.setattr(character_manager, "save", save)
    monkeypatch.setattr(background_tasks.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(secrets, "randbelow", lambda upper: 0)  # deterministic Bandage
    monkeypatch.setattr(broadcast, "log_world_event", AsyncMock())

    real_mutate = background_tasks._mutate_player_sheet
    interleaved = False

    async def player_action_then_event_commit(uid, mutation):
        nonlocal interleaved
        if not interleaved:
            # A real player action wins the same lock after load_all() but
            # before the event reloads and commits its reward.
            async with await session_manager.get_action_lock(f"user:{uid}"):
                live_sheet["gil"] -= 25
                live_sheet["inventory"].append("potion_standard")
                live_sheet["conditions"].append("blessed")
                live_sheet["character_name"] = "Updated Adventurer"
            interleaved = True
        return await real_mutate(uid, mutation)

    monkeypatch.setattr(
        background_tasks, "_mutate_player_sheet", player_action_then_event_commit
    )
    channel = SimpleNamespace(send=AsyncMock())

    asyncio.run(background_tasks.run_moogle_festival(None, channel))

    assert interleaved is True
    assert live_sheet["gil"] == 175
    assert live_sheet["inventory"] == ["potion_standard", "bandage"]
    assert live_sheet["conditions"] == ["blessed"]
    assert live_sheet["character_name"] == "Updated Adventurer"
    final_embed = channel.send.await_args.kwargs["embed"]
    assert "Updated Adventurer" in final_embed.description
    assert "Bandage" in final_embed.description


def test_combat_event_applies_only_hp_and_reward_deltas_to_fresh_sheet(monkeypatch):
    from utils.core import background_tasks
    from utils.ttrpg import character_manager

    user_id = "42002"
    live_sheet = {
        "user_id": user_id,
        "character_name": "Delta Tester",
        "class": "Warrior",
        "level": 1,
        "stats": {"con": 10},
        "hp": {"current": 30, "max": 50},
        "xp": 10,
        "gil": 75,
        "reputation": 5,
        "inventory": ["potion_standard"],
        "conditions": ["lucky", "blessed"],
    }

    async def load(uid):
        return copy.deepcopy(live_sheet) if str(uid) == user_id else None

    async def save(sheet):
        live_sheet.clear()
        live_sheet.update(copy.deepcopy(sheet))

    monkeypatch.setattr(character_manager, "load", load)
    monkeypatch.setattr(character_manager, "save", save)

    result = asyncio.run(background_tasks._commit_background_combat_result(
        user_id,
        starting_hp=20,
        simulated_hp=12,
        consumed_conditions={"lucky"},
        xp_reward=25,
        gil_reward=10,
        reputation_delta=3,
    ))

    assert result["blackout"] is None
    assert live_sheet["hp"] == {"current": 22, "max": 50}
    assert live_sheet["xp"] == 35
    assert live_sheet["gil"] == 85
    assert live_sheet["reputation"] == 8
    assert live_sheet["inventory"] == ["potion_standard"]
    assert live_sheet["conditions"] == ["blessed"]


def test_blight_event_preserves_crop_planted_after_candidate_snapshot(monkeypatch):
    from utils.core import background_tasks
    from utils.ttrpg import broadcast, character_manager, farming, housing, session_manager

    user_id = "42003"
    old_plot = {"crop_key": "blood_thistle_seed", "stage": 2, "blighted": False}
    live_housing = {
        "user_id": user_id,
        "character_name": "Gardener",
        "farming": {"plots": [copy.deepcopy(old_plot)]},
    }

    async def load_all_sheets():
        return [{"user_id": user_id, "character_name": "Current Gardener"}]

    def load_all_homes():
        # Detached pre-event snapshot: only the original crop exists.
        return [copy.deepcopy(live_housing)]

    async def load_home(uid):
        assert str(uid) == user_id
        return copy.deepcopy(live_housing)

    async def save_home(value):
        live_housing.clear()
        live_housing.update(copy.deepcopy(value))

    monkeypatch.setattr(character_manager, "load_all", load_all_sheets)
    monkeypatch.setattr(housing, "load_all_housing", load_all_homes)
    monkeypatch.setattr(housing, "load_housing_async", load_home)
    monkeypatch.setattr(housing, "save_housing_async", save_home)
    monkeypatch.setattr(background_tasks.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(background_tasks, "log_action", lambda *args, **kwargs: None)
    monkeypatch.setattr(broadcast, "log_world_event", AsyncMock())

    # The event chooses the first plot after candidate discovery.
    monkeypatch.setattr(secrets, "randbelow", lambda upper: 0)
    monkeypatch.setattr(random, "sample", lambda population, count: list(population)[:count])

    real_mutate = background_tasks._mutate_player_housing
    interleaved = False

    async def player_plants_then_event_mutates(uid, mutation):
        nonlocal interleaved
        if not interleaved:
            async with await session_manager.get_action_lock(f"user:{uid}"):
                live_housing["farming"]["plots"].append({
                    "crop_key": "honey_sap_seed",
                    "stage": 1,
                    "blighted": False,
                })
            interleaved = True
        return await real_mutate(uid, mutation)

    monkeypatch.setattr(
        background_tasks, "_mutate_player_housing", player_plants_then_event_mutates
    )
    channel = SimpleNamespace(send=AsyncMock())

    asyncio.run(background_tasks.run_blight_on_the_crops(None, channel))

    assert interleaved is True
    plots = live_housing["farming"]["plots"]
    assert len(plots) == 2
    assert plots[0]["blighted"] is True
    assert plots[1] == {
        "crop_key": "honey_sap_seed",
        "stage": 1,
        "blighted": False,
    }
    final_embed = channel.send.await_args.kwargs["embed"]
    assert "Current Gardener" in final_embed.description
    assert "Blood Thistle Seed" in final_embed.description
