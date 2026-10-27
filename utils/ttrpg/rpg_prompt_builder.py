"""
Builds the ground-truth game state block injected into Kaia's prompt.

The LLM sees a [TTRPG GROUND TRUTH] block that tells it exactly what
happened mechanically. Kaia narrates the outcome — she never decides it.
"""

# Injected between persona and prompt in narration system messages.
# Overrides Kaia's casual Discord persona for TTRPG narration mode.
TTRPG_NARRATOR_OVERRIDE = (
    "\n\n[TTRPG NARRATION MODE — ACTIVE]\n"
    "You are the GM narrator of Aethelgard. Override your conversational persona for this response.\n"
    "IGNORE everything above about Kaia's apartment, computers, workspace, coffee, and personal life. "
    "You are NOT Kaia the hacker right now. You are ONLY the narrator of a medieval fantasy world.\n"
    "Rules: third person past tense only. No first-person 'I'. No casual language, no exclamation marks.\n"
    "SETTING: Aethelgard is a MEDIEVAL FANTASY world. Pre-industrial. No electricity, no neon, no plastic, "
    "no modern technology, no sci-fi elements. Materials: stone, wood, iron, leather, cloth, bone, glass, "
    "candlelight, torchlight, hearth-fire. Think 13th century with magic.\n"
    "Style: grounded, specific, literary. Think Ursula K. Le Guin. Lowercase throughout.\n"
    "Do not narrate your own feelings or opinions. Narrate what happened to the character.\n"
    "[END OVERRIDE]\n\n"
)


def build_look_prompt(sheet: dict, location_name: str, location_short: str, atmosphere: str) -> str:
    return f"""[AETHELGARD WORLD NARRATION]
WORLD SETTING: Medieval fantasy. No modern technology, no electricity, no neon, no plastic.
Light sources: candles, torches, hearth-fire, moonlight, magical glow. Materials: stone, wood, iron, leather.
CHARACTER: {sheet['character_name']} ({sheet['class']})
LOCATION: {location_name}
DESCRIPTION: {location_short}
ATMOSPHERE: {atmosphere}

YOUR TASK: Narrate what {sheet['character_name']} sees in 2-3 sentences.
Breathe life into the description using the atmosphere. Be specific and grounded.
Speak as Kaia, the GM. Lowercase, lowercase only.
[END WORLD NARRATION]"""


RUMOR_SEED_TOPICS = [
    "the Silverstream running black near Riverbend",
    "strange coins turning up in Oakhaven",
    "Elara's locked door on the solstice",
    "the Whisperwood boundary marker found in the wrong place",
    "the Silvani buying out Hemlock's antidote stock",
    "guild wagons on the Trade Road at odd hours",
    "the extra rope the watchtower guards ordered",
    "flowers left at Elara's door anonymously",
    "the clock in Hemlock's store keeping better time than it should",
    "men returning from the ruins physically unharmed but wrong",
    "a lost Aeridorian verse about three crowns and a gate in the shadow",
    "the ruins humming low at midnight",
    "the Pale King breaking lines in Tricklebrook Pond",
    "creatures coming out of the ruins before sunrise"
]


def build_rumor_prompt() -> str:
    import secrets
    seed = secrets.choice(RUMOR_SEED_TOPICS)
    return f"""[AETHELGARD WORLD CONTEXT]
WORLD SETTING: Medieval fantasy. No modern technology. Pre-industrial.
You are Kaia, voicing rumors heard at the Stone Hearth inn in OakHaven.
OakHaven sits on the edge of the Whisperwood, built on ruins of the lost civilization Aeridor.
Recent events: livestock gone missing, travelers vanished, strange glow near the Aeridor ruins.
Other places: Grimstone (3 days north), Aeridor Ruins (2 days east), The Broken Mire (west).
Factions: The Ironclad Guild (Grimstone mine owners), Whisperwood Tribes, The Veiled (mysterious pale folk).
Gods: Aerthis (Order), Sylvara (Chaos), Thornax (Balance), Morvenna (Death).

Generate ONE rumor. 2-3 sentences. Something a traveler, farmer, or guard might overhear.
The rumor MUST reference or riff on this specific topic: "{seed}".
Keep Kaia's voice: lowercase, grounded, no purple prose. No "The… noun. It's… weight." cadence.
[END CONTEXT]

Output only the rumor text. No preamble."""


