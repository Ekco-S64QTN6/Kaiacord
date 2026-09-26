"""Pet passives that are advertised are paid."""

def test_a_fed_house_moogle_delivers_weekly():
    """Five players own one; the 'one item per week' passive had no reader."""
    from utils.ttrpg import pets
    from utils.ttrpg.equipment_registry import CONSUMABLES
    housing = {"pets": [{"key": "moogle", "fed_today": True}, {"key": "cat", "fed_today": True}]}
    for _ in range(pets.MOGNET_EVERY_FED_DAYS - 1):
        pets.reset_daily_pets(housing)
        housing["pets"][0]["fed_today"] = True
    assert not housing.get("mognet_deliveries")
    pets.reset_daily_pets(housing)
    assert housing["mognet_deliveries"] == 1
    sheet = {"inventory": []}
    assert pets.deliver_mognet(sheet, housing) == 1 and housing["mognet_deliveries"] == 0
    item = sheet["mailbox"][0]["item"]
    assert item in CONSUMABLES and 10 <= CONSUMABLES[item]["value"] <= 300
    unfed = {"pets": [{"key": "moogle", "fed_today": False}]}
    for _ in range(10):
        pets.reset_daily_pets(unfed)
    assert not unfed.get("mognet_deliveries")
