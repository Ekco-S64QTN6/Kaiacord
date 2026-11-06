"""Detailed character sheets live in a focused renderer behind the core API."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from utils.ttrpg import rpg_core_handler as core
from utils.ttrpg import rpg_sheet_handler as sheet


def test_core_sheet_adapter_forwards_patchable_load_and_view_dependencies(monkeypatch):
    calls = []

    async def replacement(*args, **kwargs):
        calls.append((args, kwargs))
        return "forwarded"

    monkeypatch.setattr(sheet, "_handle_sheet", replacement)
    args = (object(), object(), None, "", "u1", "Ash", False)

    assert asyncio.run(core._handle_sheet(*args)) == "forwarded"
    called_args, kwargs = calls[0]
    assert called_args == args
    assert kwargs["load_character"] is core.load
    assert kwargs["location_icons"] is core.LOCATION_ICONS
    assert kwargs["location_view_factory"] is core.RPGLocationView
    assert kwargs["stale_view_factory"] is core.StaleSafeView
    assert kwargs["status_btn_factory"] is core._make_status_btn
    assert kwargs["hunts_remaining_fn"] is core.hunts_remaining
    assert kwargs["max_hunts_fn"] is core.get_max_hunts
    assert kwargs["xp_to_next_level_fn"] is core.xp_to_next_level


def test_sheet_adapter_keeps_character_not_found_response(monkeypatch):
    monkeypatch.setattr(core, "load", AsyncMock(return_value=None))
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(
        mentions=[],
        channel=SimpleNamespace(send=send),
    )

    asyncio.run(core._handle_sheet(None, msg, None, "", "u1", "Ash", False))

    (embed, view), = sent
    assert embed.description == "Character not found."
    assert view is None



def _sheet_fixture(*, armor=None, level=10, user_id="u1"):
    equipment = {"weapon": None, "armor": armor, "head": None, "boots": None, "accessory": None}
    return {
        "user_id": user_id,
        "character_name": "Ash",
        "race": "Human",
        "class": "Warrior",
        "advanced_class": "",
        "level": level,
        "xp": 250,
        "created_at": 0,
        "stats": {"str": 14, "dex": 10, "con": 12, "int": 10, "wis": 10, "cha": 10},
        "equipment": equipment,
        "hp": {"current": 18, "max": 20},
        "gil": 50,
        "conditions": [],
    }


def _render_sheet(monkeypatch, sheet, *, mentions=None, pet=None, stale=False):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from utils.ttrpg import enhancement, equipment_registry, housing, pets

    monkeypatch.setattr(core, "load", AsyncMock(return_value=sheet))
    monkeypatch.setattr(housing, "load_housing_async", AsyncMock(return_value={"pets": ["test"]}))
    monkeypatch.setattr(pets, "get_pet_passive", lambda _housing: pet or {})
    monkeypatch.setattr(enhancement, "weapon_bonus", lambda *_args: (0, 0))
    monkeypatch.setattr(enhancement, "defence_bonus", lambda *_args: 0)
    monkeypatch.setattr(enhancement, "level", lambda *_args: 0)

    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(
        mentions=mentions or [],
        channel=SimpleNamespace(send=send),
    )

    view_calls = {"stale": [], "status": []}

    class FakeStaleView:
        def __init__(self, timeout=None):
            self.timeout = timeout
            self.items = []

        def add_item(self, item):
            self.items.append(item)

    def stale_view_factory(*, timeout=None):
        view_calls["stale"].append(timeout)
        return FakeStaleView(timeout=timeout)

    def status_btn_factory(*args):
        view_calls["status"].append(args)
        return "viewer-status-button"

    asyncio.run(core._handle_sheet(
        object(), msg, None, "", "u1", "Ash", False
    ))
    (embed, view), = sent
    return embed, view, view_calls


def test_detailed_sheet_includes_pet_attack_and_defense_bonuses(monkeypatch):
    sheet = _sheet_fixture(level=10)
    embed, _view, _calls = _render_sheet(
        monkeypatch, sheet, pet={"combat_bonus": 3, "def_bonus": 2}
    )

    breakdown = next(field.value for field in embed.fields if field.name == "🔬 Breakdown")
    assert "Pet +3" in breakdown
    assert "Pet +2" in breakdown
    combat = next(field.value for field in embed.fields if field.name == "⚔️ Combat")
    assert "**DEF:** **12**" in combat


def test_detailed_sheet_applies_gear_soft_cap_and_level_defense_cap(monkeypatch):
    from utils.ttrpg import equipment_registry

    monkeypatch.setitem(
        equipment_registry.ARMOR,
        "test_armor",
        {"key": "test_armor", "name": "Test Plate", "defense_bonus": 14},
    )
    sheet = _sheet_fixture(armor="test_armor", level=1)
    embed, _view, _calls = _render_sheet(monkeypatch, sheet)

    breakdown = next(field.value for field in embed.fields if field.name == "🔬 Breakdown")
    combat = next(field.value for field in embed.fields if field.name == "⚔️ Combat")
    # Raw gear DEF 14 is softened to 12; base 10 + DEX 0 + gear 12 = 22.
    assert "Gear +12" in breakdown
    assert "= 22 → cap 13" in breakdown
    assert "DEF: **13** *(raw 22, capped)*" in combat
    assert "Level 1 cap: Lv×1.5+12 = 13 effective DEF" in breakdown


def test_viewing_another_players_sheet_uses_stale_view_bound_to_viewer(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    target = _sheet_fixture(level=10, user_id="99")
    loads = []

    async def load(uid):
        loads.append(str(uid))
        return target

    monkeypatch.setattr(core, "load", load)
    sent = []

    async def send(*, embed=None, view=None):
        sent.append((embed, view))

    msg = SimpleNamespace(
        mentions=[SimpleNamespace(id=99)],
        channel=SimpleNamespace(send=send),
    )
    view_calls = []

    class FakeStaleView:
        def __init__(self, timeout=None):
            self.timeout = timeout
            self.items = []

        def add_item(self, item):
            self.items.append(item)

    def stale_view_factory(*, timeout=None):
        return FakeStaleView(timeout=timeout)

    def status_btn_factory(*args):
        view_calls.append(args)
        return "viewer-status-button"

    asyncio.run(sheet._handle_sheet(
        object(), msg, None, "", "42", "Viewer", False,
        load_character=load,
        location_icons={"oakhaven": "🏘️"},
        location_view_factory=lambda *_args: "owner-location-view",
        stale_view_factory=stale_view_factory,
        status_btn_factory=status_btn_factory,
        hunts_remaining_fn=lambda _sheet: 3,
        max_hunts_fn=lambda _sheet: 5,
        xp_to_next_level_fn=lambda _level: 100,
    ))

    (embed, view), = sent
    assert loads == ["99"]
    assert embed.title.startswith("📄  ASH")
    assert view.timeout == 120
    assert view.items == ["viewer-status-button"]
    assert view_calls == [(object.__class__ if False else view_calls[0][0], "42", "Viewer", False)]
    assert view_calls[0][1:] == ("42", "Viewer", False)
