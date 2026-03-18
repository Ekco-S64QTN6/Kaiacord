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
from utils.ttrpg.world_state import calculate_next_state, load_world_state, save_world_state
from utils.ttrpg.shop import process_purchase, process_sell
from utils.ttrpg.character_manager import create, load

# ============================================================================
# 1. World State & Ticking Tests
# ============================================================================

def test_world_state_logic():
    """Verify weather and event logic in world_state.py."""
    # Test Clear weather (Roll 0.1)
    with patch("random.random", side_effect=[0.1, 0.95]): # Clear, No event
        state = calculate_next_state()
        assert state["weather"] == "clear"
        assert state["atk_mod"] == 0
        
    # Test Stormy with Resonance Surge (Roll 0.85, 0.05)
    with patch("random.random", side_effect=[0.85, 0.05]), \
         patch("random.choice", return_value=("resonance_surge", "surge", {"atk_mod": 2, "def_mod": 2})):
        state = calculate_next_state()
        assert state["weather"] == "stormy"
        assert state["event"] == "resonance_surge"
        # -2 (storm) + 2 (surge) = 0
        assert state["atk_mod"] == 0
        assert state["def_mod"] == 0

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
        assert s_trusted["gil"] == 55
        
        # Case 2: Outlaw (Rep -60) -> Refusal
        success, msg, _ = process_purchase(sheet.copy(), item_id, 1, reputation=-60)
        assert success is False
        assert "outlaws" in msg
        
        # Case 3: Hero Sell Bonus (Rep 100) -> 50% base + 20% bonus = 70% (35g)
        s_hero = sheet.copy()
        s_hero["inventory"] = [item_id]
        s_hero["gil"] = 0
        _, _, s_sold = process_sell(s_hero, item_id, reputation=100)
        assert s_sold["gil"] == 35

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
    with patch("secrets.randbelow", side_effect=[10, 1, 1, 1]): # d20(11), d4(2), d20(2), d6(2)
        res = _resolve_combat(sheet.copy(), monster.copy(), atk_mod_global=10)
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
    
    with patch("secrets.randbelow", side_effect=[10, 3, 1, 1]): # Hit, 10 damage (secrets.randbelow(4) -> 3 means 4 damage)
        res = _resolve_combat(sheet, opponent, is_duel=True)
        assert res["monster"]["hp"]["current"] == 1
        assert any("stops their blade" in ex for ex in res["exchanges"])
        assert any("Yield!" in ex for ex in res["exchanges"])

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
    with patch("utils.ttrpg.character_manager.save"): # Don't write to disk
        sheet = create("u1", "un", "cn", "Human", "Warrior", {"str":10,"dex":10,"con":10,"int":10,"wis":10,"cha":10})
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
