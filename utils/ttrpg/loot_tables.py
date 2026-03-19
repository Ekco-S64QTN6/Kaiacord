"""
Item drops for monster kills based on their difficulty tier.
Keys match equipment_registry.py CONSUMABLES entries so items can be used/sold.
"""
import secrets
from typing import Optional

def get_loot(tier: str) -> Optional[str]:
    """Returns an item key (matching equipment_registry) or None."""
    tables = {
        "trivial": [("none", 40), ("healing_herb", 20), ("bandage", 10), ("honey_sap", 30)],
        "easy":    [("none", 30), ("healing_herb", 20), ("bandage", 15), ("tonic", 10), ("blood_thistle", 25)],
        "medium":  [("tonic", 20), ("healing_herb", 15), ("bandage", 20), ("silver_moss", 25), ("none", 20)],
        "hard":    [("tonic", 20), ("elixir", 10), ("aeridor_shard", 30), ("dire_root", 25), ("none", 15)],
        "deadly":  [("tonic", 15), ("aeridor_shard", 40), ("elixir", 25), ("dire_root", 20)],
        "boss":    [("elixir", 100)],
    }
    
    table = tables.get(tier, tables["medium"])
    total_weight = sum(w for _, w in table)
    roll = secrets.randbelow(total_weight)

    
    current = 0
    for item_name, weight in table:
        current += weight
        if roll < current:
            return None if item_name == "none" else item_name
            
    return None
