"""Aethelgard: record ids, shop limits, character names, the starter kit and the caravan."""

import pytest


@pytest.mark.parametrize("bad", ["../../etc/x", "a/b", "", "a.b", "x" * 80, "a b"])
def test_record_ids_with_separators_are_refused(bad):
    from utils.ttrpg.record_scan import safe_record_id
    with pytest.raises(ValueError):
        safe_record_id(bad)


def test_a_discord_id_is_a_record_id():
    from utils.ttrpg.record_scan import safe_record_id
    assert safe_record_id(251675123456789012) == "251675123456789012"


def test_housing_lookup_of_a_non_id_is_no_home_not_a_file_read():
    from utils.ttrpg import housing
    assert housing.load_housing("../../x") is None
    assert housing.load_housing("") is None


def test_a_purchase_quantity_is_capped():
    from utils.ttrpg import shop
    sheet = {"location": "hemlocks_store", "gil": 10**9, "inventory": []}
    ok, text, _ = shop.process_purchase(sheet, "earthworm", shop.MAX_PURCHASE_QUANTITY + 1)
    assert ok is False and str(shop.MAX_PURCHASE_QUANTITY) in text


def test_the_merchant_can_be_named_apart_from_the_sheets_location():
    import inspect
    from utils.ttrpg import shop
    assert "merchant" in inspect.signature(shop.process_purchase).parameters


@pytest.mark.parametrize("name,ok", [("Aldric", True), ("D'Arcy", True), ("Jean-Luc", True),
                                     ("<@&123>", False), ("a", False), ("x" * 40, False),
                                     ("@everyone", False), ("two\nlines", False)])
def test_character_name_rule(name, ok):
    from utils.ttrpg.rpg_character_creation_handler import NAME_PATTERN
    assert bool(NAME_PATTERN.fullmatch(name)) is ok


def test_starter_kit_keeps_bait_bought_before_the_first_menu():
    from utils.commands.fishing_handler import grant_starter_kit
    stats = {"bait_stock": {"earthworm": 3}, "bait": "cricket"}
    assert grant_starter_kit(stats) is True
    assert stats["bait_stock"]["earthworm"] == 8 and stats["bait"] == "cricket"
    assert grant_starter_kit(stats) is False


def _town_sheet():
    return {"location": "oakhaven", "gil": 100000, "inventory": [], "equipment": {},
            "reputation": 0, "flags": {}, "stats": {"cha": 10}, "level": 10}


def test_the_caravan_sells_its_stock_to_a_player_in_town_one_gear_piece_each():
    from utils.ttrpg import shop
    from utils.ttrpg.equipment_registry import get_caravan_stock
    gear, consumables = get_caravan_stock()
    ok, _, sheet = shop.process_purchase(_town_sheet(), gear[0], 1, 0, cha_mod=0, merchant="caravan")
    assert ok and sheet["flags"]["caravan_gear_bought"] is True
    ok, text, _ = shop.process_purchase(sheet, gear[1], 1, 0, cha_mod=0, merchant="caravan")
    assert not ok and "One piece of gear" in text
    ok, _, _ = shop.process_purchase(_town_sheet(), consumables[0], 3, 0, cha_mod=0, merchant="caravan")
    assert ok


def test_the_same_gear_is_not_sold_by_the_town_shop():
    from utils.ttrpg import shop
    from utils.ttrpg.equipment_registry import get_caravan_stock
    gear, _ = get_caravan_stock()
    ok, text, _ = shop.process_purchase(_town_sheet(), gear[0], 1, 0, cha_mod=0)
    assert not ok and "doesn't sell" in text
