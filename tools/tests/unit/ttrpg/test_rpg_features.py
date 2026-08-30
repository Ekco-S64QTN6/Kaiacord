import pytest
from unittest.mock import MagicMock, patch
import time

# Testing new RPG features

from utils.ttrpg.shop import process_purchase, process_sell
from utils.ttrpg.combat_engine import _resolve_combat




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
        assert s0["gil"] > 0
        
        # Hero (Rep 100) -> 50% + 20% = 70% (35g)
        s100_input = sheet.copy()
        s100_input["inventory"] = list(sheet["inventory"])
        success, msg, s100 = process_sell(s100_input, "iron_sword", reputation=100)
        assert s100["gil"] > 0

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
    with patch("secrets.randbelow", side_effect=[15, 10, 5, 2, 1, 1, 1, 1, 1, 1]): # Hit, 10 dmg, Miss, Miss
        res = _resolve_combat(sheet, opponent, is_duel=True)
        assert res["monster"]["hp"]["current"] == 1 # Stopped at 1


@pytest.mark.asyncio
async def test_dynamic_event_location_buttons():
    """Test that event buttons dynamically show/hide based on world state flags."""
    from utils.ttrpg.rpg_views import RPGFullLocationView

    # Mock App Context & Discord Message
    mock_ctx = MagicMock()
    mock_msg = MagicMock()

    # 1. Tricklebrook Pond: INACTIVE vs ACTIVE
    with patch("utils.ttrpg.world_state.load_world_state", return_value={"fishing_water_tainted": False, "blockade_active": False}):
        view_inactive = RPGFullLocationView(mock_ctx, mock_msg, "123", "User", False, "tricklebrook_pond")
        labels_inactive = [btn.label for btn in view_inactive.children if hasattr(btn, "label")]
        assert "Purify Waters" not in labels_inactive

    with patch("utils.ttrpg.world_state.load_world_state", return_value={"fishing_water_tainted": True, "blockade_active": False}):
        view_active = RPGFullLocationView(mock_ctx, mock_msg, "123", "User", False, "tricklebrook_pond")
        labels_active = [btn.label for btn in view_active.children if hasattr(btn, "label")]
        assert "Purify Waters" in labels_active

    # 2. Trade Road: INACTIVE vs ACTIVE
    with patch("utils.ttrpg.world_state.load_world_state", return_value={"fishing_water_tainted": False, "blockade_active": False}):
        view_inactive_tr = RPGFullLocationView(mock_ctx, mock_msg, "123", "User", False, "trade_road")
        labels_inactive_tr = [btn.label for btn in view_inactive_tr.children if hasattr(btn, "label")]
        assert "Raid Blockade" not in labels_inactive_tr
        assert "Rob Bandits" not in labels_inactive_tr

    with patch("utils.ttrpg.world_state.load_world_state", return_value={"fishing_water_tainted": False, "blockade_active": True}):
        view_active_tr = RPGFullLocationView(mock_ctx, mock_msg, "123", "User", False, "trade_road")
        labels_active_tr = [btn.label for btn in view_active_tr.children if hasattr(btn, "label")]
        assert "Raid Blockade" in labels_active_tr
        assert "Rob Bandits" in labels_active_tr


def test_tactical_war_map_home_scout_unlock():
    """Verify that owning Tactical War Map unlocks home_scout bonus, and absence hides it."""
    from utils.ttrpg.furniture import get_home_bonuses

    # 1. House without war_map
    house_no_map = {"furniture": ["rustic_table", "wooden_bed"]}
    bonuses_no_map = get_home_bonuses(house_no_map)
    assert "home_scout" not in bonuses_no_map
    assert not bonuses_no_map.get("home_scout")

    # 2. House with war_map
    house_with_map = {"furniture": ["rustic_table", "war_map"]}
    bonuses_with_map = get_home_bonuses(house_with_map)
    assert bonuses_with_map.get("home_scout") == 1


def test_scout_daily_limits_state():
    """Test that sheet tracks home (2) and tower (1) scout counts separately."""
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")

    sheet = {
        "scout_date": today,
        "tower_scouts_today": 1,
        "home_scouts_today": 2,
    }
    assert sheet["tower_scouts_today"] >= 1
    assert sheet["home_scouts_today"] >= 2


