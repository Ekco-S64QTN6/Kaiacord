"""
All dice resolution. Pure deterministic Python. No LLM path.
"""
import secrets
from typing import Tuple, Optional

STAT_MODIFIER = lambda stat: (stat - 10) // 2

CLASSES = {
    "Warrior":  {"hp_die": 10, "primary": "str"},
    "Ranger":   {"hp_die": 8,  "primary": "dex"},
    "Mage":     {"hp_die": 6,  "primary": "int"},
    "Rogue":    {"hp_die": 6,  "primary": "dex"},
    "Cleric":   {"hp_die": 8,  "primary": "wis"},
}

def roll(notation: str) -> Tuple[int, str]:
    """
    Parse and resolve dice notation. Returns (total, breakdown string).
    Supports: d20, 2d6, 1d8+3, d20-1, 3d6+2
    """
    import re
    notation = notation.strip().lower()
    pattern = re.compile(r'^(\d*)d(\d+)([+-]\d+)?$')
    m = pattern.match(notation)
    if not m:
        raise ValueError(f"Invalid dice notation: {notation}")
    
    count = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    modifier = int(m.group(3)) if m.group(3) else 0
    
    if count < 1 or count > 20 or sides < 2 or sides > 100:
        raise ValueError(f"Dice out of range: {notation}")
    
    rolls = [secrets.randbelow(sides) + 1 for _ in range(count)]
    total = sum(rolls) + modifier
    
    if count == 1:
        breakdown = f"d{sides}={rolls[0]}"
    else:
        breakdown = f"{count}d{sides}=[{','.join(str(r) for r in rolls)}]={sum(rolls)}"
    
    if modifier != 0:
        breakdown += f"{'+' if modifier > 0 else ''}{modifier}"
    
    breakdown += f" → **{total}**"
    return total, breakdown


def stat_check(stat_value: int, dc: int, advantage: bool = False,
               disadvantage: bool = False) -> Tuple[bool, int, str]:
    """
    Roll a d20 stat check against DC.
    Returns (success, total, breakdown).
    """
    mod = STAT_MODIFIER(stat_value)
    
    if advantage and not disadvantage:
        r1 = secrets.randbelow(20) + 1
        r2 = secrets.randbelow(20) + 1
        raw = max(r1, r2)
        breakdown = f"d20 (adv) [{r1},{r2}] → {raw}"
    elif disadvantage and not advantage:
        r1 = secrets.randbelow(20) + 1
        r2 = secrets.randbelow(20) + 1
        raw = min(r1, r2)
        breakdown = f"d20 (dis) [{r1},{r2}] → {raw}"
    else:
        raw = secrets.randbelow(20) + 1
        breakdown = f"d20 → {raw}"
    
    total = raw + mod
    mod_str = f"{'+' if mod >= 0 else ''}{mod}"
    breakdown += f" {mod_str} = **{total}** vs DC {dc}"
    
    success = total >= dc
    return success, total, breakdown


def roll_initiative(dex: int) -> Tuple[int, str]:
    mod = STAT_MODIFIER(dex)
    raw = secrets.randbelow(20) + 1
    total = raw + mod
    return total, f"d20({raw}){'+' if mod >= 0 else ''}{mod} = **{total}**"
