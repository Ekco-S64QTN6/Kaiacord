"""
Item drops for monster kills based on their difficulty tier.
Keys match equipment_registry.py CONSUMABLES entries so items can be used/sold.
"""
import secrets
from typing import Optional

def get_loot(tier: str) -> Optional[str]:
    """Returns an item key (matching equipment_registry) or None."""
    # (item_key, weight) — keys must exist in equipment_registry.CONSUMABLES or WEAPONS/ARMOR
    tables = {
        "trivial": [("none", 60), ("healing_herb", 30), ("bandage", 10)],
        "easy":    [("none", 40), ("healing_herb", 25), ("bandage", 20), ("tonic", 15)],
        "medium":  [("tonic", 30), ("healing_herb", 20), ("bandage", 30), ("none", 20)],
        "hard":    [("tonic", 25), ("elixir", 15), ("aeridor_shard", 40), ("none", 20)],
        "deadly":  [("tonic", 20), ("aeridor_shard", 50), ("elixir", 30)],
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
