"""Shared-session serialization and idempotency for fishing monster hooks."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _sheet():
    return {
        "user_id": "42",
        "character_name": "Fisher",
        "location": "tricklebrook_pond",
        "level": 5,
        "fishing_stats": {
            "bait": "earthworm",
            "bait_stock": {"earthworm": 2},
            "pole": "test_rod",
            "bag": "woven_sack",
        },
        "fishing_bag": {},
        "conditions": [],
    }


def test_tainted_fishing_hook_takes_channel_then_player_lock_and_preserves_hunt_spawn(monkeypatch):
    from utils.commands import fishing_handler as fishing
    from utils.ttrpg import monster_registry, rpg_views, session_manager, world_state

    sheet = _sheet()
    persisted_sheet = copy.deepcopy(sheet)
    session = {"channel_id": "77", "active": True, "combat_active": False, "monsters": []}
    load_started = asyncio.Event()
    release_fish = asyncio.Event()
    lock_requests = []
    load_session_calls = 0
    rand_rolls = iter([0, 49])  # cast narration choice, then Monster Hook (50)

    async def load_sheet(uid):
        return copy.deepcopy(persisted_sheet)

    async def save_sheet(current):
        persisted_sheet.clear()
        persisted_sheet.update(copy.deepcopy(current))

    async def load_session(channel_id):
        nonlocal load_session_calls
        load_session_calls += 1
        assert channel_id == "77"
        assert (await session_manager.get_action_lock("chan:77")).locked()
        if load_session_calls == 1:
            assert (await session_manager.get_action_lock("user:42")).locked()
            load_started.set()
            await release_fish.wait()
        return copy.deepcopy(session)

    async def save_session(current):
        session.clear()
        session.update(copy.deepcopy(current))

    monkeypatch.setattr(fishing, "load", load_sheet)
    monkeypatch.setattr(fishing, "save", save_sheet)
    monkeypatch.setattr(world_state, "load_world_state", lambda: {"fishing_water_tainted": True})
    monkeypatch.setattr(fishing, "POLES", {"test_rod": {"name": "Test Rod"}})
    monkeypatch.setattr(fishing, "BAIT", {"earthworm": {"name": "Earthworm"}})
    monkeypatch.setattr(fishing, "BAG_UPGRADES", {"woven_sack": {"name": "Woven Sack", "capacity": 10}})
    monkeypatch.setattr(fishing, "get_bite_wait_time", lambda pole: 0)
    monkeypatch.setattr(fishing.secrets, "randbelow", lambda upper: next(rand_rolls))
    monkeypatch.setattr(fishing.secrets, "choice", lambda values: values[0])
    monkeypatch.setattr(monster_registry, "get", lambda key: {
        "name": "Hooked Beast", "desc": "A creature from the deep.", "hp": 12,
    })
    monkeypatch.setattr(session_manager, "load_session", load_session)
    monkeypatch.setattr(session_manager, "save_session", save_session)
    monkeypatch.setattr(rpg_views, "_InteractionMsg", lambda interaction: interaction)
    monkeypatch.setattr(rpg_views, "RPGCombatView", lambda *args: "combat-view")

    original_get_action_lock = fishing.get_action_lock

    async def track_action_lock(key):
        lock_requests.append(key)
        return await original_get_action_lock(key)

    monkeypatch.setattr(fishing, "get_action_lock", track_action_lock)

    interaction = SimpleNamespace(
        id="cast-fish-1",
        channel=SimpleNamespace(id=77),
        followup=SimpleNamespace(send=AsyncMock()),
    )

    async def hunt_action():
        async with await session_manager.get_action_lock("chan:77"):
            async with await session_manager.get_action_lock("user:99"):
                current = await load_session("77")
                current["monsters"].append({"source": "hunt", "aggro_uid": "99"})
                current["combat_active"] = True
                await save_session(current)

    async def run():
        fish_task = asyncio.create_task(
            fishing._cast(None, interaction, "42", "Fisher", False)
        )
        await load_started.wait()
        hunt_task = asyncio.create_task(hunt_action())
        await asyncio.sleep(0)
        assert not hunt_task.done()
        release_fish.set()
        await fish_task
        await hunt_task

    asyncio.run(run())

    assert lock_requests[:2] == ["chan:77", "user:42"]
    assert len(session["monsters"]) == 2
    assert session["monsters"][0]["fishing_hook_cast_id"] == "cast-fish-1"
    assert session["monsters"][1]["source"] == "hunt"
    assert session["fishing_hook_receipts"] == [
        {"cast_id": "cast-fish-1", "monster_key": "blood_slime"}
    ]
    assert persisted_sheet["fishing_stats"]["bait_stock"]["earthworm"] == 1

   
def test_monster_hook_retry_after_session_write_does_not_duplicate_spawn_or_bait(monkeypatch):
    from utils.commands import fishing_handler as fishing
    from utils.ttrpg import monster_registry, rpg_views, session_manager

    persisted_sheet = _sheet()
    persisted_session = {
        "channel_id": "88",
        "active": True,
        "combat_active": False,
        "monsters": [],
    }
    session_saves = []
    sheet_save_attempts = 0

    async def load_sheet(uid):
        return copy.deepcopy(persisted_sheet)

    async def save_sheet(current):
        nonlocal sheet_save_attempts
        sheet_save_attempts += 1
        if sheet_save_attempts == 1:
            # Simulate a process/write failure after the channel session was durable.
            raise OSError("simulated character-sheet write interruption")
        persisted_sheet.clear()
        persisted_sheet.update(copy.deepcopy(current))

    async def load_session(channel_id):
        assert channel_id == "88"
        return copy.deepcopy(persisted_session)

    async def save_session(current):
        session_saves.append(copy.deepcopy(current))
        persisted_session.clear()
        persisted_session.update(copy.deepcopy(current))

    monkeypatch.setattr(fishing, "load", load_sheet)
    monkeypatch.setattr(fishing, "save", save_sheet)
    monkeypatch.setattr(fishing.secrets, "randbelow", lambda upper: 49)  # roll 50: Monster Hook
    monkeypatch.setattr(fishing.secrets, "choice", lambda values: values[0])
    monkeypatch.setattr(
        monster_registry,
        "get",
        lambda key: {"name": "Hooked Beast", "desc": "A creature from the deep.", "hp": 12},
    )
    monkeypatch.setattr(session_manager, "load_session", load_session)
    monkeypatch.setattr(session_manager, "save_session", save_session)
    monkeypatch.setattr(rpg_views, "_InteractionMsg", lambda interaction: interaction)
    monkeypatch.setattr(rpg_views, "RPGCombatView", lambda *args: "combat-view")

    channel = SimpleNamespace(id=88)
    interaction = SimpleNamespace(
        id="stable-hook-cast",
        channel=channel,
        followup=SimpleNamespace(send=AsyncMock()),
    )

    async def resolve_once():
        async with await session_manager.get_action_lock("chan:88"):
            async with await session_manager.get_action_lock("user:42"):
                return await fishing._resolve_bite(
                    None,
                    interaction,
                    "42",
                    "Fisher",
                    False,
                    "test_rod",
                    "earthworm",
                    "Earthworm",
                    True,
                    cast_id="stable-hook-cast",
                )

    async def run_retry():
        try:
            await resolve_once()
            raise AssertionError("the simulated sheet-write interruption should propagate")
        except OSError as exc:
            assert "interruption" in str(exc)

        # The session write committed, but the sheet still has its original bait.
        assert len(persisted_session["monsters"]) == 1
        assert len(persisted_session["fishing_hook_receipts"]) == 1
        assert persisted_sheet["fishing_stats"]["bait_stock"]["earthworm"] == 2
        assert "stable-hook-cast" not in persisted_sheet["fishing_stats"].get("consumed_hook_casts", [])

        await resolve_once()

        # Even after the shared session is later cleaned up, the character's
        # durable consumed-cast marker prevents a delayed callback retry from
        # recreating the monster or spending another bait.
        persisted_session["monsters"] = []
        persisted_session["fishing_hook_receipts"] = []
        await resolve_once()

    asyncio.run(run_retry())

    assert persisted_session["monsters"] == []
    assert persisted_session["fishing_hook_receipts"] == []
    assert len(session_saves) == 1
    assert persisted_sheet["fishing_stats"]["bait_stock"]["earthworm"] == 1
    assert persisted_sheet["fishing_stats"]["consumed_hook_casts"] == ["stable-hook-cast"]
    assert sheet_save_attempts == 2
    assert interaction.followup.send.await_count == 2
