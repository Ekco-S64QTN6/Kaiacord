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




def test_fifty_unique_item_types_are_well_below_the_selected_cap():
    inventory = [f"item_{i}" for i in range(50)]

    assert unique_item_type_count(inventory) == 50
    assert can_add_item(inventory, "item_50")
    sheet = {"inventory": inventory}
    assert grant_item(sheet, "item_50")
    assert unique_item_type_count(sheet["inventory"]) == 51


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

    from utils.ttrpg import (
        farming,
        furniture,
        housing as housing_store,
        rpg_housing_handler as housing,
    )

    existing_crop = {"crop_key": "existing_plot"}
    blocked_crop = {"crop_key": "new_plot"}
    sheet = {"user_id": "42", "inventory": [f"item_{i}" for i in range(100)]}
    sheet["inventory"][0] = "existing_crop_item"
    home = {"user_id": "42", "farming": {"plots": [existing_crop, blocked_crop]}}

    monkeypatch.setattr(housing, "load", AsyncMock(return_value=sheet))
    save_sheet = AsyncMock()
    from utils.ttrpg import character_manager
    monkeypatch.setattr(housing, "save", save_sheet)
    monkeypatch.setattr(character_manager, "save", save_sheet)
    monkeypatch.setattr(housing_store, "load_housing", lambda uid: home)
    saved_homes = []
    monkeypatch.setattr(housing_store, "save_housing", lambda value: saved_homes.append(value))

    async def save_housing_async(value):
        saved_homes.append(value)

    monkeypatch.setattr(housing_store, "save_housing_async", save_housing_async)
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
    assert "Left on the plots" in send.await_args.args[1]


def test_reward_goes_to_moogle_mail_when_inventory_is_full():
    from utils.ttrpg.inventory_capacity import grant_item_or_mail

    sheet = {"inventory": [f"item_{i}" for i in range(100)]}

    delivery = grant_item_or_mail(sheet, "quest_relic", "The Lost Reliquary")

    assert delivery == "mailbox"
    assert "quest_relic" not in sheet["inventory"]
    assert len(sheet["mailbox"]) == 1
    assert sheet["mailbox"][0]["from_name"] == "The Lost Reliquary"
    assert sheet["mailbox"][0]["item"] == "quest_relic"
    assert sheet["mailbox"][0]["gil"] == 0


def test_reward_is_granted_directly_when_inventory_has_capacity():
    from utils.ttrpg.inventory_capacity import grant_item_or_mail

    sheet = {"inventory": [f"item_{i}" for i in range(99)]}

    delivery = grant_item_or_mail(sheet, "quest_relic", "The Lost Reliquary")

    assert delivery == "inventory"
    assert "quest_relic" in sheet["inventory"]
    assert "mailbox" not in sheet


def test_moogle_mail_partial_claim_preserves_item_but_delivers_gil():
    from utils.ttrpg.rpg_views import MailMenuView

    sheet = {
        "inventory": [f"item_{i}" for i in range(100)],
        "gil": 25,
        "mailbox": [
            {
                "dispatch_id": "dispatch-1",
                "from_name": "A Friend",
                "item": "quest_relic",
                "gil": 40,
            }
        ],
    }
    view = MailMenuView(None, None, "42", "Tester", False, sheet)

    first_claim = view._claim(sheet["mailbox"])

    assert sheet["gil"] == 65
    assert len(sheet["mailbox"]) == 1
    assert sheet["mailbox"][0]["item"] == "quest_relic"
    assert sheet["mailbox"][0]["gil"] == 0
    assert "inventory full" in first_claim[0]

    # Once the player makes room, the same attachment can be claimed without
    # paying its Gil a second time.
    sheet["inventory"].pop()
    second_claim = view._claim(sheet["mailbox"])

    assert "quest_relic" in sheet["inventory"]
    assert sheet["mailbox"] == []
    assert sheet["gil"] == 65
    assert "quest relic" in second_claim[0].lower()


def test_player_reward_modules_do_not_bypass_the_shared_inventory_grant():
    from pathlib import Path
    import re

    repository = Path(__file__).resolve().parents[4]
    reward_modules = (
        "utils/ttrpg/rpg_views.py",
        "utils/ttrpg/rpg_social_handler.py",
        "utils/commands/fishing_handler.py",
        "utils/core/background_tasks.py",
        "utils/ttrpg/rpg_core_handler.py",
        "utils/ttrpg/rpg_combat_handler.py",
        "utils/ttrpg/rpg_housing_handler.py",
        "utils/ttrpg/micro_events.py",
        "utils/ttrpg/alchemy.py",
        "utils/ttrpg/shop.py",
        "utils/ttrpg/rpg_shop_handler.py",
        "utils/ttrpg/pets.py",
        "utils/ttrpg/forest_events.py",
        "utils/ttrpg/farming.py",
    )
    mail_fallback_modules = (
        "utils/ttrpg/rpg_views.py",
        # NPC quest rewards now delegate to this shared exactly-once settlement
        # helper, which owns the inventory grant and Moogle Mail fallback.
        "utils/ttrpg/quest_completion.py",
        "utils/commands/fishing_handler.py",
        "utils/core/background_tasks.py",
        "utils/ttrpg/rpg_core_handler.py",
        "utils/ttrpg/rpg_combat_handler.py",
        "utils/ttrpg/micro_events.py",
    )
    direct_inventory_write = re.compile(
        r"(?:"
        r"\w+\.setdefault\(['\"]inventory['\"],\s*\[\]\)\.(?:append|extend)"
        r"|\w+\[['\"]inventory['\"]\]\.(?:append|extend)"
        r"|\b(?:inventory|inv)\.(?:append|extend)"
        r")\s*\("
    )

    violations = {}
    for relative_path in reward_modules:
        source = (repository / relative_path).read_text(encoding="utf-8")
        matches = [
            f"{line_number}: {line.strip()}"
            for line_number, line in enumerate(source.splitlines(), start=1)
            if direct_inventory_write.search(line)
        ]
        if matches:
            violations[relative_path] = matches

    assert not violations, (
        "Player-facing inventory grants must use utils.ttrpg.inventory_capacity; "
        f"raw writes remain: {violations}"
    )

    # Each reward family whose policy is "deliver or preserve for later" must
    # explicitly use the same mailbox fallback rather than inventing its own.
    missing_fallback = [
        path for path in mail_fallback_modules
        if "grant_item_or_mail" not in (repository / path).read_text(encoding="utf-8")
    ]
    assert not missing_fallback, (
        "These reward families must preserve full-bag rewards in Moogle Mail: "
        f"{missing_fallback}"
    )
