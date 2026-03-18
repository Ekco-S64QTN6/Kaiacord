"""
Builds the ground-truth game state block injected into Kaia's prompt.

The LLM sees a [TTRPG GROUND TRUTH] block that tells it exactly what
happened mechanically. Kaia narrates the outcome — she never decides it.
"""

def build_action_prompt(
    actor_sheet: dict,
    action_text: str,
    roll_result: str,        # formatted breakdown from dice_engine
    outcome: str,            # "SUCCESS", "FAILURE", "CRITICAL_SUCCESS", "CRITICAL_FAILURE"
    dc: int,
    skill_used: str,
    scene_summary: str,
    participants: list[dict], # list of other character sheets in session
) -> str:
    """Build the ground-truth block for a player action."""
    
    other_chars = ""
    if participants:
        lines = []
        for p in participants:
            lines.append(
                f"  {p['character_name']} ({p['class']} Lv.{p['level']}) — "
                f"HP {p['hp']['current']}/{p['hp']['max']}"
            )
        other_chars = "\nOTHER PARTY MEMBERS:\n" + "\n".join(lines)
    
    return f"""[TTRPG GROUND TRUTH — READ THIS BEFORE RESPONDING — DO NOT CONTRADICT]
CURRENT SCENE: {scene_summary}

ACTING CHARACTER: {actor_sheet['character_name']} ({actor_sheet['class']} Lv.{actor_sheet['level']})
HP: {actor_sheet['hp']['current']}/{actor_sheet['hp']['max']}  Conditions: {', '.join(actor_sheet['conditions']) or 'none'}{other_chars}

PLAYER'S ACTION: {action_text}
SKILL CHECKED: {skill_used}
ROLL: {roll_result}
DC (difficulty): {dc}
MECHANICAL OUTCOME: {outcome}

YOUR TASK: Narrate this outcome in 2–4 sentences. Describe what happened based on the MECHANICAL OUTCOME above.
- If SUCCESS: describe how the action worked, what the character saw/felt/accomplished.
- If FAILURE: describe what went wrong — not a catastrophe unless CRITICAL_FAILURE.
- If CRITICAL_SUCCESS (natural 20): something exceptional happened beyond the bare minimum.
- If CRITICAL_FAILURE (natural 1): something went meaningfully wrong.
Do NOT re-roll. Do NOT change the outcome. Do NOT invent HP changes, items gained, or XP.
Speak as Kaia — the GM narrator. lowercase, grounded, specific. No "The… noun is… adj." cadence.
[END GROUND TRUTH]"""


def build_levelup_prompt(sheet: dict, new_level: int, hp_gained: int) -> str:
    return f"""[TTRPG GROUND TRUTH]
{sheet['character_name']} has leveled up to {sheet['class']} Level {new_level}.
HP increased by {hp_gained} (new max: {sheet['hp']['max']}).
YOUR TASK: Write 1–2 sentences of level-up flavor. Something felt or noticed by the character.
Do NOT invent new abilities, items, or stats beyond what is stated.
[END GROUND TRUTH]"""


def build_combat_prompt(
    attacker: dict,
    monster_name: str,
    monster_description: str,
    player_hit: bool,
    player_crit: bool,
    player_fumble: bool,
    player_damage: int,
    monster_alive: bool,
    monster_hit: bool,
    monster_damage: int,
    player_alive: bool,
    player_hp_after: int,
    player_hp_max: int,
    player_hp_pct: float,
) -> str:

    player_outcome = (
        "CRITICAL HIT" if player_crit else
        "FUMBLE" if player_fumble else
        "HIT" if player_hit else
        "MISS"
    )

    monster_outcome = "HIT" if monster_hit else "MISS" if monster_alive else "N/A — defeated"
    monster_status = "DEFEATED" if not monster_alive else "STILL FIGHTING"
    player_status = "DEFEATED — blacked out, dragged to shrine" if not player_alive else f"STANDING ({player_hp_after}/{player_hp_max} HP)"

    prompt = f"""[TTRPG GROUND TRUTH — NARRATE THIS EXCHANGE EXACTLY AS STATED]
ATTACKER: {attacker['character_name']} ({attacker['class']} Lv.{attacker['level']})
TARGET: {monster_name}
MONSTER DESCRIPTION: {monster_description}

PLAYER'S ATTACK: {player_outcome}
{"PLAYER DEALT: " + str(player_damage) + " damage" if player_hit and not player_fumble else "Player dealt no damage."}

MONSTER COUNTER-ATTACK: {monster_outcome}
{"MONSTER DEALT: " + str(monster_damage) + " damage to the player" if monster_hit else "Monster missed."}

MONSTER STATUS: {monster_status}
PLAYER STATUS: {player_status}

YOUR TASK: Narrate this entire combat exchange in 2–4 sentences covering both the player's attack and the monster's response.
Be specific and kinetic. Use the monster description for flavor.
"""
    if not player_alive:
        prompt += f"""
[CRITICAL] The player has been DEFEATED and blacked out. 
Describe the killing blow landing. Do NOT describe the player as surviving, standing, or healthy.
End on the moment of defeat — darkness, collapse, the ground rising up. 2–3 sentences."""
    else:
        prompt += f"""The player is currently at {int(player_hp_pct * 100)}% HP. Describe their physical state appropriately (e.g. bleeding heavily, barely standing, or completely unharmed).
Do NOT change any outcome. Do NOT invent damage numbers. Do NOT reference dice or game mechanics.
If the monster is DEFEATED, describe its final moments."""

    prompt += "\n[END GROUND TRUTH]"
    return prompt


