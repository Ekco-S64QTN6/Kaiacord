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
