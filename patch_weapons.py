import json

with open("utils/ttrpg/equipment_registry.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_classes = {
    "rusty_dagger": '["Rogue", "Trickster", "Mage", "Wizard", "Necromancer", "Ranger", "Hunter"]',
    "wooden_club": '["Warrior", "Cleric", "Paladin", "Shaman"]',
    "shortbow": '["Ranger", "Hunter", "Rogue", "Trickster"]',
    "rusty_hand_axe": '["Warrior", "Ranger", "Hunter"]',
    "rusty_stiletto": '["Rogue", "Trickster"]',
    "iron_sword": '["Warrior", "Paladin", "Shadowknight", "Ranger"]',
    "iron_spear": '["Warrior", "Ranger", "Hunter", "Paladin"]',
    "crossbow": '["Ranger", "Hunter", "Rogue", "Trickster"]',
    "iron_battle_axe": '["Warrior", "Paladin", "Shadowknight"]',
    "iron_dirk": '["Rogue", "Trickster", "Ranger"]',
    "steel_longsword": '["Warrior", "Paladin", "Shadowknight"]',
    "steel_dagger": '["Rogue", "Trickster", "Ranger"]',
    "flame_sword": '["Warrior", "Paladin", "Shadowknight", "Mage", "Wizard"]',
    "ice_brand": '["Warrior", "Paladin", "Shadowknight", "Mage", "Wizard"]',
    "flame_scepter": '["Mage", "Wizard", "Necromancer", "Cleric", "High Priest"]',
    "flametongue": '["Warrior", "Paladin"]',
    "frostbrand": '["Warrior", "Paladin"]',
    "aeridorian_axe": '["Warrior", "Paladin", "Shadowknight"]',
    "ykesha_sword": '["Warrior", "Shadowknight"]',
    "ultima_weapon": '["Warrior", "Paladin", "Shadowknight"]'
}

with open("utils/ttrpg/equipment_registry.py", "w", encoding="utf-8") as f:
    for line in lines:
        for w_key, c_val in new_classes.items():
            if f'"{w_key}":' in line and '"name":' in line and '"tier":' in line and '"classes"' not in line:
                line = line.rstrip()
                if line.endswith(","):
                    line = line[:-1]
                # line may end with } or },
                if line.endswith("}"):
                    line = line[:-1] + f', "classes": {c_val}' + "}," + "\n"
                else: # already removed comma, so ends with }
                    line = line + f', "classes": {c_val}' + "}," + "\n"
                # prevent multiple replacements in same line by not breaking but we know only 1 matches
                # wait, let's just do it cleanly
                break
        f.write(line)
