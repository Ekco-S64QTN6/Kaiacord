"""The inventory limit applies to distinct item keys, not copy count."""
from utils.ttrpg import character_manager
from utils.ttrpg.inventory_capacity import (
    can_add_item,
    can_add_items,
    grant_item,
    grant_items,
    unique_item_type_count,
)


def test_inventory_policy_is_one_hundred_unique_types():
    assert character_manager.INVENTORY_LIMIT == 100
    assert unique_item_type_count(["potion"] * 150) == 1


def test_duplicate_copies_do_not_consume_additional_capacity():
    sheet = {"inventory": ["potion"] * 120}

    assert can_add_item(sheet["inventory"], "potion")
    assert grant_item(sheet, "potion", quantity=80)
    assert sheet["inventory"] == ["potion"] * 200
    assert unique_item_type_count(sheet["inventory"]) == 1


def test_one_hundred_unique_types_fit_but_the_one_hundred_first_does_not():
    sheet = {"inventory": [f"item_{i}" for i in range(99)]}

    assert can_add_item(sheet["inventory"], "item_99")
    assert grant_item(sheet, "item_99")
    assert len(sheet["inventory"]) == 100
    assert unique_item_type_count(sheet["inventory"]) == 100

    # A stack of an item already present still fits at the cap.
    assert can_add_item(sheet["inventory"], "item_3")
    assert grant_item(sheet, "item_3", quantity=3)
    assert len(sheet["inventory"]) == 103
    assert unique_item_type_count(sheet["inventory"]) == 100

    before = list(sheet["inventory"])
    assert not can_add_item(sheet["inventory"], "item_100")
    assert not grant_item(sheet, "item_100")
    assert sheet["inventory"] == before


def test_bulk_reward_grant_is_all_or_nothing_at_capacity_boundary():
    sheet = {"inventory": [f"item_{i}" for i in range(99)]}

    # One new type plus a duplicate stack remains within the cap.
    assert can_add_items(sheet["inventory"], ["item_99", "item_99", "item_0"])
    assert grant_items(sheet, ["item_99", "item_99", "item_0"])
    assert sheet["inventory"][-3:] == ["item_99", "item_99", "item_0"]
    assert unique_item_type_count(sheet["inventory"]) == 100

    before = list(sheet["inventory"])
    # Two new types would require 101 distinct keys; neither is granted.
    assert not can_add_items(sheet["inventory"], ["item_100", "item_101"])
    assert not grant_items(sheet, ["item_100", "item_101"])
    assert sheet["inventory"] == before


def test_bulk_stack_reward_can_exceed_one_hundred_copies_of_one_type():
    sheet = {"inventory": []}
    reward = ["tonic"] * 125

    assert can_add_items(sheet["inventory"], reward)
    assert grant_items(sheet, reward)
    assert len(sheet["inventory"]) == 125
    assert unique_item_type_count(sheet["inventory"]) == 1


def test_failed_bulk_grant_does_not_mutate_inventory_or_create_partial_reward():
    sheet = {"inventory": [f"item_{i}" for i in range(100)]}
    before = list(sheet["inventory"])

    assert not grant_items(sheet, ["item_100", "item_101"])
    assert sheet["inventory"] == before
