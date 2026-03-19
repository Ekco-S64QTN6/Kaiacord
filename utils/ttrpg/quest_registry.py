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
        "tasks": ["kill_road_bandit", "talk_maren"],
        "rewards": {"xp": 200, "gil": 50, "recipe": "potion"},
        "completion_msg": "Sister Maren's eyes light up. 'The Silverleaf! Now I can finish the brew. Bless you.'",
    }
}

def get_quest(quest_id):
    return QUESTS.get(quest_id)

def get_npc_quests(npc_id):
    """Returns a list of quests offered by a specific NPC."""
    return [q for q in QUESTS.values() if q["npc"] == npc_id]
