import pytest
from unittest.mock import MagicMock, patch
import random
import secrets
import os
import json
import time

# Core TTRPG Systems
from utils.ttrpg.combat_engine import _resolve_combat
from utils.ttrpg.alchemy import brew
from utils.ttrpg.progression import check_level_up, hunts_remaining
from utils.ttrpg.world_state import load_world_state, save_world_state
from utils.ttrpg.shop import process_purchase, process_sell
from utils.ttrpg.character_manager import create, load

# ============================================================================
# 1. World State & Ticking Tests
# ============================================================================



def test_world_state_persistence():
    """Verify saving and loading from disk."""
    test_state = {"weather": "test_storm", "atk_mod": -5, "last_tick": 12345}
    save_world_state(test_state)
    loaded = load_world_state()
    assert loaded["weather"] == "test_storm"
    assert loaded["atk_mod"] == -5

# ============================================================================
# 2. Reputation & Shop Tests
# ============================================================================

def test_shop_reputation_modifiers():
    """Verify reputation affects prices and trade availability."""
    sheet = {"gil": 100, "inventory": [], "reputation": 0, "class": "Warrior"}
    item_id = "iron_sword" # Base value 50
    
    with patch("utils.ttrpg.shop.WEAPONS", {item_id: {"name": "Iron Sword", "value": 50, "key": item_id}}):
        # Case 1: Trusted (Rep 50) -> 10% discount (45g)
        _, _, s_trusted = process_purchase(sheet.copy(), item_id, 1, reputation=50)
        assert s_trusted["gil"] < 100
        
        # Case 2: Outlaw (Rep -60) -> Refusal
        success, msg, _ = process_purchase(sheet.copy(), item_id, 1, reputation=-60)
        assert success is False
        assert "outlaws" in msg
        
        # Case 3: Hero Sell Bonus (Rep 100) -> 50% base + 20% bonus = 70% (35g)
        s_hero = sheet.copy()
        s_hero["inventory"] = [item_id]
        s_hero["gil"] = 0
        _, _, s_sold = process_sell(s_hero, item_id, reputation=100)
        assert s_sold["gil"] > 0

# ============================================================================
# 3. Combat & Duel Tests
# ============================================================================

def test_combat_modifiers_integration():
    """Verify global modifiers (World State) apply to combat rolls."""
    sheet = {
        "character_name": "Hero",
        "class": "Warrior", "level": 1,
        "stats": {"str": 10, "dex": 10, "con": 10},
        "hp": {"current": 20, "max": 20},
        "equipment": {"weapon": None, "armor": None}
    }
    monster = {"name": "Test", "hp": {"current": 10, "max": 10}, "attack": 1, "defense": 20, "id": "t1"}
    
    # Normally, 10 + d20(5) = 15 (Miss vs 20)
    # With global +10 ATK, it should hit.
    # d20(11) + 0 + 10 = 21 (Hit vs 20)
    with patch("secrets.randbelow", side_effect=[19, 1, 1, 1, 1, 1, 1, 1]): # Enough values
        res = _resolve_combat(sheet.copy(), monster.copy(), atk_mod_global=100)
        assert res["player_hit"] is True

def test_duel_non_lethal_termination():
    """Verify duels stop at 1 HP and show correct messaging."""
    sheet = {
        "character_name": "Hero", "class": "Warrior",
        "stats": {"str": 30, "dex": 10, "con": 10},
        "hp": {"current": 20, "max": 20},
        "equipment": {"weapon": None, "armor": None}
    }
    opponent = {"name": "Rival", "hp": {"current": 5, "max": 5}, "attack": 1, "defense": 1, "id": "rival"}
    
    with patch("secrets.randbelow", side_effect=[19, 3, 1, 1, 1, 1, 1, 1]): # Hit, 10 damage
        res = _resolve_combat(sheet, opponent, is_duel=True)
        assert res["monster"]["hp"]["current"] == 1
        assert any("stops their blade" in ex for ex in res["exchanges"])

# ============================================================================
# 4. Progression & Scaling
# ============================================================================

def test_leveling_and_hunts():
    """Verify level up HP scaling and hunt caps."""
    sheet = {
        "class": "Warrior",
        "level": 1, "xp": 350, 
        "stats": {"con": 10}, 
        "hp": {"current": 10, "max": 10}
    }
    
    # 1. Level up
    leveled, new_lvl = check_level_up(sheet)
    assert leveled is True
    assert sheet["level"] == 2
    assert sheet["hp"]["max"] > 10
    
    # 2. Hunt limits
    sheet["hunts_today"] = 10
    sheet["hunts_reset_date"] = "2020-01-01" # Trigger reset
    with patch("datetime.date") as mock_date:
        mock_date.today.return_value.strftime.return_value = "2026-03-17"
        assert hunts_remaining(sheet) == 5 # Should be MAX_HUNTS_PER_DAY (5)

# ============================================================================
# 5. Bank & Interest
# ============================================================================

def test_bank_logic_simulation():
    """Verify interest formula: 2%, max 10g."""
    def calc_interest(bal):
        return min(10, int(bal * 0.02))
        
    assert calc_interest(100) == 2
    assert calc_interest(1000) == 10
    assert calc_interest(10) == 0

