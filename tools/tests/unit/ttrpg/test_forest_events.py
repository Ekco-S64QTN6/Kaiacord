import pytest
from unittest.mock import patch, MagicMock
from utils.ttrpg.forest_events import resolve_event

@pytest.fixture
def base_sheet():
    return {
        "character_name": "TestHero",
        "class": "Warrior",
        "level": 5,
        "hp": {"current": 10, "max": 30},
        "gil": 100,
        "xp": 500,
        "inventory": [],
        "stats": {
            "str": 15,
            "dex": 12,
            "int": 10,
            "wis": 14,
            "con": 13,
            "cha": 16
        }
    }

def test_all_events_can_be_resolved(base_sheet):
    """
    Smoke test: ensures every event defined in EVENT_HANDLERS
    can be called via resolve_event without throwing an exception.
    """
    events_to_test = [
        "sylvan_sprites", "moogle_sighting", "injured_silvani",
        "old_man_riddle", "chocobo_tracks", "aeridor_fragment",
        "gilded_mushroom", "veiled_elder", "timid_tonberry",
        "mognet_delivery", "crystal_resonance", "whisper_in_bark",
        "cactuar_sighting", "abandoned_camp", "strange_statue",
        "echo_of_aeridor", "dream_walker", "twin_wisps",
        "lost_merchant", "ancient_coin"
    ]
    
    # We patch secrets.randbelow to ensure deterministic paths if possible,
    # and to prevent random failures in tests.
    with patch("secrets.randbelow", return_value=0):
        for event_key in events_to_test:
            sheet = base_sheet.copy()
            # Deep copy lists/dicts to prevent cross-contamination between tests
            sheet["hp"] = dict(base_sheet["hp"])
            sheet["stats"] = dict(base_sheet["stats"])
            sheet["inventory"] = list(base_sheet["inventory"])
            
            try:
                result = resolve_event(event_key, sheet)
                assert isinstance(result, dict), f"Event {event_key} did not return a dict result"
                assert "outcome" in result or "event_key" in result, f"Event {event_key} returned malformed dict"
            except Exception as e:
                pytest.fail(f"Event {event_key} raised an exception: {e}")

def test_event_sylvan_sprites(base_sheet):
    """Specific test for a healing event"""
    sheet = base_sheet.copy()
    sheet["hp"] = {"current": 10, "max": 30}
    
    with patch("secrets.randbelow", side_effect=[5, 6]): # heal 5+4=9, xp 6+5=11
        result = resolve_event("sylvan_sprites", sheet)
        
    assert result.get("hp_change", 0) > 0
    assert result.get("xp", 0) > 0
    assert "heal" in result.get("outcome", "").lower()

def test_veiled_elder_buffs(base_sheet):
    """Specific test for class-based buffs"""
    classes = {
        "Warrior": "battle_focus",
        "Ranger": "forest_sight",
        "Mage": "resonance_link",
        "Rogue": "shadow_step",
        "Cleric": "divine_clarity"
    }
    
    for cls, buff in classes.items():
        sheet = base_sheet.copy()
        sheet["class"] = cls
        result = resolve_event("veiled_elder", sheet)
        assert result.get("condition_add") == buff, f"Class {cls} did not get buff {buff}"

def test_mognet_delivery(base_sheet):
    """Specific test for gaining a quest condition"""
    sheet = base_sheet.copy()
    result = resolve_event("mognet_delivery", sheet)
    assert result.get("xp", 0) == 10
    assert result.get("condition_add") == "mognet_pending"

def test_crystal_resonance_damage(base_sheet):
    """Specific test for receiving damage"""
    sheet = base_sheet.copy()
    sheet["hp"] = {"current": 20, "max": 30}
    sheet["stats"] = {"int": 1} # guarantee failure
    
    with patch("secrets.randbelow", side_effect=[1, 2]): # d20 roll, damage roll
        result = resolve_event("crystal_resonance", sheet)
        
    assert result.get("hp_change", 0) < 0 # Took damage

