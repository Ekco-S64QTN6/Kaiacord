import pytest
from unittest.mock import patch
from utils.ttrpg.shop import process_purchase, get_shop_inventory

def test_caravan_gear_limit():
    """Verify that only one gear item can be bought at the caravan."""
    sheet = {
        "gil": 10000,
        "inventory": [],
        "flags": {},
        "location": "caravan",
        "reputation": 0
    }
    
    # Mock Tier 3 item
    item_key = "masterwork_sword"
    item_id = "masterwork_sword"
    with patch("utils.ttrpg.shop.find_item", return_value={"name": "Masterwork Sword", "value": 1000, "category": "weapon", "key": item_id}):
        # 1. First purchase should succeed
        success, msg, s1 = process_purchase(sheet.copy(), item_key)
        assert success is True
        assert s1["flags"]["caravan_gear_bought"] is True
        assert item_id in s1["inventory"]
        
        # 2. Second purchase should fail
        success, msg, s2 = process_purchase(s1, item_key)
        assert success is False
        assert "One piece of gear" in msg

def test_caravan_consumable_no_limit():
    """Verify that consumables have no limit at the caravan."""
    sheet = {
        "gil": 1000,
        "inventory": [],
        "flags": {"caravan_gear_bought": True}, # Already bought gear
        "location": "caravan",
        "reputation": 0
    }
    
    item_key = "potion_high"
    with patch("utils.ttrpg.shop.find_item", return_value={"name": "High Potion", "value": 100, "category": "consumable", "key": "potion_high"}):
        success, msg, s1 = process_purchase(sheet.copy(), item_key)
        assert success is True
        assert "potion_high" in s1["inventory"]

def test_caravan_inventory_filtering():
    """Verify that the caravan only shows Tier 3 items."""
    # Patch WHERE it is defined (since it is imported inside the function in shop.py)
    with patch("utils.ttrpg.shop.WEAPONS", {
        "t1_sword": {"name": "T1", "tier": 1},
        "t3_sword": {"name": "T3", "tier": 3}
    }):
        with patch("utils.ttrpg.equipment_registry.get_caravan_stock", return_value=(["t3_sword"], [])):
            weapons, _, _, _, _, _ = get_shop_inventory("caravan")
            assert "t3_sword" in weapons
            assert "t1_sword" not in weapons
