"""Overworld micro-events hand out what the weather and inventory allow."""
from datetime import date

import utils.ttrpg.micro_events as me
from utils.ttrpg.character_manager import INVENTORY_LIMIT


def _sheet(inv=None):
    return {"inventory": list(inv or []), "hp": {"current": 10, "max": 20}, "conditions": []}


def test_rain_in_every_season_can_strike_a_shard(monkeypatch):
    """Spring calls it "Raining", the other seasons "Rain"; only the key is stable."""
    for key in ("rain", "storm"):
        monkeypatch.setattr(me, "get_weather", lambda key=key: {"key": key, "name": "Rain"})
        s = _sheet()
        assert me._weather_discovery(s)[0] and s["inventory"] == ["aeridor_shard"]


def test_no_sunny_find_in_a_blizzard(monkeypatch):
    monkeypatch.setattr(me, "get_weather", lambda: {"key": "blizzard", "name": "Blizzard"})
    s = _sheet()
    assert me._weather_discovery(s) == (False, "") and not s["inventory"]


def test_space_is_unique_types_not_stack_size():
    assert me._has_space(_sheet(["potion"] * 80), "tonic")
    full = [f"item_{i}" for i in range(INVENTORY_LIMIT)]
    assert not me._has_space(_sheet(full), "tonic")
    assert me._has_space(_sheet(full), "item_3"), "an item already held adds no type"
