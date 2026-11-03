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


def test_alchemy_brew_uses_net_unique_types_after_consuming_ingredients():
    from utils.ttrpg.alchemy import brew

    sheet = {
        "recipes": ["potion"],
        "inventory": [
            "blood_thistle",
            "honey_sap",
            *[f"item_{i}" for i in range(98)],
        ],
    }

    success, message = brew(sheet, "potion")

    assert success is True
    assert "Successfully brewed" in message
    assert "blood_thistle" not in sheet["inventory"]
    assert "honey_sap" not in sheet["inventory"]
    assert "potion_standard" in sheet["inventory"]
    assert unique_item_type_count(sheet["inventory"]) == 99


def test_alchemy_brew_refuses_to_overflow_legacy_over_cap_inventory():
    from utils.ttrpg.alchemy import brew

    original = [
        "blood_thistle",
        "honey_sap",
        *[f"item_{i}" for i in range(100)],
    ]
    sheet = {"recipes": ["potion"], "inventory": list(original)}

    success, message = brew(sheet, "potion")

    assert success is False
    assert "unique item types" in message
    assert sheet["inventory"] == original


def test_shop_purchase_uses_shared_unique_item_grant_at_capacity(monkeypatch):
    from utils.ttrpg import shop
    from utils.ttrpg.character_manager import INVENTORY_LIMIT

    monkeypatch.setattr(shop, "_in_stock", lambda location, key: True)
    monkeypatch.setattr(shop, "get_buy_price", lambda *args, **kwargs: 10)

    # Existing item type remains purchasable as a stack at the cap.
    sheet = {
        "location": "hemlocks_store",
        "gil": 100,
        "inventory": ["potion_standard", *[
            f"item_{i}" for i in range(INVENTORY_LIMIT - 1)
        ]],
    }
    success, _, updated = shop.process_purchase(sheet, "potion_standard", quantity=5)
    assert success is True
    assert updated["gil"] == 90
    assert updated["inventory"].count("potion_standard") == 6
    assert unique_item_type_count(updated["inventory"]) == INVENTORY_LIMIT

    # A new key cannot be added to an already-full unique-type inventory.
    blocked = {
        "location": "hemlocks_store",
        "gil": 100,
        "inventory": [f"item_{i}" for i in range(INVENTORY_LIMIT)],
    }
    before = list(blocked["inventory"])
    success, message, unchanged = shop.process_purchase(blocked, "potion_standard")
    assert success is False
    assert "unique item types" in message
    assert unchanged["gil"] == 100
    assert unchanged["inventory"] == before


def test_harvest_at_capacity_keeps_new_item_types_on_their_plots(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from utils.ttrpg import farming, furniture, rpg_housing_handler as housing

    existing_crop = {"crop_key": "existing_plot"}
    blocked_crop = {"crop_key": "new_plot"}
    sheet = {"inventory": [f"item_{i}" for i in range(100)]}
    sheet["inventory"][0] = "existing_crop_item"
    home = {"farming": {"plots": [existing_crop, blocked_crop]}}

    monkeypatch.setattr(housing, "load", AsyncMock(return_value=sheet))
    save_sheet = AsyncMock()
    monkeypatch.setattr(housing, "save", save_sheet)
    monkeypatch.setattr(housing, "load_housing", lambda uid: home)
    saved_homes = []
    monkeypatch.setattr(housing, "save_housing", lambda value: saved_homes.append(value))
    monkeypatch.setattr(farming, "is_harvestable", lambda plot: True)
    monkeypatch.setattr(
        farming,
        "harvest_crop",
        lambda plot, season, bonus: (
            ("existing_crop_item", 4) if plot is existing_crop
            else ("new_crop_item", 2)
        ),
    )
    monkeypatch.setattr(housing, "_handle_my_home", AsyncMock())
    monkeypatch.setattr("utils.ttrpg.calendar.get_season", lambda: "spring")
    monkeypatch.setattr(furniture, "get_home_bonuses", lambda value: {})

    channel = SimpleNamespace()
    msg = SimpleNamespace(channel=channel)
    send = AsyncMock()

    asyncio.run(housing._handle_harvest_crops.__wrapped__(
        None, msg, send, "", "42", "Tester", False
    ))

    assert sheet["inventory"].count("existing_crop_item") == 5
    assert "new_crop_item" not in sheet["inventory"]
    assert home["farming"]["plots"] == [blocked_crop]
    save_sheet.assert_awaited_once_with(sheet)
    assert saved_homes == [home]
    assert "new crop item" in send.await_args.args[1]
    assert "remain on their plots" in send.await_args.args[1]
