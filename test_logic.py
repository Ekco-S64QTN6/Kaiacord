def get_home_bonuses(housing):
    return {"home_brewing": 1}

def test_logic(loc, _housing):
    LOCATION_DATA = {} # empty initially
    _has_alchemy_table = _housing and get_home_bonuses(_housing).get("home_brewing")
    print(f"Testing loc={loc}, _housing={_housing}")
    print(f"  LOCATION_DATA: {LOCATION_DATA.get(loc, {}).get('brewing_allowed')}")
    print(f"  _has_alchemy: {_has_alchemy_table}")
    if not LOCATION_DATA.get(loc, {}).get("brewing_allowed") and not _has_alchemy_table:
        print("  RESULT: ERROR TRIGGERED!")
    else:
        print("  RESULT: SUCCESS!")

test_logic("housing_district", {"home": "yes"})
test_logic("oakhaven", {"home": "yes"})