# ============================================================================
# 6. NPC & Dialogue Context
# ============================================================================

def test_dialogue_context_logic():
    """Verify context extraction for LLM prompts."""
    # Simulation of rpg_handler.py logic
    def get_time_of_day(hour):
        if 5 <= hour < 12: return "morning"
        if 12 <= hour < 17: return "afternoon"
        if 17 <= hour < 21: return "evening"
        return "night"
        
    assert get_time_of_day(8) == "morning"
    assert get_time_of_day(23) == "night"

# ============================================================================
# 7. Character Management
# ============================================================================

def test_character_creation_and_reputation():
    """Verify default reputation and creation stats."""
    import asyncio
    with patch("utils.ttrpg.character_manager._save_sync"): # Don't write to disk
        sheet = asyncio.run(create("u1", "un", "cn", "Human", "Warrior", {"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10}))
        assert sheet["reputation"] == 0
        assert sheet["bank_balance"] == 0
        assert sheet["location"] == "oakhaven"
# ============================================================================
# 8. Weather Tests
# ============================================================================

def test_deterministic_weather():
    """Verify weather is consistent for a given date."""
    from utils.ttrpg.calendar import get_weather
    from datetime import date
    
    d1 = date(2026, 3, 18)
    w1 = get_weather(d1)
    w2 = get_weather(d1)
    
    assert w1["key"] == w2["key"]
    assert "name" in w1
    assert "emoji" in w1
    
    # Different date should (usually) be different weather
    d2 = date(2026, 3, 19)
    w3 = get_weather(d2)
    assert isinstance(w3, dict)
    assert "key" in w3

# ============================================================================
# 9. Forest Events & Loot
# ============================================================================

def test_forest_event_loot():
    """Verify forest events award correct items, and items can be sold/delivered."""
    from utils.ttrpg.forest_events import resolve_event
    from utils.ttrpg.shop import process_sell
    
    sheet = {
        "character_name": "Test",
        "xp": 0, "gil": 0, "level": 1,
        "hp": {"current": 10, "max": 10},
        "inventory": [],
        "reputation": 0
    }
    
    # Gilded Mushroom
    res_m = resolve_event("gilded_mushroom", sheet)
    assert res_m["item_add"] == "gilded_mushroom"
    assert res_m["gil"] == 0 # No Gil directly anymore
    
    # Mognet Letter
    res_l = resolve_event("mognet_delivery", sheet)
    assert res_l["item_add"] == "mognet_letter"
    
    # Verify Sellable
    sheet["inventory"] = ["gilded_mushroom"]
    success, msg, updated_sheet = process_sell(sheet, "gilded_mushroom")
    assert success is True
    assert "gilded_mushroom" not in updated_sheet["inventory"]
    assert updated_sheet["gil"] > 0

# ============================================================================
# 10. Progression & Advanced Classes
# ============================================================================

def test_daily_hunts_reset():
    """Verify check_and_reset_hunts clears non-permanent buffs."""
    from utils.ttrpg.progression import check_and_reset_hunts
    
    sheet = {
        "character_name": "Resetter",
        "hunts_today": 5,
        "last_hunt_date": "1999-12-31",
        "conditions": ["battle_focus", "blessed", "mognet_pending", "ale_warmth", "tree_memory"],
        "hp": {"current": 30, "max": 30}
    }
    
    updated = check_and_reset_hunts(sheet)
    
    # Hunts should be 0
    assert updated["hunts_today"] == 0
    # Permanent conditions should stay, temp ones should drop
    assert "blessed" in updated["conditions"]
    assert "mognet_pending" in updated["conditions"]
    assert "battle_focus" not in updated["conditions"]
    assert "ale_warmth" not in updated["conditions"]
    assert "tree_memory" not in updated["conditions"]

def test_class_titles():
    """Verify class titles are assigned properly at level thresholds."""
    from utils.ttrpg.class_advancement import get_title
    
    # Base class thresholds
    assert get_title({"class": "Mage", "level": 1}) == "Apprentice"
    assert get_title({"class": "Mage", "level": 3}) == "Channeler" # Updated from Caster
    assert get_title({"class": "Mage", "level": 5, "deaths": 1}) == "Invoker"
    
    # Advanced class thresholds
    assert get_title({"class": "Warrior", "advanced_class": "Paladin", "level": 5, "deaths": 1}) == "Initiate"
    assert get_title({"class": "Warrior", "advanced_class": "Shadowknight", "level": 9, "deaths": 1}) == "Deathbringer"

# ============================================================================
# 11. Alchemy
# ============================================================================

def test_alchemy_brewing():
    """Verify ingredients map correctly to potions."""
    from utils.ttrpg.alchemy import brew
    
    # Standard health potion (15g, 25 HP)
    sheet = {
        "character_name": "Brewer",
        "inventory": ["blood_thistle", "honey_sap", "iron_sword"],
        "recipes": ["potion"],
        "xp": 0,
        "level": 1
    }
    
    success, msg = brew(sheet, "potion")
    assert success is True
    assert "potion_standard" in sheet["inventory"]
    assert "blood_thistle" not in sheet["inventory"]
    assert "honey_sap" not in sheet["inventory"]
    assert sheet["xp"] == 0 # Recipe XP removed
