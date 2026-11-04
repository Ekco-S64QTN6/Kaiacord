"""Fishing-bag capacity is enforced at the final reel/claim boundary."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.commands import fishing_handler as fishing


def test_two_pending_bites_cannot_overfill_the_fishing_bag(monkeypatch):
    persisted = {
        "user_id": "42",
        "character_name": "Fisher",
        "fishing_bag": {},
        "fishing_stats": {
            "bait": "earthworm",
            "bait_stock": {"earthworm": 2},
            "pole": "test_rod",
            "bag": "woven_sack",
        },
    }
    lock_by_player = {}

    async def load_sheet(uid):
        return copy.deepcopy(persisted)

    async def save_sheet(sheet):
        persisted.clear()
        persisted.update(copy.deepcopy(sheet))

    async def player_lock(uid):
        return lock_by_player.setdefault(str(uid), asyncio.Lock())

    monkeypatch.setattr(fishing, "load", load_sheet)
    monkeypatch.setattr(fishing, "save", save_sheet)
    monkeypatch.setattr(fishing, "_player_lock", player_lock)
    monkeypatch.setattr(
        fishing,
        "BAG_UPGRADES",
        {"woven_sack": {"name": "Woven Sack", "capacity": 1}},
    )
    monkeypatch.setattr(
        fishing,
        "FISH",
        {"silver_bream": {"name": "Silver Bream", "category": "common", "desc": "A silver fish."}},
    )
    monkeypatch.setattr(
        fishing,
        "POLES",
        {"test_rod": {"name": "Test Rod", "snap_chance": 0}},
    )
    monkeypatch.setattr(fishing, "FishingMenuView", lambda *args: "fishing-menu")
    monkeypatch.setattr(fishing, "update_world_records", lambda *args: False)
    monkeypatch.setattr(fishing.secrets, "randbelow", lambda upper: 9999)

    views = [
        fishing.BiteView(None, "42", "Fisher", False, "silver_bream", 1.5, 10, 30, "earthworm")
        for _ in range(2)
    ]
    interactions = [
        SimpleNamespace(
            user=SimpleNamespace(id=42),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        for _ in range(2)
    ]
    buttons = [next(child for child in view.children if child.label == "🎣 Reel It In!") for view in views]

    async def run():
        await asyncio.gather(*[
            button.callback(interaction)
            for button, interaction in zip(buttons, interactions)
        ])

    asyncio.run(run())

    stored_catches = sum(len(catches) for catches in persisted["fishing_bag"].values())
    assert stored_catches == 1
    assert persisted["fishing_stats"]["total_caught"] == 1
    assert persisted["fishing_stats"]["bait_stock"]["earthworm"] == 0
    # The second bite was rejected at the claim point, not counted as a catch.
    descriptions = [
        call.kwargs["embed"].description
        for interaction in interactions
        for call in interaction.followup.send.await_args_list
        if call.kwargs.get("embed") is not None
    ]
    assert any("filled up before you reeled it in" in description for description in descriptions)
