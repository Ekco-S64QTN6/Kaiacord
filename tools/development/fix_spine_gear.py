#!/usr/bin/env python3
"""
Remove the 20 broken items (wrong field names) and replace with
properly formatted Spine Dungeon gear sets.

Upper Spine (T4, floors 1-40): 5 classes × 5 slots = 25 items
Lower Spine (T5, floors 41-77): 5 classes × 5 slots = 25 items
Total: 50 items, all with correct field schema and weapon procs.
"""
import re

BROKEN_KEYS = [
    "miners_rebellion_pick", "soot_stained_cleaver", "bone_woven_bow", "echo_chime_focus",
    "void_touched_scalpel", "marrow_bite_spear", "forge_masters_hammer", "aeridorian_spine_staff",
    "heart_forged_greatsword", "elaras_betrayal_dagger",
    "rusted_ironclad_plate", "ash_woven_robes", "flesh_forged_cuirass", "the_vessels_mantle",
    "cowl_of_the_blind_leech", "slag_crusted_helm",
    "striders_of_the_abyss",
    "pendant_of_the_lost_scout", "resonance_warped_ring", "tithe_collectors_signet",
]

# ─── UPPER SPINE SET (Tier 4, Floors 1-40) ────────────────────────
UPPER_WEAPONS = {
    # Warrior
    "miners_rebellion_pick": {
        "name": "Miners' Rebellion Pick",
        "attack_bonus": 7, "damage_die": 10, "damage_bonus": 5,
        "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "proc": {"name": "Iron Fury", "emoji": "⛏️", "die": 6, "element": "physical"},
    },
    # Ranger
    "bone_woven_bow": {
        "name": "Bone-Woven Bow",
        "attack_bonus": 6, "damage_die": 8, "damage_bonus": 5,
        "value": 1350, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
        "proc": {"name": "Marrow Snap", "emoji": "💀", "die": 6, "element": "physical"},
    },
    # Mage
    "echo_chime_focus": {
        "name": "Echo Chime Focus",
        "attack_bonus": 5, "damage_die": 8, "damage_bonus": 6,
        "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "proc": {"name": "Resonance Pulse", "emoji": "🔔", "die": 6, "element": "arcane"},
    },
    # Rogue
    "soot_stained_cleaver": {
        "name": "Soot-Stained Cleaver",
        "attack_bonus": 7, "damage_die": 8, "damage_bonus": 4,
        "value": 1350, "tier": 4, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "proc": {"name": "Choking Ash", "emoji": "🌫️", "die": 6, "element": "shadow"},
    },
    # Cleric
    "crypt_warden_mace": {
        "name": "Crypt Warden's Mace",
        "attack_bonus": 6, "damage_die": 8, "damage_bonus": 5,
        "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Paladin"],
        "proc": {"name": "Sanctified Strike", "emoji": "✨", "die": 6, "element": "holy"},
    },
}

UPPER_ARMOR = {
    "rusted_ironclad_plate": {
        "name": "Rusted Ironclad Plate", "defense_bonus": 10, "stat_bonus": {"str": 1},
        "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "desc": "Standard issue for the Grimstone deep-guards. The inside of the breastplate has frantic claw marks.",
    },
    "scouts_bone_leather": {
        "name": "Scout's Bone Leather", "defense_bonus": 7, "stat_bonus": {"dex": 2},
        "value": 1350, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
        "desc": "Treated with marrow oil from the Bone Warrens. The leather is eerily light.",
    },
    "ash_woven_robes": {
        "name": "Ash-Woven Robes", "defense_bonus": 5, "stat_bonus": {"int": 2},
        "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "desc": "Garments worn by the Entombed Scholars. If you listen closely, you can hear a woman apologizing.",
    },
    "tunnel_runners_garb": {
        "name": "Tunnel Runner's Garb", "defense_bonus": 6, "stat_bonus": {"dex": 2},
        "value": 1350, "tier": 4, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "Worn by the miners who tried to escape. They ran in the dark. The leather remembers the route.",
    },
    "deep_chaplains_vestment": {
        "name": "Deep Chaplain's Vestment", "defense_bonus": 8, "stat_bonus": {"wis": 2},
        "value": 1400, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
        "desc": "A priest was assigned to bless each shift. He stopped blessing. He started praying.",
    },
}