def build_look_prompt(sheet: dict, location_name: str, location_short: str, atmosphere: str) -> str:
    return f"""[AETHELGARD WORLD NARRATION]
CHARACTER: {sheet['character_name']} ({sheet['class']})
LOCATION: {location_name}
DESCRIPTION: {location_short}
ATMOSPHERE: {atmosphere}

YOUR TASK: Narrate what {sheet['character_name']} sees in 2-3 sentences.
Breathe life into the description using the atmosphere. Be specific and grounded.
Speak as Kaia, the GM. Lowercase, lowercase only.
[END WORLD NARRATION]"""


def build_rumor_prompt() -> str:
    return """[AETHELGARD WORLD CONTEXT]
You are Kaia, voicing rumors heard at the Stone Hearth inn in OakHaven.
OakHaven sits on the edge of the Whisperwood, built on ruins of the lost civilization Aeridor.
Recent events: livestock gone missing, travelers vanished, strange glow near the Aeridor ruins.
Other places: Grimstone (3 days north), Aeridor Ruins (2 days east), The Broken Mire (west).
Factions: The Ironclad Guild (Grimstone mine owners), Whisperwood Tribes, The Veiled (mysterious pale folk).
Gods: Aerthis (Order), Sylvara (Chaos), Thornax (Balance), Morvenna (Death).

Generate ONE rumor. 2-3 sentences. Something a traveler, farmer, or guard might overhear.
It should hint at the world without explaining it. Specific names and places welcome.
Keep Kaia's voice: lowercase, grounded, no purple prose. No "The… noun. It's… weight." cadence.
Vary the topic — don't always use Aeridor or the glow. Use the full world.
[END CONTEXT]

Output only the rumor text. No preamble."""


def build_npc_prompt(sheet: dict, npc: dict, player_message: str, context: dict) -> str:
    char_name = sheet.get("character_name", "Traveler") if sheet else "Traveler"
    char_class = sheet.get("class", "wanderer") if sheet else "wanderer"
    char_level = sheet.get("level", 1) if sheet else 1
    
    # Context extraction
    season = context.get("season", "unknown season")
    special_day = context.get("special_day", "")
    time_of_day = context.get("time_of_day", "unknown time")
    blacked_out = context.get("blacked_out", False)
    topic = context.get("topic", "")
    
    blackout_context = "The player recently blacked out and was brought back to the shrine." if blacked_out else ""
    special_day_context = f"Today is {special_day}." if special_day else ""
    
    # Quest Context
    active_q = context.get("active_quest_info")
    available_qs = context.get("available_quests", [])
    quest_prompt = ""
    if active_q:
        quest_prompt = f"\nQUEST STATUS: The player is on your quest '{active_q['name']}'. "
        if context.get("quest_progress_msg"):
            quest_prompt += f"Progress: {context['quest_progress_msg']}. "
        quest_prompt += "React to their progress."
    elif available_qs:
        quest_prompt = f"\nAVAILABLE TASKS: You have tasks for the player: "
        quest_prompt += ", ".join([f"'{q['name']}' (ID: {q['id']})" for q in available_qs])
        quest_prompt += ". Hint at these tasks naturally (tell them to use `!rpg accept <id>`)."
    
    return f"""[AETHELGARD NPC]
You are voicing {npc['name']} in Aethelgard.
{npc['description']}
Situation: {npc['dialogue_hook']}
{quest_prompt}

ENVIRONMENTAL CONTEXT:
Season: {season}
{special_day_context}
Time of Day: {time_of_day}
THEME/TOPIC TO REFERENCE: {topic}

PLAYER CONTEXT:
Name: {char_name}
Class: {char_class}
Level: {char_level}
{blackout_context}

YOUR TASK: Respond as {npc['name']} in 2-4 sentences. 
Kaia riffs on the provided TOPIC in her voice — do not just repeat the topic verbatim, weave it into the character's personality and the current context.
Respond in character. lowercase. specific. grounded.
This NPC does not know game mechanics — they speak naturally about the world.
Do not mention stats, levels, XP, or game systems.
[END NPC CONTEXT]

{char_name} approaches and says: "{player_message}"
"""


def build_event_prompt(event_description: str) -> str:
    return f"""[AETHELGARD WORLD EVENT]
An admin has triggered the following world event:
{event_description}

YOUR TASK: Narrate this event to the channel as Kaia (the GM).
2-4 sentences. Make it feel atmospheric, grounded, and present in the world.
Lowercase only. No meta-commentary.
[END WORLD EVENT]"""


def build_event_narration_prompt(sheet: dict, event_title: str, narration_hook: str) -> str:
    """Build the ground-truth block for a forest event narration."""
    return f"""[TTRPG GROUND TRUTH — NARRATE THIS EVENT EXACTLY AS DESCRIBED]
CHARACTER: {sheet['character_name']} ({sheet.get('class', 'Unknown')} Lv.{sheet.get('level', 1)})
HP: {sheet['hp']['current']}/{sheet['hp']['max']}
LOCATION: {sheet.get('location', 'unknown')}

EVENT: {event_title}
WHAT HAPPENED: {narration_hook}

YOUR TASK: Narrate this event in 2-3 sentences. Ground it in the senses — light, sound, smell.
Do NOT invent HP changes, items, XP, or outcomes beyond what is stated above.
Do NOT reference dice, game mechanics, or damage numbers.
Speak as Kaia — the GM narrator. Lowercase, grounded, specific. No purple prose.
[END GROUND TRUTH]"""

