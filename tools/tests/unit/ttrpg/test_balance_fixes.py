import pytest
from unittest.mock import patch, MagicMock
import secrets
from utils.ttrpg.combat_engine import _resolve_combat
from utils.ttrpg.encounter_tables import random_encounter, random_event
from utils.ttrpg.equipment_registry import HEADGEAR, BOOTS, ACCESSORIES

def test_defense_soft_cap():
    """Verify that defense values above 10 are soft-capped (halved)."""
    sheet = {
        "character_name": "Tank",
        "class": "Warrior", "level": 1,
        "stats": {"str": 10, "dex": 10, "con": 10},
        "hp": {"current": 20, "max": 20},
        "equipment": {
            "weapon": None, 
            "armor": "adamantine_plate", # 12 DEF
            "head":  "void_helm",        # 3 DEF
            "boots": "void_striders",    # 3 DEF
            "accessory": "void_band"     # 2 DEF
        }
    }
    # Raw Gear DEF = 12 + 3 + 3 + 2 = 20
    # Soft Cap: 10 + (20-10)//2 = 15
    # Total DEF = 10 (Base) + 0 (Dex 10) + 15 (Gear) = 25
    
    monster = {"name": "Test", "hp": {"current": 10, "max": 10}, "attack": 10, "defense": 20, "tier": "medium"}
    
    with patch("secrets.randbelow", side_effect=[14, 0, 0, 0, 0, 0, 0, 0, 0, 0]): # d20 rolls
        # Player: 15 (Misses 20). Monster: 1 (Misses 25).
        # Target DEF: 25. Result: MISS.
        res = _resolve_combat(sheet, monster)
        assert res["monster_hit"] is False
        
    with patch("secrets.randbelow", side_effect=[14, 17, 0, 0, 0, 0]): # d20 rolls = 15, 18
        # Player: 15. Monster: 18 + 7 = 25. Result: HIT.
        res = _resolve_combat(sheet, monster)
        assert res["monster_hit"] is True

def test_tier_scaled_monster_combat():
    """Verify monsters use tier-scaled hit mods and damage dice."""
    sheet = {
        "character_name": "Hero", "class": "Warrior", "level": 1,
        "stats": {"dex": 10}, "hp": {"current": 50, "max": 50},
        "equipment": {"weapon": None, "armor": None, "head": None, "boots": None, "accessory": None}
    }
    # Player DEF = 10
    
    # Deadly Monster
    monster = {"name": "Lich", "attack": 10, "defense": 20, "tier": "deadly", "hp": {"current": 100, "max": 100}}
    # Deadly hit mod = +14
    # Deadly damage = 3d6 + attack//2 (5)
    
    # Sequence: 1.PlayerHit 2.MonsterHit 3..5 Dmg
    with patch("secrets.randbelow", side_effect=[0, 15, 0, 0, 0, 0, 0, 0, 0, 0, 0]):
        # Player: d20(1) fumble
        # Monster: d20(16) + 14 = 30 (HIT vs 10)
        # Damage: 3 * d6(1) + 5 = 8
        res = _resolve_combat(sheet, monster)
        assert res["monster_hit"] is True
        assert res["monster_damage"] == 8

def test_encounter_table_registry():
    """Verify encounter tables pull from the full registry and filter correctly."""
    # Smoke test for random_encounter
    monster = random_encounter("whisperwood_edge", player_level=1)
    assert monster is not None
    
    # Verify filtering
    # Level 10 should filter for hard+ monsters.
    # whisperwood_deep has malboro (hard).
    monster_high = random_encounter("whisperwood_deep", player_level=10)
    from utils.ttrpg.monster_registry import MONSTERS
    assert MONSTERS[monster_high]["tier"] in ["hard", "deadly", "boss"]

@pytest.mark.parametrize("cls,adv,healed", [("Warrior", "", 20), ("Cleric", "", 25),
                                             ("Cleric", "High Priest", 30)])
def test_cleric_heal_bonus(cls, adv, healed):
    """A potion heals a Cleric x1.25 and a High Priest x1.5 (it was a `pass`)."""
    import asyncio
    import types
    from unittest.mock import AsyncMock
    import utils.ttrpg.rpg_core_handler as cor
    sheet = {"user_id": "42", "class": cls, "advanced_class": adv, "inventory": ["hi_potion"],
             "hp": {"current": 10, "max": 100}}
    with patch.object(cor, "load", AsyncMock(return_value=sheet)), \
            patch.object(cor, "save", AsyncMock()), \
            patch.object(cor, "_get_active_view", AsyncMock(return_value=None)), \
            patch.object(cor, "_make_status_view", MagicMock()), \
            patch("utils.ttrpg.shop.find_item",
                  return_value={"name": "Potion", "category": "consumable", "hp_restore": 20}):
        msg = types.SimpleNamespace(channel=types.SimpleNamespace(id=7, send=AsyncMock()))
        ctx = types.SimpleNamespace(bot=None, config=None)
        asyncio.run(cor._handle_use(ctx, msg, None, "hi_potion", "42", "p", False))
    assert sheet["hp"]["current"] == 10 + healed

def test_forest_event_reachability():
    """Verify new events are in the tables."""
    from utils.ttrpg.encounter_tables import EVENTS
    all_events = set()
    for table in EVENTS.values():
        for e, _ in table:
            all_events.add(e)
            
    assert "whisper_in_bark" in all_events
    assert "dream_walker" in all_events

def test_equipment_def_reductions():
    """Verify secondary slot defense values have been reduced."""
    assert HEADGEAR["void_helm"]["defense_bonus"] == 2
    assert BOOTS["void_striders"]["defense_bonus"] == 2
    assert ACCESSORIES["void_band"]["defense_bonus"] == 1