def _cha_npc_line(context: dict) -> str:
    """Return a CHA-influence line for NPC prompts."""
    cha_mod = context.get("cha_mod", 0)
    if cha_mod >= 3:
        return "CHARISMA NOTE: This player is extremely charismatic. The NPC is warm, trusting, and may share extra information or offer a small favor."
    elif cha_mod >= 1:
        return "CHARISMA NOTE: This player is charming. The NPC is friendly and forthcoming."
    elif cha_mod <= -2:
        return "CHARISMA NOTE: This player is socially awkward. The NPC is curt and less forthcoming."
    return ""


def build_npc_prompt(sheet: dict, npc: dict, player_message: str, context: dict) -> str:
    char_name = sheet.get("character_name", "Traveler") if sheet else "Traveler"
    char_class = sheet.get("class", "wanderer") if sheet else "wanderer"
    char_level = sheet.get("level", 1) if sheet else 1
    
    from utils.ttrpg.pantheon import get_class_deity_name
    deity_name = get_class_deity_name(char_class) if sheet else "none"

    # Context extraction
    season = context.get("season", "unknown season")
    special_day = context.get("special_day", "")
    time_of_day = context.get("time_of_day", "unknown time")
    blacked_out = context.get("blacked_out", False)
    topic = context.get("topic", "")
    
    blackout_context = "The player recently blacked out and was brought back to the shrine." if blacked_out else ""
    special_day_context = f"Today is {special_day}." if special_day else ""
    
    # Quest Context
    active_qs = context.get("active_quests_info", [])
    available_qs = context.get("available_quests", [])
    quest_prompt = ""
    if active_qs:
        quest_prompt = "\nQUEST STATUS: The player is currently on your quests:\n"
        for i, q in enumerate(active_qs):
            prog = context.get("quest_progress_msgs", [])
            prog_str = next((p for p in prog if q["name"] in p), "No progress yet")
            quest_prompt += f"- '{q['name']}': {q.get('description', '')} (Progress: {prog_str})\n"
        quest_prompt += "React to their progress based on the quest details."
    elif available_qs:
        quest_prompt = f"\nAVAILABLE TASKS: You have tasks for the player: "
        quest_prompt += ", ".join([f"'{q['name']}' ({q.get('description', '')})" for q in available_qs])
        quest_prompt += ". Hint at these tasks naturally and give them the information they need to start."
    
    if npc.get("role") == "bard" or "Caelindra" in npc.get("name", ""):
        return f"""[AETHELGARD NPC: THE BARD]
WORLD SETTING: Medieval fantasy. No modern technology. This NPC lives in a pre-industrial world.
You are voicing {npc['name']} in Aethelgard.
{npc['description']}
Situation: {npc['dialogue_hook']}

ENVIRONMENTAL CONTEXT:
Season: {season}
{special_day_context}
Time of Day: {time_of_day}

TOPIC TO SING ABOUT:
{topic}

PLAYER CONTEXT:
Name: {char_name}
Class: {char_class}
Level: {char_level}
Deity Patron: {deity_name}
{blackout_context}

YOUR TASK: The player wants to hear you perform. Respond as {npc['name']}.
Weave the TOPIC into a short, moody tavern song or poem (4-6 lines). 
If specific names/events are in the topic, ensure they are mentioned in the lyrics.

FORMAT RULES:
- Narrate {npc['name']}'s actions and reactions in THIRD-PERSON LIMITED. "Caelindra doesn't stop playing." NOT "I don't stop playing."
- Dialogue and song lyrics are delivered in first-person by the character.
- NEVER use parenthetical stage directions like (I shift slightly) or (she looks up). Write it as prose instead.
- lowercase throughout. specific. grounded.
[END NPC CONTEXT]

{char_name} approaches and says: "{player_message}"
"""

    return f"""[AETHELGARD NPC]
WORLD SETTING: Medieval fantasy. No modern technology. This NPC lives in a pre-industrial world.
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
Deity Patron: {deity_name}
{_cha_npc_line(context)}
{blackout_context}

YOUR TASK: Respond as {npc['name']} in 2-4 sentences. 
Kaia riffs on the provided TOPIC in her voice — do not just repeat the topic verbatim, weave it into the character's personality and the current context.
Respond in character. lowercase. specific. grounded.
This NPC does not know game mechanics — they speak naturally about the world.
Do not mention stats, levels, XP, or game systems.

FORMAT RULES:
- Narrate the character's physical actions in THIRD-PERSON LIMITED as the GM (e.g., "{npc['name']} shifts in the shadows," NOT "I shift in the shadows").
- Only spoken dialogue should be delivered in first-person by the character.
[END NPC CONTEXT]

{char_name} approaches and says: "{player_message}"
"""


