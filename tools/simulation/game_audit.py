import os
import sys
import secrets
import asyncio
import json
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from utils.ttrpg.character_manager import create
from utils.ttrpg.combat_engine import _resolve_combat
from utils.ttrpg.monster_registry import get as get_monster, random_encounter
from utils.ttrpg.forest_events import resolve_event
from utils.ttrpg.progression import check_level_up, XP_THRESHOLDS

# Configuration
HUNTS_PER_SET = 200 # More hunts for better data
CLASSES_TO_TEST = ["Warrior", "Ranger", "Mage", "Rogue", "Cleric"]

STATS = {
    "Warrior": {"str": 16, "dex": 12, "con": 14, "int": 8, "wis": 10, "cha": 10},
    "Ranger":  {"str": 12, "dex": 16, "con": 14, "int": 10, "wis": 12, "cha": 8},
    "Mage":    {"str": 8,  "dex": 14, "con": 12, "int": 16, "wis": 12, "cha": 10},
    "Rogue":   {"str": 10, "dex": 18, "con": 12, "int": 12, "wis": 10, "cha": 10},
    "Cleric":  {"str": 12, "dex": 10, "con": 14, "int": 10, "wis": 16, "cha": 12},
}

class SimulationResult:
    def __init__(self, class_name):
        self.class_name = class_name
        self.wins = 0
        self.deaths = 0
        self.events = 0
        self.hp_lost = 0
        self.gil_earned = 0
        self.xp_earned = 0
        self.levels_gained = 0
        self.monsters_killed = {}
        self.bugs_found = []

    def report(self):
        total_encounters = self.wins + self.deaths
        win_rate = (self.wins / total_encounters * 100) if total_encounters > 0 else 0
        avg_hp_lost = (self.hp_lost / total_encounters) if total_encounters > 0 else 0
        
        return {
            "class": self.class_name,
            "win_rate": f"{win_rate:.1f}%",
            "deaths": self.deaths,
            "avg_hp_loss": f"{avg_hp_lost:.1f}",
            "gil_per_hunt": f"{(self.gil_earned / HUNTS_PER_SET):.1f}",
            "xp_per_hunt": f"{(self.xp_earned / HUNTS_PER_SET):.1f}",
            "max_level": self.levels_gained + 1,
            "bugs": self.bugs_found
        }

