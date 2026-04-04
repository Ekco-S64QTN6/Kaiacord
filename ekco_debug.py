import sys, os, json
sys.path.insert(0, '/home/ekco/github/Kaiacord')

from utils.ttrpg.character_manager import load
from utils.ttrpg.housing import load_housing
from utils.ttrpg.furniture import get_home_bonuses
from utils.ttrpg.world import LOCATION_DATA

async def main():
    uid = "177011971818782721"
    sheet = await load(uid)
    housing = load_housing(uid)
    
    loc = sheet.get("location", "oakhaven")
    bonuses = get_home_bonuses(housing)
    has_alchemy = bonuses.get("home_brewing")
    
    print(f"User: {sheet.get('character_name')}")
    print(f"Location: {loc}")
    print(f"Housing found: {housing is not None}")
    print(f"Bonuses: {bonuses}")
    print(f"Brewing allowed at loc: {LOCATION_DATA.get(loc, {}).get('brewing_allowed')}")
    
    error_triggered = (not LOCATION_DATA.get(loc, {}).get("brewing_allowed") and not has_alchemy)
    print(f"Error triggered: {error_triggered}")

import asyncio
asyncio.run(main())