UPPER_HEADGEAR = {
    "slag_crusted_helm": {
        "name": "Slag-Crusted Helm", "defense_bonus": 3,
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "desc": "The visor is welded shut by centuries of forge heat. Whoever wore it last did not die from combat.",
    },
    "tunnel_scouts_hood": {
        "name": "Tunnel Scout's Hood", "defense_bonus": 2, "stat_bonus": {"dex": 1},
        "value": 1250, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
    },
    "scholars_ashen_cowl": {
        "name": "Scholar's Ashen Cowl", "defense_bonus": 1, "stat_bonus": {"int": 1},
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
    },
    "cowl_of_the_blind_leech": {
        "name": "Cowl of the Blind Leech", "defense_bonus": 2, "stat_bonus": {"dex": 1},
        "value": 1250, "tier": 4, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "A hood that covers the eyes. The wearer sees nothing, but feels the pulse of every living thing.",
    },
    "deep_chaplains_mitre": {
        "name": "Deep Chaplain's Mitre", "defense_bonus": 2, "stat_bonus": {"wis": 1},
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

UPPER_BOOTS = {
    "ironclad_stompers": {
        "name": "Ironclad Stompers", "defense_bonus": 3,
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "tunnel_runners_boots": {
        "name": "Tunnel Runner's Boots", "defense_bonus": 2, "stat_bonus": {"dex": 1},
        "value": 1250, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
    },
    "emberwalk_slippers": {
        "name": "Emberwalk Slippers", "defense_bonus": 1, "stat_bonus": {"int": 1},
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
    },
    "striders_of_the_abyss": {
        "name": "Striders of the Abyss", "defense_bonus": 2, "stat_bonus": {"dex": 1},
        "value": 1250, "tier": 4, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "They make absolutely no sound. The perfect boots for abandoning your friends to the dark.",
    },
    "deep_chaplains_sandals": {
        "name": "Deep Chaplain's Sandals", "defense_bonus": 2, "stat_bonus": {"wis": 1},
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

UPPER_ACCESSORIES = {
    "pendant_of_the_lost_scout": {
        "name": "Pendant of the Lost Scout", "defense_bonus": 1, "attack_bonus": 2,
        "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "desc": "A silver locket containing a map back to Oakhaven. The map is crossed out. 'THEY KNOW' is scratched on the back.",
    },
    "bone_tooth_necklace": {
        "name": "Bone-Tooth Necklace", "defense_bonus": 1, "attack_bonus": 2,
        "value": 1250, "tier": 4, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
    },
    "resonance_warped_ring": {
        "name": "Resonance-Warped Ring", "defense_bonus": 2,
        "stat_bonus": {"int": 1}, "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "desc": "A band of crystal that absorbs light. The crystal is cracked.",
    },
    "lockpicks_of_the_damned": {
        "name": "Lockpicks of the Damned", "attack_bonus": 3,
        "value": 1250, "tier": 4, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "Shaped from the finger bones of a thief who died mid-pick. They fit every lock in the Spine.",
    },
    "deep_chaplains_rosary": {
        "name": "Deep Chaplain's Rosary", "defense_bonus": 2,
        "stat_bonus": {"wis": 1}, "value": 1300, "tier": 4, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

# ─── LOWER SPINE SET (Tier 5, Floors 41-77) ────────────────────────
LOWER_WEAPONS = {
    # Warrior
    "heart_forged_greatsword": {
        "name": "Heart-Forged Greatsword",
        "attack_bonus": 10, "damage_die": 12, "damage_bonus": 7,
        "value": 2800, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "proc": {"name": "Core Eruption", "emoji": "🤍", "die": 8, "element": "force"},
    },
    # Ranger
    "void_touched_longbow": {
        "name": "Void-Touched Longbow",
        "attack_bonus": 9, "damage_die": 10, "damage_bonus": 7,
        "value": 2700, "tier": 5, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
        "proc": {"name": "Abyssal Arrow", "emoji": "🌑", "die": 8, "element": "void"},
    },
    # Mage
    "aeridorian_spine_staff": {
        "name": "Aeridorian Spine-Staff",
        "attack_bonus": 8, "damage_die": 10, "damage_bonus": 8,
        "value": 2800, "tier": 5, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "proc": {"name": "Resonance Cascade", "emoji": "💠", "die": 8, "element": "arcane"},
    },
    # Rogue
    "elaras_betrayal_dagger": {
        "name": "Elara's Betrayal",
        "attack_bonus": 9, "damage_die": 8, "damage_bonus": 7,
        "value": 2700, "tier": 5, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "proc": {"name": "Treachery", "emoji": "🗡️", "die": 10, "element": "shadow"},
    },
    # Cleric
    "forge_masters_hammer": {
        "name": "Forge-Master's Hammer",
        "attack_bonus": 9, "damage_die": 10, "damage_bonus": 7,
        "value": 2800, "tier": 5, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Paladin"],
        "proc": {"name": "Molten Judgement", "emoji": "🔥", "die": 8, "element": "fire"},
    },
}

LOWER_ARMOR = {
    "flesh_forged_cuirass": {
        "name": "Flesh-Forged Cuirass", "defense_bonus": 12, "stat_bonus": {"str": 2}, "hp_bonus": 10,
        "value": 2800, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "desc": "Aeridorian metal fused with living sinew. It tightens when you are afraid.",
    },
    "deep_stalkers_hide": {
        "name": "Deep Stalker's Hide", "defense_bonus": 9, "stat_bonus": {"dex": 3},
        "value": 2700, "tier": 5, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
        "desc": "Skinned from a Deep Stalker. The leather still shifts color in torchlight.",
    },
    "the_vessels_mantle": {
        "name": "The Vessel's Mantle", "defense_bonus": 7, "stat_bonus": {"int": 3}, "hp_bonus": 10,
        "value": 2800, "tier": 5, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "desc": "A cloak of woven resonance. It was meant for the Elder who feeds the mountain.",
    },
    "eyeless_horrors_skin": {
        "name": "Eyeless Horror's Skin", "defense_bonus": 8, "stat_bonus": {"dex": 3},
        "value": 2700, "tier": 5, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "It screams at a frequency only the wearer can hear. You get used to it. That's the worst part.",
    },
    "core_chaplains_raiment": {
        "name": "Core Chaplain's Raiment", "defense_bonus": 10, "stat_bonus": {"wis": 3},
        "value": 2800, "tier": 5, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
        "desc": "The last chaplain abandoned his faith on Floor 62. The robes kept praying without him.",
    },
}

LOWER_HEADGEAR = {
    "heartstone_visor": {
        "name": "Heartstone Visor", "defense_bonus": 4, "stat_bonus": {"str": 1}, "hp_bonus": 5,
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "void_stalkers_cowl": {
        "name": "Void Stalker's Cowl", "defense_bonus": 3, "stat_bonus": {"dex": 2},
        "value": 2500, "tier": 5, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
    },
    "resonance_diadem_spine": {
        "name": "Crystalline Mind-Crown", "defense_bonus": 2, "stat_bonus": {"int": 2},
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "desc": "Grown from a shard of the mountain's core. It whispers solutions to problems you haven't encountered yet.",
    },
    "lurking_shadows_hood": {
        "name": "Lurking Shadow's Hood", "defense_bonus": 3, "stat_bonus": {"dex": 2},
        "value": 2500, "tier": 5, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "Woven from darkness itself. The wearer's face becomes difficult to remember.",
    },
    "core_chaplains_circlet": {
        "name": "Core Chaplain's Circlet", "defense_bonus": 3, "stat_bonus": {"wis": 2},
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

LOWER_BOOTS = {
    "heartstone_greaves": {
        "name": "Heartstone Greaves", "defense_bonus": 4, "hp_bonus": 5,
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
    },
    "abyssal_striders": {
        "name": "Abyssal Striders", "defense_bonus": 3, "stat_bonus": {"dex": 1},
        "value": 2500, "tier": 5, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
    },
    "pulse_walkers_treads": {
        "name": "Pulse-Walker's Treads", "defense_bonus": 2, "stat_bonus": {"int": 1},
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
        "desc": "Boots that step in time with the mountain's heartbeat. You cannot walk off-rhythm.",
    },
    "shadow_step_boots": {
        "name": "Shadow-Step Boots", "defense_bonus": 3, "stat_bonus": {"dex": 1},
        "value": 2500, "tier": 5, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
    },
    "core_chaplains_sandals": {
        "name": "Core Chaplain's Sandals", "defense_bonus": 3, "stat_bonus": {"wis": 1},
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
    },
}

LOWER_ACCESSORIES = {
    "tithe_collectors_signet": {
        "name": "Tithe-Collector's Signet", "defense_bonus": 2, "attack_bonus": 3,
        "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Warrior", "Paladin", "Shadowknight"],
        "desc": "A heavy gold ring bearing the seal of Oakhaven. It burns to the touch. The mountain expects a meal.",
    },
    "deep_watcher_charm": {
        "name": "Deep Watcher's Charm", "defense_bonus": 1, "attack_bonus": 3,
        "stat_bonus": {"dex": 1}, "value": 2500, "tier": 5, "droppable_only": True,
        "classes": ["Ranger", "Sniper", "Warden"],
    },
    "crystalline_focus_ring": {
        "name": "Crystalline Focus Ring", "defense_bonus": 2,
        "stat_bonus": {"int": 2}, "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Mage", "Wizard", "Invoker"],
    },
    "marrow_bite_ring": {
        "name": "Marrow-Bite Ring", "attack_bonus": 4,
        "value": 2500, "tier": 5, "droppable_only": True,
        "classes": ["Rogue", "Assassin", "Shadowblade"],
        "desc": "The band is carved from a single tooth. It bites back if you try to remove it.",
    },
    "vessels_rosary": {
        "name": "Vessel's Rosary", "defense_bonus": 3,
        "stat_bonus": {"wis": 2}, "value": 2600, "tier": 5, "droppable_only": True,
        "classes": ["Cleric", "High Priest", "Shaman"],
        "desc": "Each bead is a crystallized tear from a different Oakhaven Elder. There have been many.",
    },
}

def remove_item_block(content, key):
    """Remove a 'key': { ... }, block from the file content."""
    pattern = rf'    "{re.escape(key)}": \{{[^}}]*\}},?\n'
    return re.sub(pattern, '', content)

def format_item(key, data):
    """Format one item dict in the correct registry style."""
    lines = [f'    "{key}": {{']
    for k, v in data.items():
        if isinstance(v, str):
            # Escape quotes in string values
            escaped = v.replace('"', '\\"')
            lines.append(f'        "{k}": "{escaped}",')
        elif isinstance(v, dict):
            inner = ", ".join(f'"{ik}": {repr(iv)}' for ik, iv in v.items())
            lines.append(f'        "{k}": {{{inner}}},')
        elif isinstance(v, list):
            inner = ", ".join(f'"{x}"' if isinstance(x, str) else str(x) for x in v)
            lines.append(f'        "{k}": [{inner}],')
        elif isinstance(v, bool):
            lines.append(f'        "{k}": {v},')
        else:
            lines.append(f'        "{k}": {v},')
    lines.append('    },')
    return "\n".join(lines)

def insert_items_into_dict(content, dict_name, items):
    """Insert items right after the opening of a dict."""
    pattern = rf'({dict_name}\s*=\s*\{{)'
    match = re.search(pattern, content)
    if not match:
        print(f"ERROR: Could not find {dict_name}")
        return content
    insert_pos = match.end()
    block = "\n" + "\n".join(format_item(k, v) for k, v in items.items()) + "\n"
    return content[:insert_pos] + block + content[insert_pos:]


# ── Main ──────────────────────────────────────────────────────────
with open("utils/ttrpg/equipment_registry.py", "r") as f:
    content = f.read()

# Step 1: Remove all broken items
for key in BROKEN_KEYS:
    content = remove_item_block(content, key)

# Step 2: Insert correct items
all_weapons = {**UPPER_WEAPONS, **LOWER_WEAPONS}
all_armor = {**UPPER_ARMOR, **LOWER_ARMOR}
all_headgear = {**UPPER_HEADGEAR, **LOWER_HEADGEAR}
all_boots = {**UPPER_BOOTS, **LOWER_BOOTS}
all_accessories = {**UPPER_ACCESSORIES, **LOWER_ACCESSORIES}

content = insert_items_into_dict(content, "WEAPONS", all_weapons)
content = insert_items_into_dict(content, "ARMOR", all_armor)
content = insert_items_into_dict(content, "HEADGEAR", all_headgear)
content = insert_items_into_dict(content, "BOOTS", all_boots)
content = insert_items_into_dict(content, "ACCESSORIES", all_accessories)

with open("utils/ttrpg/equipment_registry.py", "w") as f:
    f.write(content)

print("Done. Removed broken items, inserted 50 correct items.")
