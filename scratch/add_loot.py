import json

new_weapons = {
    # HARD TIER
    "miners_rebellion_pick": {
        "name": "Miners' Rebellion Pick", "type": "weapon", "slot": "weapon", "tier": "hard", "buy_price": 0, "sell_price": 500,
        "attack": 22, "defense": 0, "magic": 0, "speed": 1, "crit_chance": 8, "crit_multiplier": 1.5,
        "classes": ["warrior", "berserker", "paladin"], "passive": "", "effect": "",
        "desc": "A heavy iron pickaxe caked in rusted blood. The miners didn't just dig for ore; eventually, they dug to escape what the Guild sealed them in with. It didn't work."
    },
    "soot_stained_cleaver": {
        "name": "Soot-Stained Cleaver", "type": "weapon", "slot": "weapon", "tier": "hard", "buy_price": 0, "sell_price": 550,
        "attack": 24, "defense": 0, "magic": 0, "speed": 0, "crit_chance": 5, "crit_multiplier": 1.5,
        "classes": ["warrior", "berserker"], "passive": "", "effect": "",
        "desc": "A massive, chipped blade used by the Foreman. The notches in the steel are the exact width of a human collarbone."
    },
    "bone_woven_bow": {
        "name": "Bone-Woven Bow", "type": "weapon", "slot": "weapon", "tier": "hard", "buy_price": 0, "sell_price": 500,
        "attack": 19, "defense": 0, "magic": 0, "speed": 4, "crit_chance": 12, "crit_multiplier": 1.5,
        "classes": ["ranger", "sniper"], "passive": "", "effect": "",
        "desc": "Crafted from vertebrae and strung with sinew. It fires with a sickening snap that echoes too loudly in the dark."
    },
    "echo_chime_focus": {
        "name": "Echo Chime Focus", "type": "weapon", "slot": "weapon", "tier": "hard", "buy_price": 0, "sell_price": 550,
        "attack": 8, "defense": 0, "magic": 22, "speed": 1, "crit_chance": 5, "crit_multiplier": 1.5,
        "classes": ["mage", "invoker"], "passive": "", "effect": "",
        "desc": "A crystal chime that rings when near hidden passages. The magic it casts smells like old copper."
    },
    
    # DEADLY TIER
    "void_touched_scalpel": {
        "name": "Void-Touched Scalpel", "type": "weapon", "slot": "weapon", "tier": "deadly", "buy_price": 0, "sell_price": 1200,
        "attack": 26, "defense": 0, "magic": 5, "speed": 6, "crit_chance": 18, "crit_multiplier": 2.0,
        "classes": ["rogue", "assassin", "ninja"], "passive": "", "effect": "",
        "desc": "An Aeridorian surgical tool, corrupted by the deep dark. It doesn't just cut flesh; it severs the memories attached to it."
    },
    "marrow_bite_spear": {
        "name": "The Marrow-Bite Spear", "type": "weapon", "slot": "weapon", "tier": "deadly", "buy_price": 0, "sell_price": 1300,
        "attack": 28, "defense": 2, "magic": 0, "speed": 3, "crit_chance": 10, "crit_multiplier": 1.5,
        "classes": ["warrior", "dragoon", "paladin"], "passive": "", "effect": "",
        "desc": "Fashioned from the femur of something that shouldn't have fit inside the mountain. It hums when pointed towards Oakhaven."
    },
    "forge_masters_hammer": {
        "name": "Forge-Master's Hammer", "type": "weapon", "slot": "weapon", "tier": "deadly", "buy_price": 0, "sell_price": 1400,
        "attack": 30, "defense": 0, "magic": 0, "speed": 0, "crit_chance": 5, "crit_multiplier": 1.5,
        "classes": ["cleric", "warrior", "paladin"], "passive": "", "effect": "",
        "desc": "It weighs almost too much to lift. The head is permanently white-hot, meant to shape flesh as easily as iron."
    },
    "aeridorian_spine_staff": {
        "name": "Aeridorian Spine-Staff", "type": "weapon", "slot": "weapon", "tier": "deadly", "buy_price": 0, "sell_price": 1300,
        "attack": 12, "defense": 0, "magic": 28, "speed": 2, "crit_chance": 5, "crit_multiplier": 1.5,
        "classes": ["mage", "warlock", "sorcerer"], "passive": "", "effect": "",
        "desc": "A staff that resembles a segmented metallic spinal cord. It occasionally twitches of its own accord."
    },
    
    # BOSS TIER
    "heart_forged_greatsword": {
        "name": "Heart-Forged Greatsword", "type": "weapon", "slot": "weapon", "tier": "boss", "buy_price": 0, "sell_price": 3500,
        "attack": 34, "defense": 0, "magic": 0, "speed": -1, "crit_chance": 5, "crit_multiplier": 2.0,
        "classes": ["warrior", "berserker", "paladin", "dark_knight"], "passive": "", "effect": "",
        "desc": "A blade cast in the white, corrosive blood of the mountain's core. It is impossibly heavy, yet swings itself if the wielder hates enough."
    },
    "elaras_betrayal_dagger": {
        "name": "Elara's Betrayal", "type": "weapon", "slot": "weapon", "tier": "boss", "buy_price": 0, "sell_price": 3500,
        "attack": 30, "defense": 0, "magic": 10, "speed": 8, "crit_chance": 25, "crit_multiplier": 2.5,
        "classes": ["rogue", "assassin", "ninja"], "passive": "", "effect": "",
        "desc": "A ceremonial dagger never meant for combat. It was used to finalize the pact. The edge is so sharp it cuts through the silence."
    },
}