def build_event_prompt(event_description: str) -> str:
    return f"""[AETHELGARD WORLD EVENT]
WORLD SETTING: Medieval fantasy. No modern technology, no electricity, no neon, no plastic.
An admin has triggered the following world event:
{event_description}

YOUR TASK: Narrate this event to the channel as Kaia (the GM).
2-4 sentences. Make it feel atmospheric, grounded, and present in the world.
Lowercase only. No meta-commentary.
[END WORLD EVENT]"""


def _first_sentences(text: str, limit: int = 320) -> str:
    """A monster's description, cut at a sentence end rather than mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:end + 1] if end > 0 else cut.rsplit(" ", 1)[0] + "…"


def build_outing_summary_prompt(sheet: dict, outing: dict, reason: str) -> str:
    """Ground truth for one paragraph about a whole trip out (utils/ttrpg/outing.py):
    every fight and event since the player set out, told once when they come back."""
    from utils.core import pronouns
    from utils.ttrpg.world import LOCATION_DATA
    char_name = sheet.get("character_name", "The adventurer")
    char_class = sheet.get("advanced_class") or sheet.get("class", "adventurer")
    zones = [LOCATION_DATA.get(z, {}).get("name", z.replace("_", " ")) for z in outing.get("zones", [])]
    fights = outing.get("fights", [])
    by_monster: dict = {}
    for f in fights:
        m = by_monster.setdefault(f["monster"], {"n": 0, "won": 0, "close": 0, "clean": 0, "crits": 0,
                                                 "desc": f.get("desc", "")})
        m["n"] += 1
        m["won"] += f["won"]
        m["close"] += f["taken"] >= max(1, f["dealt"]) * 0.6
        m["clean"] += bool(f["won"] and not f["taken"])
        m["crits"] += f.get("crits", 0)
    fight_lines = []
    for name, m in sorted(by_monster.items(), key=lambda kv: -kv[1]["n"]):
        feel = [f"{m['close']} close call(s)" if m["close"] else "",
                f"{m['clean']} without a scratch" if m["clean"] else "",
                f"{m['crits']} lucky strike(s)" if m["crits"] else ""]
        line = f"  - {name}: fought {m['n']}x, won {m['won']}" + "".join(f", {x}" for x in feel if x)
        desc = _first_sentences(m["desc"])
        fight_lines.append(line + (f"\n    DESCRIPTION: {desc}" if desc else ""))
    hardest = max(fights, key=lambda f: f["taken"], default=None)
    daily_summary = bool(outing.get("daily_summary"))
    died = any(f.get("died") for f in fights)
    if daily_summary and died:
        facts.append("KNOCKED OUT DURING THE DAY: the character recovered or was brought back; this was not necessarily the final outcome.")
    loot = outing.get("loot", [])
    levels = outing.get("levels", [])
    notes = outing.get("notes", {})
    hp = sheet.get("hp") or {}

    def counted(items):
        seen: dict = {}
        for x in items:
            seen[x] = seen.get(x, 0) + 1
        return ", ".join(f"{k}{f' x{n}' if n > 1 else ''}" for k, n in seen.items())

    # One line per thing that happened, and none for what didn't: a "none" line
    # is read back as something to say ("no quests were advanced").
    facts = []
    if hp.get("max"):
        facts.append(f"HP COMING HOME: {hp.get('current')}/{hp.get('max')}")
    if fights:
        facts.append(f"FIGHTS ({outing.get('fight_count', len(fights))} total, {outing.get('wins', 0)} won, "
                     f"{outing.get('losses', 0)} lost):\n" + "\n".join(fight_lines))
        facts.append(f"HARDEST FIGHT: {hardest['monster']} ({hardest['rounds']} rounds, {hardest['taken']} damage taken)")
        big = [f["monster"] for f in fights if f.get("tier") in ("deadly", "boss")]
        if big:
            facts.append(f"THE BIG ONES: {counted(big)}")
    if outing.get("events"):
        facts.append("EVENTS:\n" + "\n".join(f"  - {e['title']}: {e['hook']}" for e in outing["events"]))
    done = list(dict.fromkeys(notes.get("quest_done", [])))
    moved = [q for q in dict.fromkeys(notes.get("quest", [])) if q not in done]
    if done:
        facts.append(f"QUEST FINISHED: {', '.join(done)}")
    if moved:
        facts.append(f"QUEST MOVED ON: {', '.join(moved)}")
    if notes.get("fled"):
        facts.append(f"RAN FROM: {counted(notes['fled'])}")
    if notes.get("used"):
        facts.append(f"DRANK OR USED: {counted(notes['used'])}")
    if loot:
        facts.append(f"LOOT: {', '.join(loot[:12])}" + (f" and {len(loot) - 12} more" if len(loot) > 12 else ""))
    if levels:
        facts.append(f"LEVELLED UP: reached level {max(levels)}")
    if outing.get("started") and outing.get("ended"):
        minutes = (outing["ended"] - outing["started"]) / 60
        if minutes < 10:
            facts.append("LENGTH: a quick trip")
        elif minutes > 45:
            facts.append("LENGTH: a long time out")
    if died and not daily_summary:
        outcome = (f"[CRITICAL — {char_name.upper()} WAS KNOCKED OUT ON THIS TRIP]\n"
                   f"{char_name} went down and woke at the Shrine. Do NOT tell the trip as a clean victory, "
                   f"and do NOT describe whatever beat them as falling or dying.\n"
                   f"End on {char_name} going down — pain, darkness, the Shrine's cold floor.\n[END CRITICAL]\n")
    elif daily_summary:
        outcome = "End on the character's final state at the close of the day, not on an intermediate outing.\n"
    else:
        outcome = "End on the return itself, in your own words — never repeat the HOW IT ENDED line.\n"
    # A one-fight trip told in six sentences gets padded with things that never happened.
    n = outing.get("fight_count", len(fights)) + len(outing.get("events", []))
    length = "2–3 sentences" if n <= 2 else "3–5 sentences" if n <= 6 else "4–6 sentences"
    nl = "\n"
    return f"""[TTRPG GROUND TRUTH — ONE OUTING — DO NOT CONTRADICT]
WORLD SETTING: Medieval fantasy. Pre-industrial. No modern technology.
CHARACTER: {char_name} ({char_class} Lv.{sheet.get('level', 1)})
{pronouns.line([char_name])}
WHERE: {' → '.join(dict.fromkeys(zones)) or 'the wilds'}
HOW IT ENDED: {char_name} {reason}.
{nl.join(facts)}
{outcome}
YOUR TASK: One paragraph, {length}, recalling the whole trip as it ended.
Give it a shape: how it started, what wore on them, the hardest moment, how it ended.
Capture the feel of it — was it close? dominant? sloppy? lucky?
Name the creatures they met most and use their descriptions for texture. Ground it in the senses — light, sound, smell.
Work in what else is listed above — an event, a quest finished, a fight they ran from, a potion — as part of the story, not as a list.
Tell only what is above. Never mention something that did not happen: no "no quests", no "without a potion".
Speak as Kaia — the GM narrator. Lowercase, grounded, specific. No purple prose.
No numbers, no dice, no blow-by-blow, no list. Do not invent fights, kills, items or deaths that are not above.
[END GROUND TRUTH]"""
