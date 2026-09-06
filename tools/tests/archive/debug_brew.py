import sys, os, json
sys.path.insert(0, '/home/ekco/github/Kaiacord')

from utils.ttrpg.housing import load_housing
from utils.ttrpg.furniture import get_home_bonuses, FURNITURE
from utils.ttrpg.world import LOCATION_DATA

uid = "1415184297744404482"
housing = load_housing(uid)
print(f"Housing found: {housing is not None}")
if housing:
    print(f"Furniture keys: {housing.get('furniture', [])}")
    bonuses = get_home_bonuses(housing)
    print(f"Bonuses: {bonuses}")
    has_alchemy = bonuses.get("home_brewing")
    print(f"Has Alchemy: {has_alchemy}")

loc = "watchtower"
station_here = LOCATION_DATA.get(loc, {}).get("brewing_allowed")
print(f"Station here ({loc}): {station_here}")

error_triggered = (not station_here and not has_alchemy)
print(f"Error triggered: {error_triggered}")

# Let's check if there are any other furniture keys that might be relevant
for key, data in FURNITURE.items():
    if "Alchemy" in data["name"]:
        print(f"Found FURNITURE key: {key} (Name: {data['name']})")