new_armor = {
    "rusted_ironclad_plate": {
        "name": "Rusted Ironclad Plate", "type": "armor", "slot": "armor", "tier": "hard", "buy_price": 0, "sell_price": 600,
        "attack": 0, "defense": 18, "magic": 0, "speed": -3, "hp_bonus": 20,
        "classes": ["warrior", "paladin", "dark_knight"], "passive": "",
        "desc": "Standard issue for the Grimstone deep-guards. The inside of the breastplate has frantic claw marks. They were trying to get out of the armor."
    },
    "ash_woven_robes": {
        "name": "Ash-Woven Robes", "type": "armor", "slot": "armor", "tier": "hard", "buy_price": 0, "sell_price": 500,
        "attack": 0, "defense": 8, "magic": 14, "speed": 1, "hp_bonus": 10,
        "classes": ["mage", "warlock", "sorcerer"], "passive": "",
        "desc": "Garments worn by the Entombed Scholars. They smell eternally of woodsmoke. If you listen closely to the fabric, you can hear a woman apologizing."
    },
    "flesh_forged_cuirass": {
        "name": "Flesh-Forged Cuirass", "type": "armor", "slot": "armor", "tier": "deadly", "buy_price": 0, "sell_price": 1500,
        "attack": 0, "defense": 24, "magic": 0, "speed": -1, "hp_bonus": 40,
        "classes": ["warrior", "berserker", "paladin"], "passive": "",
        "desc": "Aeridorian metal fused with living sinew. It tightens around your chest when you are afraid, feeding off the adrenaline."
    },
    "the_vessels_mantle": {
        "name": "The Vessel's Mantle", "type": "armor", "slot": "armor", "tier": "boss", "buy_price": 0, "sell_price": 4000,
        "attack": 0, "defense": 20, "magic": 25, "speed": 3, "hp_bonus": 60,
        "classes": ["mage", "cleric", "high_priest", "invoker"], "passive": "",
        "desc": "A cloak of pure woven resonance. It was meant for the Elder who feeds the mountain, woven as a reward for her centuries of tribute."
    },
}

