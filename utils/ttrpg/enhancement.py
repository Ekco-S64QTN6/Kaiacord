"""Gear enhancement: a gil sink that stays worth paying for.

Five of six characters are level 15 with tens or hundreds of thousands of gil
and nothing left to buy; every price in the game is a one-off. Hemlock can
rework a piece of gear, +1 to +5, for an escalating price.

The bonus is small and goes through the existing caps: armour, headgear,
boots and accessories gain +1 defence per level, which the gear soft-cap and
the global DEF cap in combat_engine still bound; a weapon alternates +1
attack and +1 damage. Levels are kept per item key on the sheet
(`enhancements`), so they survive unequipping, and combat reads them by key
the same way it reads the registry.
"""
from __future__ import annotations

from typing import Tuple

MAX_LEVEL = 5
MIN_BASIS = 1000          # a cheap item still costs something to rework
SLOTS = ("weapon", "armor", "head", "boots", "accessory")


def level(sheet: dict, key: str) -> int:
    return int((sheet.get("enhancements") or {}).get(key or "", 0))


def cost(item_value: int, next_level: int) -> int:
    """Half the item's value (at least 1,000) times the level being bought:
    top gear to +5 is 150,000 gil."""
    return max(MIN_BASIS, int(item_value)) * next_level // 2


def weapon_bonus(sheet: dict, key: str) -> Tuple[int, int]:
    """(attack, damage) — odd levels add attack, even levels add damage."""
    n = level(sheet, key)
    return (n + 1) // 2, n // 2


def defence_bonus(sheet: dict, key: str) -> int:
    return level(sheet, key)


def _slot_key(val) -> str:
    if not val:
        return ""
    return val.get("key", "") if isinstance(val, dict) else str(val)


def enhance(sheet: dict, slot: str) -> Tuple[bool, str]:
    """Rework the item in `slot`, paying from gil on hand. Mutates the sheet."""
    from utils.ttrpg.shop import find_item
    if slot not in SLOTS:
        return False, f"Enhance which slot? {', '.join(SLOTS)}."
    key = _slot_key((sheet.get("equipment") or {}).get(slot))
    item = find_item(key) if key else None
    if not item:
        return False, f"Nothing equipped in your {slot} slot."
    current = level(sheet, item["key"])
    if current >= MAX_LEVEL:
        return False, f"**{item['name']}** is already +{MAX_LEVEL}. Hemlock won't touch it again."
    price = cost(item.get("value", 0), current + 1)
    if sheet.get("gil", 0) < price:
        return False, f"+{current + 1} on **{item['name']}** costs {price:,}g. You have {sheet.get('gil', 0):,}g on hand."
    sheet["gil"] -= price
    sheet.setdefault("enhancements", {})[item["key"]] = current + 1
    return True, f"Hemlock reworks your **{item['name']}** to **+{current + 1}** for {price:,}g."


def summary(sheet: dict) -> list[tuple[str, str, int, int | None]]:
    """[(slot, item name, level, next price or None)] for the equipped gear."""
    from utils.ttrpg.shop import find_item
    rows = []
    for slot in SLOTS:
        key = _slot_key((sheet.get("equipment") or {}).get(slot))
        item = find_item(key) if key else None
        if not item:
            continue
        n = level(sheet, item["key"])
        rows.append((slot, item["name"], n, None if n >= MAX_LEVEL else cost(item.get("value", 0), n + 1)))
    return rows
