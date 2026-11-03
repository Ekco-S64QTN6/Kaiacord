"""Shared inventory-capacity policy and grant helpers.

The RPG inventory is capped by the number of distinct item keys, not by the
number of copies. Repeated copies of an existing key do not use additional
capacity; stack quantity is otherwise unlimited by this rule.
"""


def unique_item_type_count(inventory) -> int:
    """Count distinct item keys currently in an inventory."""
    return len(set(inventory or []))


def can_add_items(inventory, item_keys) -> bool:
    """Whether all requested item copies fit under the unique-type limit."""
    from utils.ttrpg.character_manager import INVENTORY_LIMIT

    if isinstance(item_keys, str):
        item_keys = [item_keys]
    additions = list(item_keys or [])
    if any(not isinstance(key, str) or not key for key in additions):
        return False
    return len(set(inventory or []) | set(additions)) <= INVENTORY_LIMIT


def can_add_item(inventory, item_key: str) -> bool:
    """Whether one copy of item_key can be added without exceeding the cap."""
    return can_add_items(inventory, [item_key])


def grant_items(sheet: dict, item_keys) -> bool:
    """Atomically validate and append a batch of item copies to a character sheet.

    Returns False without changing the inventory when the batch would exceed
    the unique-type limit. Duplicate copies count as one type.
    """
    if isinstance(item_keys, str):
        additions = [item_keys]
    else:
        additions = list(item_keys or [])
    if not additions:
        return True
    if any(not isinstance(key, str) or not key for key in additions):
        return False

    inventory = sheet.setdefault("inventory", [])
    if not isinstance(inventory, list) or not can_add_items(inventory, additions):
        return False
    inventory.extend(additions)
    return True


def grant_item(sheet: dict, item_key: str, quantity: int = 1) -> bool:
    """Grant quantity copies of one item under the shared capacity policy."""
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        return False
    return grant_items(sheet, [item_key] * quantity)
