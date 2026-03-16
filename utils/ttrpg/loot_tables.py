"""
Item drops for monster kills based on their difficulty tier.
"""
import secrets
from typing import Optional

def get_loot(tier: str) -> Optional[str]:
    """Returns an item name or None."""
    # (item_name, weight)
    tables = {
        "trivial": [("none", 60), ("Herb", 30), ("Antidote", 10)],
        "easy":    [("none", 40), ("Herb", 25), ("Wolf Pelt", 20), ("Potion", 15)],
        "medium":  [("Potion", 30), ("Ether", 20), ("Monster Fang", 30), ("none", 20)],
        "hard":    [("Hi-Potion", 25), ("Rare Drop", 15), ("Monster Core", 40), ("none", 20)],
        "deadly":  [("Hi-Potion", 20), ("Monster Core", 50), ("Rare Drop", 30)],
        "boss":    [("Elixir", 100)]
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
