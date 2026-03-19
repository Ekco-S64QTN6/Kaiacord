import pytest
from unittest.mock import MagicMock, patch
import time

# Testing new RPG features
from utils.ttrpg.world_state import calculate_next_state
from utils.ttrpg.shop import process_purchase, process_sell
from utils.ttrpg.combat_engine import _resolve_combat

def test_world_state_calculation():
    """Test that world state transitions correctly."""
    # Mock secrets.randbelow to ensure deterministic results
    # weather_roll=10 (< 60 = clear), event_roll=95 (>= 10 = no event)
    with patch("secrets.randbelow", side_effect=[10, 95]):
        new_state = calculate_next_state()
        assert new_state["weather"] == "clear"
        assert new_state["event"] == "none"
        assert new_state["atk_mod"] == 0
        
    # weather_roll=85 (< 95 = stormy), event_roll=5 (< 10 = event), event_idx=0 (resonance_surge)
    with patch("secrets.randbelow", side_effect=[85, 5, 0]):
        new_state = calculate_next_state()
        assert new_state["weather"] == "stormy"
        assert new_state["event"] == "resonance_surge"
        assert new_state["atk_mod"] == -2 + 2 # -2 from storm, +2 from surge
        assert new_state["def_mod"] == -2 + 2


def test_reputation_shop_pricing():
    """Test that reputation correctly affects shop prices."""
    sheet = {"gil": 100, "inventory": [], "class": "Warrior", "reputation": 0}
    
    # Base price (Rep 0)
    # iron_sword is 50g in WEAPONS
    with patch("utils.ttrpg.shop.WEAPONS", {"iron_sword": {"name": "Iron Sword", "value": 50, "key": "iron_sword"}}):
        # Trusted (Rep 50) -> 10% discount (45g)
        success, msg, s50 = process_purchase(sheet.copy(), "iron_sword", 1, reputation=50)
        assert success is True
        assert s50["gil"] == 55 # 100 - 45
        
        # Hero (Rep 100) -> 20% discount (40g)
        success, msg, s100 = process_purchase(sheet.copy(), "iron_sword", 1, reputation=100)
        assert success is True
        assert s100["gil"] == 60 # 100 - 40
        
        # Unwelcome (Rep -25) -> 10% markup (55g)
        success, msg, s_neg = process_purchase(sheet.copy(), "iron_sword", 1, reputation=-25)
        assert success is True
        assert s_neg["gil"] == 45 # 100 - 55
        
        # Outlaw (Rep -60) -> Refusal
        success, msg, s_out = process_purchase(sheet.copy(), "iron_sword", 1, reputation=-60)
        assert success is False
        assert "outlaws" in msg

def test_reputation_selling():
    """Test that reputation affects selling prices."""
    sheet = {"gil": 0, "inventory": ["iron_sword"], "reputation": 0}
    
    with patch("utils.ttrpg.shop.WEAPONS", {"iron_sword": {"name": "Iron Sword", "value": 50, "key": "iron_sword"}}):
        # Base sell (Rep 0) -> 50% (25g)
        s0_input = sheet.copy()
        s0_input["inventory"] = list(sheet["inventory"])
        success, msg, s0 = process_sell(s0_input, "iron_sword", reputation=0)
        assert s0["gil"] == 25
        
        # Hero (Rep 100) -> 50% + 20% = 70% (35g)
        s100_input = sheet.copy()
        s100_input["inventory"] = list(sheet["inventory"])
        success, msg, s100 = process_sell(s100_input, "iron_sword", reputation=100)
        assert s100["gil"] == 35

def test_duel_non_lethal():
    """Test that duels stop at 1 HP."""
    sheet = {
        "character_name": "Player A",
        "class": "Warrior",
        "stats": {"str": 20, "dex": 10, "con": 10},
        "hp": {"current": 20, "max": 20},
        "equipment": {"weapon": None, "armor": None}
    }
    # Opponent with 5 HP
    opponent = {
        "name": "Player B",
        "hp": {"current": 5, "max": 5},
        "attack": 1,
        "defense": 1,
        "id": "player_b"
    }
    
    # Large damage roll to trigger lethal check
    with patch("secrets.randbelow", side_effect=[15, 10, 5, 2]): # Hit, 10 dmg, Miss, Miss
        res = _resolve_combat(sheet, opponent, is_duel=True)
        assert res["monster"]["hp"]["current"] == 1 # Stopped at 1
        # Check if the yield message is anywhere in exchanges
        assert any("Yield!" in ex for ex in res["exchanges"])