async def run_sim_for_class(class_name):
    res = SimulationResult(class_name)
    stats = STATS[class_name]
    
    # Mock save to avoid writing to disk
    with patch("utils.ttrpg.character_manager.save"):
        sheet = create("sim_user", "Sim", f"Sim_{class_name}", "Human", class_name, stats)
    
    # Gear setup
    base_gear = {
        "Warrior": {"weapon": "hand_axe", "armor": "leather_armor"},
        "Ranger":  {"weapon": "shortbow", "armor": "leather_armor"},
        "Mage":    {"weapon": "wooden_staff", "armor": "mages_robe"},
        "Rogue":   {"weapon": "rusty_dagger", "armor": "leather_armor"},
        "Cleric":  {"weapon": "wooden_staff", "armor": "leather_armor"},
    }
    sheet["equipment"] = base_gear[class_name]

    for i in range(HUNTS_PER_SET):
        # Determine location based on level
        if sheet["level"] < 3:
            loc = "whisperwood_edge"
        elif sheet["level"] < 5:
            loc = "trade_road"
        elif sheet["level"] < 8:
            loc = "whisperwood_deep"
        else:
            loc = "aeridor_ruins"

        # Event vs Combat
        if secrets.randbelow(100) < 20:
            event_keys = ["sylvan_sprites", "moogle_sighting", "injured_silvani", "gilded_mushroom"]
            event_key = secrets.choice(event_keys)
            try:
                evt_res = resolve_event(event_key, sheet)
                res.events += 1
                res.xp_earned += evt_res.get("xp", 0)
                res.gil_earned += evt_res.get("gil", 0)
                sheet["hp"]["current"] = max(0, min(sheet["hp"]["max"], sheet["hp"]["current"] + evt_res.get("hp_change", 0)))
                sheet["xp"] += evt_res.get("xp", 0)
                sheet["gil"] += evt_res.get("gil", 0)
                if evt_res.get("item_add"):
                    sheet["inventory"].append(evt_res["item_add"])
            except Exception as e:
                res.bugs_found.append(f"Event Error ({event_key}): {str(e)}")
        else:
            # Combat
            m_key = random_encounter(loc)
            monster_base = get_monster(m_key)
            if not monster_base:
                res.bugs_found.append(f"Missing Monster: {m_key}")
                continue
            
            # Prepare monster dict for combat engine
            monster = {
                "name": monster_base["name"],
                "attack": monster_base["attack"],
                "defense": monster_base["defense"],
                "hp": {"current": monster_base["hp"], "max": monster_base["hp"]},
                "xp": monster_base["xp"],
                "gil": monster_base["gil"]
            }
            
            start_hp = sheet["hp"]["current"]
            rounds = 0
            while monster["hp"]["current"] > 0 and sheet["hp"]["current"] > 0 and rounds < 50:
                try:
                    round_res = _resolve_combat(sheet, monster)
                    sheet = round_res["sheet"]
                    monster = round_res["monster"]
                    rounds += 1
                except Exception as e:
                    res.bugs_found.append(f"Combat Error ({m_key}): {str(e)}")
                    break
            
            if rounds >= 50:
                res.bugs_found.append(f"Infinite Combat: {class_name} vs {m_key}")
            
            res.hp_lost += (start_hp - sheet["hp"]["current"])
            
            if sheet["hp"]["current"] > 0:
                res.wins += 1
                res.xp_earned += monster["xp"]
                res.gil_earned += monster["gil"]
                sheet["xp"] += monster["xp"]
                sheet["gil"] += monster["gil"]
                res.monsters_killed[monster['name']] = res.monsters_killed.get(monster['name'], 0) + 1
            else:
                res.deaths += 1
                sheet["hp"]["current"] = sheet["hp"]["max"] # Respawn
        
        # Level up check
        leveled, new_lvl = check_level_up(sheet)
        if leveled:
            res.levels_gained += 1
            sheet["hp"]["current"] = sheet["hp"]["max"]

        # Basic "Heal" simulation - if low HP, "rest" (costs nothing for simulation)
        if sheet["hp"]["current"] < (sheet["hp"]["max"] / 2):
            sheet["hp"]["current"] = sheet["hp"]["max"]

        # Gear Upgrades
        if sheet["gil"] > 100:
            if sheet["equipment"]["armor"] == "leather_armor":
                sheet["equipment"]["armor"] = "studded_leather"
                sheet["gil"] -= 40
            elif sheet["equipment"]["armor"] == "mages_robe" and class_name == "Mage":
                sheet["equipment"]["armor"] = "silken_robe"
                sheet["gil"] -= 45
        
        if sheet["gil"] > 80 and sheet["level"] >= 3:
            if class_name == "Warrior" and sheet["equipment"]["weapon"] == "hand_axe":
                sheet["equipment"]["weapon"] = "iron_sword"
                sheet["gil"] -= 35
            elif class_name == "Mage" and sheet["equipment"]["weapon"] == "wooden_staff":
                sheet["equipment"]["weapon"] = "iron_staff"
                sheet["gil"] -= 30
            elif class_name == "Ranger" and sheet["equipment"]["weapon"] == "shortbow":
                # Upgrades to longsword or similar? Shortbow is Tier 1.
                pass

    return res

async def main():
    print(f"Starting Aethelgard Balance Simulation...")
    reports = []
    for cls in CLASSES_TO_TEST:
        print(f"  Simulating {cls}...")
        res = await run_sim_for_class(cls)
        reports.append(res.report())
    
    with open("tools/simulation/audit_results.json", "w") as f:
        json.dump(reports, f, indent=2)
    
    print("\n--- SIMULATION COMPLETE ---")
    for r in reports:
        print(f"{r['class']:8} | Win: {r['win_rate']:6} | Deaths: {r['deaths']:2} | XP/H: {r['xp_per_hunt']:5} | Max Lvl: {r['max_level']}")

if __name__ == "__main__":
    asyncio.run(main())
