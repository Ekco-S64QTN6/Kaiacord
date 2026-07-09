"""
Quest Registry - Definitions and logic for Oakhaven Quests
"""

QUESTS = {
    "arrival": {
        "id": "arrival",
        "name": "A Stranger in the Mud",
        "npc": "elara",
        "description": "Elder Elara wants you to introduce yourself to the town. Visit Mira at the Stone Hearth and Hemlock at the shop.",
        "requirements": {"level": 1},
        "tasks": ["talk_barkeep", "talk_hemlock", "talk_elara"],
        "rewards": {"xp": 50, "gil": 20},
        "completion_msg": "Elder Elara nods approvingly. 'Small steps, adventurer. You're part of Oakhaven now.'",
    },
    "whisperwood_scout": {
        "id": "whisperwood_scout",
        "name": "The Darkening Woods",
        "npc": "guard",
        "description": "The Watchtower guards are worried about movement in the Whisperwood Deep. Scout the area by hunting there once.",
        "requirements": {"level": 3},
        "tasks": ["hunt_whisperwood_deep", "talk_guard"],
        "rewards": {"xp": 150, "gil": 100, "item": "lucky_charm"},
        "completion_msg": "The guard takes your report. 'Deep movement, eh? We'll double the patrols. Take this for your trouble.'",
    },
    "maren_herbs": {
        "id": "maren_herbs",
        "name": "Sister Maren's Request",
        "npc": "maren",
        "description": "Sister Maren needs rare herbs found only near the Trade Road. Defeat a 'Road Bandit' to recover her stolen supplies.",
        "requirements": {"level": 4},
        "tasks": ["kill_bandit", "talk_maren"],
        "rewards": {"xp": 200, "gil": 50, "recipe": "potion", "item": "silverleaf"},
        "completion_msg": "Sister Maren's eyes light up. 'The Silverleaf! Now I can finish the brew. Bless you.'",
    },
    "grimstone_relic": {
        "id": "grimstone_relic",
        "name": "The Aeridorian Signal",
        "npc": "elara",
        "description": "Elder Elara has detected a pulse from deep below Oakhaven — Aeridorian constructs are waking up. Clear a dungeon and report back what you find.",
        "requirements": {"level": 5},
        "tasks": ["complete_dungeon", "talk_elara"],
        "rewards": {"xp": 500, "gil": 200, "item": "lightstone"},
        "completion_msg": "Elara listens to your account without expression. 'The constructs are active again. That pulse was not random. Something triggered them.' She pauses. 'Keep the lightstone. You'll need it more than I will.'",
    },
    "deep_hunt": {
        "id": "deep_hunt",
        "name": "What Sleeps Beneath",
        "npc": "guard",
        "description": "The Watchtower has lost contact with a patrol in the Whisperwood Deep. Something powerful took them. Find and kill the creatures responsible — a Frost Wolf and an Owlbear.",
        "requirements": {"level": 7},
        "tasks": ["kill_frost_wolf", "kill_owlbear", "talk_guard"],
        "rewards": {"xp": 1200, "gil": 350, "item": "ironbark_tonic"},
        "completion_msg": "The guard stares at the blood on your gear. 'You found them, didn't you. What was left of them.' A long silence. 'The Watchtower owes you a debt. This doesn't cover it, but it's what we have.'",
    },

    "silent_ones": {
        "id": "silent_ones",
        "name": "The Final Silence",
        "npc": "elara",
        "description": "The Shrine of the Silent Ones has gone dark. Elder Elara believes the seal is failing. Pray at the Shrine, then seek out a dungeon and defeat its boss to purge the corrupted essence.",
        "requirements": {"level": 9},
        "tasks": ["pray_shrine", "complete_dungeon", "talk_elara"],
        "rewards": {"xp": 1500, "gil": 500, "item": "amulet_health"},
        "completion_msg": "Elara is waiting in the square when you return. She doesn't ask what you saw in the dark. 'The seal held. This time.' She presses something cold and heavy into your hand. 'The Silent Ones left this for whoever came back. Not everyone does.'",
    },
    "aeridor_remnant": {
        "id": "aeridor_remnant",
        "name": "The Waking Metal",
        "npc": "elara",
        "description": "An Aeridorian Iron Golem has broken the perimeter of the ruins. Destroy it before it reaches the treeline.",
        "requirements": {"level": 11},
        "tasks": ["kill_iron_golem", "talk_elara"],
        "rewards": {"xp": 2500, "gil": 800, "item": "void_band"},
        "completion_msg": "Elara inspects the metallic plating you brought back. 'They are learning. Or remembering. I am not sure which is worse.'",
    },
    "shadow_incursion": {
        "id": "shadow_incursion",
        "name": "The Darkening",
        "npc": "guard",
        "description": "The Watchtower reports unnatural cold from the Deepwood. A Shadow Lich is massing forces. End it.",
        "requirements": {"level": 13},
        "tasks": ["kill_shadow_lich", "talk_guard"],
        "rewards": {"xp": 3500, "gil": 1500, "item": "mox_pearl"},
        "completion_msg": "The guard shivers despite the sun. 'We saw the shadows retreat. Oakhaven owes you its life today.'",
    },
    "the_last_guardian": {
        "id": "the_last_guardian",
        "name": "The Last Guardian",
        "npc": "elara",
        "description": "The heart of the Aeridor Ruins has opened. We cannot wait any longer. Go in. Do not come out until it is quiet.",
        "requirements": {"level": 15},
        "tasks": ["complete_dungeon", "talk_elara"],
        "rewards": {"xp": 5000, "gil": 5000, "item": "the_end"},
        "completion_msg": "Elder Elara bows her head. 'It is done. The bones of Aeridor can finally rest. And so can we.'",
    },
    "merchant_gambit": {
        "id": "merchant_gambit",
        "name": "The Merchant's Gambit",
        "npc": "pell",
        "description": "Pell needs an escort for a cargo shipment through bandit territory. Defeat a 'Road Bandit' to secure the route.",
        "requirements": {"level": 8},
        "tasks": ["kill_bandit", "talk_pell"],
        "rewards": {"xp": 800, "gil": 300, "item": "potion_standard"},
        "completion_msg": "Pell grins. 'Cargo arrived safe and sound. Hemlock's going to be pleased. Here's your cut.'",
    },
    "grimstone_shadows": {
        "id": "grimstone_shadows",
        "name": "Shadows Over Grimstone",
        "npc": "valdric",
        "description": "Rook reports constructs breaching the mine perimeter. Clear a dungeon and report back.",
        "requirements": {"level": 9},
        "tasks": ["complete_dungeon", "talk_valdric"],
        "rewards": {"xp": 1000, "gil": 400, "item": "ironbark_tonic"},
        "completion_msg": "Valdric nods approvingly. 'The constructs collapsed back into the dark. Excellent work, scout.'",
    },
    "tithe_collector": {
        "id": "tithe_collector",
        "name": "The Tithe Collector",
        "npc": "elara",
        "description": "A mysterious figure is collecting 'tithes' from travelers. Track and defeat the 'Tithe Collector' in the ruins.",
        "requirements": {"level": 10},
        "tasks": ["kill_tithe_collector", "talk_elara"],
        "rewards": {"xp": 1400, "gil": 600, "item": "void_band"},
        "completion_msg": "Elara listens to your report. 'The tithes have ceased. But what they were building remains a dark mystery.'",
    },
}

def get_quest(quest_id):
    return QUESTS.get(quest_id)

def get_npc_quests(npc_id):
    """Returns a list of quests offered by a specific NPC."""
    return [q for q in QUESTS.values() if q["npc"] == npc_id]