new_headgear = {
    "cowl_of_the_blind_leech": {
        "name": "Cowl of the Blind Leech", "type": "headgear", "slot": "headgear", "tier": "hard", "buy_price": 0, "sell_price": 400,
        "attack": 0, "defense": 6, "magic": 0, "speed": 3, "hp_bonus": 0,
        "classes": ["rogue", "assassin", "ninja"], "passive": "",
        "desc": "A hood that covers the eyes entirely. The wearer sees nothing, but feels the pulse of every living thing in the room."
    },
    "slag_crusted_helm": {
        "name": "Slag-Crusted Helm", "type": "headgear", "slot": "headgear", "tier": "deadly", "buy_price": 0, "sell_price": 800,
        "attack": 0, "defense": 12, "magic": 0, "speed": -1, "hp_bonus": 15,
        "classes": ["warrior", "paladin"], "passive": "",
        "desc": "The visor is welded shut by centuries of forge heat. Whoever wore it last did not die from combat, but from the inside."
    },
}

new_boots = {
    "striders_of_the_abyss": {
        "name": "Striders of the Abyss", "type": "boots", "slot": "boots", "tier": "deadly", "buy_price": 0, "sell_price": 750,
        "attack": 0, "defense": 6, "magic": 0, "speed": 6, "hp_bonus": 0,
        "classes": ["rogue", "ranger", "ninja"], "passive": "",
        "desc": "Leather boots treated with an alchemical compound. They make absolutely no sound. The perfect boots for abandoning your friends to the dark."
    },
}

new_accessories = {
    "pendant_of_the_lost_scout": {
        "name": "Pendant of the Lost Scout", "type": "accessory", "slot": "accessory", "tier": "hard", "buy_price": 0, "sell_price": 500,
        "attack": 2, "defense": 2, "magic": 0, "speed": 2, "hp_bonus": 10,
        "classes": ["all"], "passive": "",
        "desc": "A tarnished silver locket containing a map back to Oakhaven. The map is crossed out, and 'THEY KNOW' is etched frantically across the back."
    },
    "resonance_warped_ring": {
        "name": "Resonance-Warped Ring", "type": "accessory", "slot": "accessory", "tier": "deadly", "buy_price": 0, "sell_price": 1000,
        "attack": 0, "defense": 5, "magic": 8, "speed": 0, "hp_bonus": 0,
        "classes": ["all"], "passive": "",
        "desc": "A band of crystal that absorbs light. It was meant to stabilize the wearer's mind against the Whispers, but the crystal is cracked."
    },
    "tithe_collectors_signet": {
        "name": "Tithe-Collector's Signet", "type": "accessory", "slot": "accessory", "tier": "boss", "buy_price": 0, "sell_price": 2500,
        "attack": 5, "defense": 5, "magic": 5, "speed": 0, "hp_bonus": 25,
        "classes": ["all"], "passive": "",
        "desc": "A heavy gold ring bearing the seal of Oakhaven. It burns slightly to the touch. The mountain recognizes this seal, and expects a meal when it approaches."
    },
}

def insert_dict(filename, dict_name, data):
    with open(filename, 'r') as f:
        content = f.read()
    
    import re
    # Find where dict_name = { ends
    # We'll just look for dict_name = { and insert right after it
    pattern = re.compile(rf'({dict_name}\s*=\s*{{)')
    match = pattern.search(content)
    if not match:
        print(f"Could not find {dict_name}")
        return content
        
    insert_str = "\n"
    for k, v in data.items():
        insert_str += f'    "{k}": {{\n'
        for vk, vv in v.items():
            if isinstance(vv, str):
                insert_str += f'        "{vk}": "{vv}",\n'
            elif isinstance(vv, list):
                if len(vv) > 0 and vv[0] == "all":
                    insert_str += f'        "{vk}": ["all"],\n'
                else:
                    insert_str += f'        "{vk}": {json.dumps(vv)},\n'
            else:
                insert_str += f'        "{vk}": {vv},\n'
        insert_str += '    },\n'
        
    return content[:match.end()] + insert_str + content[match.end():]

content = "utils/ttrpg/equipment_registry.py"
with open(content, 'r') as f:
    text = f.read()

for name, d in [("WEAPONS", new_weapons), ("ARMOR", new_armor), ("HEADGEAR", new_headgear), ("BOOTS", new_boots), ("ACCESSORIES", new_accessories)]:
    text = insert_dict("utils/ttrpg/equipment_registry.py", name, d)
    with open("utils/ttrpg/equipment_registry.py", 'w') as f:
        f.write(text)

print("Insertion done.")
