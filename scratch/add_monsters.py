import json

new_monsters = {
    # -- Zone 1: Working Tunnels --
    "blind_cave_leech": {
        "name": "Blind Cave Leech",
        "hp": 45, "attack": 8, "defense": 4,
        "xp": 35, "gil": 10, "tier": "easy",
        "desc": "It drops from the cavern ceiling without a sound, seeking the warmth of blood. It has no eyes, only hunger.",
    },
    "rust_lung_miner": {
        "name": "Rust-Lung Miner",
        "hp": 65, "attack": 10, "defense": 5,
        "xp": 45, "gil": 12, "tier": "easy",
        "desc": "A former worker of the deep tunnels. Its lungs gave out years ago, replaced by a wet, rattling cough and an endless hostility toward the living.",
    },
    "chittering_skitterer": {
        "name": "Chittering Skitterer",
        "hp": 30, "attack": 12, "defense": 3,
        "xp": 30, "gil": 8, "tier": "easy",
        "desc": "A multi-legged vermin with a hard carapace. It moves erratically, always attempting to flank its prey in the dark.",
    },
    "iron_blight_bat": {
        "name": "Iron-Blight Bat",
        "hp": 40, "attack": 11, "defense": 6,
        "xp": 40, "gil": 15, "tier": "medium",
        "desc": "Oversized and mutated by the ores of the mountain. Its bite leaves behind jagged flakes of toxic rust.",
    },
    "subterranean_prowler": {
        "name": "Subterranean Prowler",
        "hp": 85, "attack": 14, "defense": 8,
        "xp": 60, "gil": 20, "tier": "medium",
        "desc": "A sleek, pale predator adapted to complete darkness. It tracks prey by the vibrations of their heartbeat.",
    },
    "foremans_enforcer": {
        "name": "Foreman's Enforcer",
        "hp": 110, "attack": 15, "defense": 10,
        "xp": 80, "gil": 25, "tier": "medium",
        "desc": "Once tasked with keeping the miners in line, now tasked with keeping intruders out. It wields a massive, blood-stained pickaxe.",
    },

    # -- Zone 2: Bone Warrens --
    "marrow_hound": {
        "name": "Marrow Hound",
        "hp": 70, "attack": 13, "defense": 7,
        "xp": 50, "gil": 15, "tier": "medium",
        "desc": "A feral canine assembled from mismatched bones. It doesn't bark; it only clatters as it charges.",
    },
    "crypt_warden": {
        "name": "Crypt Warden",
        "hp": 130, "attack": 16, "defense": 12,
        "xp": 90, "gil": 30, "tier": "medium",
        "desc": "A skeletal guardian adorned in rusted armor. Its eye sockets burn with a pale, cold flame.",
    },
    "whispering_skull_swarm": {
        "name": "Whispering Skull-Swarm",
        "hp": 80, "attack": 12, "defense": 15,
        "xp": 70, "gil": 20, "tier": "hard",
        "desc": "A dozen animated skulls orbiting each other, chattering incessantly. The noise is disorienting and maddening.",
    },
    "ash_wraith": {
        "name": "Ash Wraith",
        "hp": 90, "attack": 18, "defense": 8,
        "xp": 100, "gil": 25, "tier": "hard",
        "desc": "The bitter remains of a cremated soul. It phases through solid bone, leaving a trail of choking grey dust.",
    },
    "ossified_terror": {
        "name": "Ossified Terror",
        "hp": 150, "attack": 17, "defense": 14,
        "xp": 120, "gil": 35, "tier": "hard",
        "desc": "A hulking amalgamation of ribcages and femurs woven together by dark magic. It crushes everything in its path.",
    },
    "entombed_scholar": {
        "name": "Entombed Scholar",
        "hp": 110, "attack": 20, "defense": 10,
        "xp": 150, "gil": 40, "tier": "deadly",
        "desc": "It studied the dark resonance of these catacombs until it became part of them. It casts spells of pure, focused despair.",
    },

    # -- Zone 3: Sunken Forge --
    "slag_crawler_spine": {
        "name": "Slag-Crawler",
        "hp": 100, "attack": 15, "defense": 15,
        "xp": 110, "gil": 25, "tier": "hard",
        "desc": "A crustacean-like entity with a shell made of hardened slag. It spits globs of superheated metal.",
    },
    "ignited_sentinel": {
        "name": "Ignited Sentinel",
        "hp": 140, "attack": 18, "defense": 16,
        "xp": 140, "gil": 35, "tier": "hard",
        "desc": "An Aeridorian construct permanently set on fire. The heat radiating from it warps the air and scorches the ground.",
    },
    "smoldering_ash_walker": {
        "name": "Smoldering Ash-Walker",
        "hp": 120, "attack": 19, "defense": 12,
        "xp": 130, "gil": 30, "tier": "hard",
        "desc": "A humanoid figure composed entirely of burning embers. Its footsteps leave permanent scorch marks.",
    },
    "molten_slime": {
        "name": "Molten Slime",
        "hp": 160, "attack": 14, "defense": 8,
        "xp": 150, "gil": 40, "tier": "hard",
        "desc": "A blob of liquid fire that absorbed industrial runoff. Touching it is a very bad idea.",
    },
    "brass_plated_hound": {
        "name": "Brass-Plated Hound",
        "hp": 130, "attack": 21, "defense": 14,
        "xp": 160, "gil": 45, "tier": "deadly",
        "desc": "A mechanical beast driven by an internal furnace. It vents steam when angry, which is always.",
    },
    "forge_fire_wisp": {
        "name": "Forge-Fire Wisp",
        "hp": 80, "attack": 25, "defense": 10,
        "xp": 180, "gil": 50, "tier": "deadly",
        "desc": "A concentrated spark of Aeridorian forge-magic. Extremely fragile, but capable of incinerating a heavily armored knight.",
    },

    # -- Zone 4: The Deep Dark --
    "void_touched_weaver": {
        "name": "Void-Touched Weaver",
        "hp": 150, "attack": 22, "defense": 16,
        "xp": 200, "gil": 55, "tier": "hard",
        "desc": "A massive arachnid corrupted by the deep resonance. Its webs don't just trap the body; they trap the mind.",
    },
    "deep_stalker": {
        "name": "Deep Stalker",
        "hp": 180, "attack": 24, "defense": 15,
        "xp": 220, "gil": 60, "tier": "hard",
        "desc": "Tall, gangly, and utterly silent. You only know it's there when you feel its cold breath on your neck.",
    },
    "abyssal_leech_spine": {
        "name": "Abyssal Leech",
        "hp": 120, "attack": 20, "defense": 10,
        "xp": 190, "gil": 50, "tier": "hard",
        "desc": "A monstrous annelid that thrives in the absolute dark. Its bite drains both blood and magical energy.",
    },
    "eyeless_horror": {
        "name": "Eyeless Horror",
        "hp": 200, "attack": 26, "defense": 18,
        "xp": 300, "gil": 75, "tier": "deadly",
        "desc": "A hulking mass of flesh and teeth. It relies entirely on echolocation, shrieking constantly to map its surroundings.",
    },
    "resonance_warped_troll": {
        "name": "Resonance-Warped Troll",
        "hp": 250, "attack": 25, "defense": 20,
        "xp": 350, "gil": 80, "tier": "deadly",
        "desc": "A cave troll that wandered too deep. Crystals jut from its skin, granting it terrible magical resistance but driving it insane.",
    },
    "the_lurking_shadow": {
        "name": "The Lurking Shadow",
        "hp": 170, "attack": 28, "defense": 22,
        "xp": 400, "gil": 100, "tier": "deadly",
        "desc": "A predator made of pure darkness. It snuffs out torches merely by existing near them.",
    },

    # -- Zone 5: Heart of the Mountain --
    "pulse_walker": {
        "name": "Pulse-Walker",
        "hp": 220, "attack": 29, "defense": 24,
        "xp": 500, "gil": 120, "tier": "deadly",
        "desc": "An entity animated by the heartbeat of the mountain. Its attacks strike in perfect rhythm with the pulsing walls.",
    },
    "crystalline_abomination": {
        "name": "Crystalline Abomination",
        "hp": 300, "attack": 27, "defense": 28,
        "xp": 600, "gil": 150, "tier": "deadly",
        "desc": "A jagged horror of pure resonance crystal. It shatters weapons that strike it and hums with a deafening frequency.",
    },
    "flesh_forged_construct": {
        "name": "Flesh-Forged Construct",
        "hp": 350, "attack": 30, "defense": 25,
        "xp": 750, "gil": 200, "tier": "deadly",
        "desc": "Aeridorian machinery fused with organic matter. The horrible culmination of the mountain's long digestion.",
    },
    "the_mountains_white_blood": {
        "name": "The Mountain's White Blood",
        "hp": 400, "attack": 32, "defense": 20,
        "xp": 900, "gil": 250, "tier": "deadly",
        "desc": "A massive, rolling wave of corrosive white fluid that functions as the mountain's immune response.",
    },
    "aeridorian_echo": {
        "name": "Aeridorian Echo",
        "hp": 280, "attack": 35, "defense": 22,
        "xp": 850, "gil": 220, "tier": "deadly",
        "desc": "A ghostly projection of a long-dead Aeridorian geomancer. It wields ancient, forgotten magic with perfect precision.",
    },
    "core_warped_behemoth": {
        "name": "Core-Warped Behemoth",
        "hp": 450, "attack": 38, "defense": 30,
        "xp": 1200, "gil": 300, "tier": "deadly",
        "desc": "A legendary beast entirely consumed and puppeteered by the mountain's core. Its eyes are empty white crystals.",
    }
}

output = "    # ══════════════════════════════════════════════════════════════\n"
output += "    # NEW SPINE DUNGEON NORMAL MOBS\n"
output += "    # ══════════════════════════════════════════════════════════════\n"
for key, data in new_monsters.items():
    output += f'    "{key}": {{\n'
    for k, v in data.items():
        if isinstance(v, str):
            output += f'        "{k}": "{v}",\n'
        else:
            output += f'        "{k}": {v},\n'
    output += '    },\n'

with open("scratch/new_monsters.py", "w") as f:
    f.write(output)
