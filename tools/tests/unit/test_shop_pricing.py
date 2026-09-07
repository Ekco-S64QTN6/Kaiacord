"""Shop pricing — the dropdown label must match what checkout charges.

`noon_events_mechanical_audit.md` Phase A flagged a "shop dropdown price bug"
and it sat unfixed while the rest of that table was struck through as done.
The UI computed its own price applying only the calendar and sale overrides,
ignoring reputation, the CHA discount (up to 10%) and the market-glut
multiplier — so a player with any CHA modifier saw one number and was charged
another. Both sides now call `shop.get_buy_price`.
"""
import pytest

from utils.ttrpg.shop import find_item, get_buy_price, get_sell_price, process_purchase


@pytest.fixture
def item():
    from utils.ttrpg.equipment_registry import WEAPONS
    key = "steel_longsword" if "steel_longsword" in WEAPONS else next(iter(WEAPONS))
    return find_item(key)


def _sheet(gil=999_999):
    return {"gil": gil, "inventory": [], "level": 5,
            "location": "hemlocks_store", "flags": {}, "stats": {"cha": 10}}


def test_base_price_is_the_item_value(item):
    assert get_buy_price(item, "hemlocks_store") == item["value"]


@pytest.mark.parametrize("reputation,expected_mult", [
    (100, 0.8),   # 20% discount
    (50, 0.9),    # 10% discount
    (0, 1.0),
    (-50, 1.1),   # 10% markup
])
def test_reputation_moves_the_price(item, reputation, expected_mult):
    assert get_buy_price(item, "hemlocks_store", reputation=reputation) == \
        int(item["value"] * expected_mult)


def test_cha_discount_is_capped_at_ten_percent(item):
    assert get_buy_price(item, "hemlocks_store", cha_mod=20) == int(item["value"] * 0.90)
    assert get_buy_price(item, "hemlocks_store", cha_mod=1) == int(item["value"] * 0.98)


def test_negative_cha_does_not_raise_the_price(item):
    """The discount floors at zero; a dump-CHA character pays list, not more."""
    assert get_buy_price(item, "hemlocks_store", cha_mod=-5) == item["value"]


def test_quantity_scales(item):
    assert get_buy_price(item, "hemlocks_store", quantity=3) == item["value"] * 3


@pytest.mark.parametrize("reputation,cha_mod", [(0, 0), (50, 0), (0, 4), (100, 4), (-50, 2)])
def test_label_price_equals_the_amount_actually_charged(item, reputation, cha_mod):
    """The bug: these two were computed by different code."""
    label = get_buy_price(item, "hemlocks_store", reputation=reputation, cha_mod=cha_mod)

    sheet = _sheet(gil=label)          # exactly enough, and not a gil more
    ok, msg, after = process_purchase(sheet, item["key"], 1,
                                      reputation=reputation, cha_mod=cha_mod)
    assert ok, f"labelled {label}g but purchase was refused: {msg}"
    assert after["gil"] == 0, f"labelled {label}g, charged {label - after['gil']}g"


def test_one_gil_short_is_refused(item):
    """Guards the boundary from the other side: if the label were lower than
    the charge, this would pass and the player would be over-billed."""
    price = get_buy_price(item, "hemlocks_store")
    ok, _msg, _ = process_purchase(_sheet(gil=price - 1), item["key"], 1)
    assert ok is False


def test_buy_price_is_not_the_sell_price(item):
    """Sanity: the two paths are distinct and sell is the worse deal."""
    assert get_sell_price(item["value"]) < get_buy_price(item, "hemlocks_store")


def test_unknown_item_does_not_crash_the_label():
    assert find_item("no_such_item_key") is None