def test_tonberry_knife_drop(base_sheet):
    """Specific test for equipment drops"""
    sheet = base_sheet.copy()
    
    with patch("secrets.randbelow", return_value=1): # outcome 1 is knife drop
        result = resolve_event("timid_tonberry", sheet)
        
    assert result.get("item_add") == "tonberry_knife"


def test_forest_event_knockout_uses_normal_overworld_blackout_flow(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from types import SimpleNamespace

    from utils.ttrpg import outing
    from utils.ttrpg import rpg_combat_handler as combat

    sheet = {
        "user_id": "42",
        "character_name": "TestHero",
        "class": "Warrior",
        "level": 5,
        "location": "whisperwood_edge",
        "hp": {"current": 5, "max": 30},
        "xp": 1000,
        "gil": 200,
        "deaths": 2,
        "hunt_streak": 3,
        "hunts_today": 1,
        "conditions": ["blessed", "fortified"],
        "inventory": [],
    }
    result = {
        "event_key": "crystal_resonance",
        "title": "Crystal Resonance",
        "outcome": "The resonance shatters through you.",
        "xp": 100,
        "gil": 50,
        "hp_change": -10,
        "condition_add": None,
        "condition_remove": None,
        "extra_hunt": False,
        "item_add": None,
        "narration_hook": "a crystal pulse felled the traveler",
    }

    saves = AsyncMock()
    announce = AsyncMock()
    record_event = AsyncMock()
    close = AsyncMock(return_value=True)
    actions = []
    record_event.side_effect = lambda *a, **k: actions.append(("record_event", a, k))
    close.side_effect = lambda *a, **k: actions.append(("close", a, k)) or True

    monkeypatch.setattr(combat, "save", saves)
    monkeypatch.setattr(combat, "check_level_up", lambda current: (False, current["level"]))
    monkeypatch.setattr(combat, "xp_to_next_level", lambda level: 1500)
    monkeypatch.setattr(combat, "_announce_overworld_blackout", announce)
    monkeypatch.setattr(combat, "_make_status_view", lambda *args: "status-view")
    monkeypatch.setattr(outing, "record_event", record_event)
    monkeypatch.setattr(outing, "close", close)

    channel = SimpleNamespace(send=AsyncMock())
    msg = SimpleNamespace(channel=channel)
    ctx = SimpleNamespace()

    asyncio.run(combat._apply_and_narrate_event(
        ctx, msg, None, sheet, result, "TestHero", uid="42", is_owner=False
    ))

    # Event rewards apply first, then the same 10% XP / 5% Gil blackout
    # penalty as ordinary overworld combat.
    assert sheet["xp"] == 990
    assert sheet["gil"] == 238
    assert sheet["hp"] == {"current": 1, "max": 30}
    assert sheet["location"] == "shrine"
    assert sheet["deaths"] == 3
    assert sheet["hunt_streak"] == 0
    # Conditions have the same retention behavior as the existing combat path.
    assert sheet["conditions"] == ["blessed", "fortified"]
    saves.assert_awaited_once_with(sheet)
    announce.assert_awaited_once()
    assert announce.await_args.args == (ctx, sheet, "Crystal Resonance", {
        "xp_loss": 110,
        "gil_loss": 12,
    })

    record_event.assert_awaited_once_with(
        "42", "whisperwood_edge", "Crystal Resonance",
        "a crystal pulse felled the traveler",
    )
    close.assert_awaited_once()
    assert actions[0][0] == "record_event"
    assert actions[1][0] == "close"
    assert actions[1][2]["reason"] == "was knocked out by a forest event and woke at the Shrine"

    assert channel.send.await_count == 2
    event_embed = channel.send.await_args_list[0].kwargs["embed"]
    assert "You blacked out" in event_embed.description
    assert "dropped 110 XP and 12 Gil" in event_embed.description
    recovery = channel.send.await_args_list[1]
    assert recovery.kwargs["view"] == "status-view"
    assert "back at the Shrine" in recovery.kwargs["embed"].description
