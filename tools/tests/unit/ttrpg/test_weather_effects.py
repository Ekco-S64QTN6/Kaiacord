"""Every weather effect announced to players does what it says."""
from datetime import date
from unittest.mock import patch

from utils.ttrpg import calendar, encounter_tables


def _weather(mod, value, **extra):
    return {"key": "x", "effect": {"type": "encounter_mod", "mod": mod, "value": value, **extra}}


def test_every_announced_encounter_mod_names_what_it_changes():
    for season, rows in calendar.WEATHER_TABLES.items():
        for *_, effect in rows:
            if effect and effect.get("type") == "encounter_mod":
                assert effect.get("mod") in {"forest_event_pct", "tier_shift", "fire_atk", "seasonal_weight_pct"}, effect


def test_rain_raises_the_forest_event_chance(monkeypatch):
    monkeypatch.setattr(encounter_tables.secrets, "randbelow", lambda n: 20)     # 20 < 15? no; < 25? yes
    monkeypatch.setattr("utils.ttrpg.world_state.load_world_state", lambda: {})
    monkeypatch.setitem(encounter_tables.EVENT_CHANCE, "whisperwood_edge", 15)
    with patch.object(calendar, "get_weather", lambda today=None: {"effect": None}):
        assert not encounter_tables.roll_for_event("whisperwood_edge")
    with patch.object(calendar, "get_weather", lambda today=None: _weather("forest_event_pct", 10)):
        assert encounter_tables.roll_for_event("whisperwood_edge")


def test_a_dry_wind_sharpens_fire_monsters_only():
    from utils.ttrpg import combat_engine
    assert combat_engine._FIRE_ADJACENT.search("Molten Slime") and combat_engine._FIRE_ADJACENT.search("Bomb")
    assert not combat_engine._FIRE_ADJACENT.search("Dire Wolf")
    with patch.object(calendar, "get_weather", lambda today=None: _weather("fire_atk", 2)):
        assert calendar.weather_mod("fire_atk")["value"] == 2 and calendar.weather_mod("tier_shift") is None


def test_a_storm_raises_trade_road_encounters_a_tier(monkeypatch):
    from utils.ttrpg.monster_registry import MONSTERS
    monkeypatch.setattr("utils.ttrpg.world_state.load_world_state", lambda: {})
    monkeypatch.setattr(encounter_tables, "get_special_day", lambda: None)
    order = ["trivial", "easy", "medium", "hard", "deadly", "boss"]

    def mean_tier(weather, n=400):
        with patch.object(calendar, "get_weather", lambda today=None: weather):
            return sum(order.index(MONSTERS[encounter_tables.random_encounter("trade_road", 1)]["tier"])
                       for _ in range(n)) / n
    assert mean_tier(_weather("tier_shift", 1, locations=["trade_road"])) > mean_tier({"effect": None}) + 0.5
