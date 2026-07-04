import os
import json
import discord
import secrets
from utils.infrastructure.logging.kaia_logger import log_error
from utils.infrastructure.system.yaml_config import config

async def log_world_event(event_text):
    import asyncio
    import functools
    def _sync_log(event_text):
        path = os.path.join("memory", "ttrpg", "world_events.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        events = []
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    events = json.load(f)
            except (OSError, json.JSONDecodeError, ValueError):
                events = []
        if not isinstance(events, list):
            events = []
        events.append(event_text)
        if len(events) > 10:
            events = list(events)[-10:]
        tmp = path + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(events, f, indent=2)
        os.replace(tmp, path)
    await asyncio.to_thread(functools.partial(_sync_log, event_text))

async def broadcast_world_event(ctx, embed: discord.Embed):
    """Post a notable event embed to the main #aethelgard broadcast channel."""
    try:
        channel_name = config.get('discord.rpg_channel', 'aethelgard').lower()
        channel = discord.utils.get(ctx.bot.get_all_channels(), name=channel_name)
        if channel:
            await channel.send(embed=embed)
    except Exception as e:
        log_error(f"[rpg broadcast] {e}")

def level_up_flavor(sheet: dict, level: int) -> str:
    """Short lore-flavored level-up announcement."""
    name = sheet["character_name"]
    cls = sheet.get("advanced_class") or sheet.get("class", "Adventurer")
    loc = sheet.get("location", "oakhaven").replace("_", " ")
    FLAVOR = {
        2:  f"*The first real fight is behind them. {name} is starting to understand the difference.*",
        3:  f"*{name} stopped flinching at the sound of something moving in the dark.*",
        4:  f"*Something about the way {name} moves has changed. The forest notices.*",
        5:  f"*{name} reached level 5. A crossroads approaches — the path ahead splits.*",
        6:  f"*{cls} {name} has survived long enough to become something the Whisperwood remembers.*",
        7:  f"*Seven levels in. The monsters that gave {name} trouble at the start no longer look up.*",
        8:  f"*The Aeridorian constructs track {name} now. That is not a comfortable thing to know.*",
        9:  f"*Nine levels. {name} has outlived three scouts and a guard who had twenty years of experience.*",
        10: f"*{name} reached level 10. The things that live in the ruins have started to take notice.*",
        11: f"*Something shifted in the deep Whisperwood when {name} leveled. The trees leaned in.*",
        12: f"*Twelve levels. {name} walks into places that kill other adventurers and walks back out. Every time.*",
        13: f"*The Aeridorian constructs no longer attack {name} on sight. They pause first. That's worse.*",
        14: f"*Fourteen levels. {name} is becoming something Oakhaven tells stories about. The stories aren't comfortable ones.*",
        15: f"*{name} reached the pinnacle. Whatever Aeridor was, {name} now stands where its champions stood. The ruins remember.*",
    }
    return FLAVOR.get(level, f"*{name} grows stronger. The {loc} feels it.*")

def rare_loot_flavor(monster_name: str, item_name: str, location: str) -> str:
    loc_name = location.replace("_", " ").title()
    FLAVOR = [
        f"*Something worth keeping fell from the {monster_name} in the {loc_name}.*",
        f"*The {monster_name} had no use for it anymore. Now someone does.*",
        f"*It wasn't supposed to survive the fight. Neither was the {monster_name}.*",
        f"*The {loc_name} gives up something old.*",
    ]
    return FLAVOR[secrets.randbelow(len(FLAVOR))]

def _boss_approach_flavor(theme_key: str, boss_name: str) -> str:
    """Atmospheric warning text shown when player is one room away from the boss."""
    flavors = {
        "undead": (
            f"*The temperature drops sharply. Your torch gutters for a moment — no draft, nothing visible.*\n\n"
            f"*Something massive shifts in the chamber beyond this door. The sound it makes is not quite breathing.*\n\n"
            f"**{boss_name}** is in there. The stonework around the frame is scorched from the inside."
        ),
        "constructs": (
            f"*The Aeridorian script above the next chamber door is lit from within — active. It wasn't lit two minutes ago.*\n\n"
            f"*A low resonance hum rises through the floor. Something on the other side registered your approach before you did.*\n\n"
            f"**{boss_name}** has been waiting. The waiting has been very long."
        ),
        "beasts": (
            f"*Something large exhales on the other side of the wall. The stone vibrates — briefly, once.*\n\n"
            f"*Claw marks on the floor, deep and recent, leading toward the chamber ahead. Whatever made them was moving fast.*\n\n"
            f"**{boss_name}** is in there. It knows you are out here."
        ),
        "deepwood": (
            f"*The roots in the walls thicken as you approach. The air turns green and close.*\n\n"
            f"*Something ancient and patient fills the chamber beyond — **{boss_name}** — and the Whisperwood itself seems to lean in to watch.*\n\n"
            f"*The door is made of something that was once a living tree. It still is, slightly.*"
        ),
        "demons": (
            f"*The air tastes like copper and burning stone. The light bends wrong around the next doorframe.*\n\n"
            f"*Whatever **{boss_name}** is, it has been seeping through the walls here for some time. The floor is warm underfoot.*\n\n"
            f"*You can still turn back. The dungeon is still behind you.*"
        ),
    }
    default = (
        f"*The passage narrows. Something breathes on the other side of the next chamber — slow, patient, immense.*\n\n"
        f"***{boss_name}*** *does not know the meaning of hurry.*\n\n"
        f"*Everything else in this dungeon is still behind you.*"
    )
    return flavors.get(theme_key, default)


def raid_outcome_flavor(town_name: str, theme_key: str, defenders_won: bool, casualty_count: int) -> str:
    """Short, terse lore flavor of the raid result."""
    t_name = town_name.replace("_", " ").title()
    if defenders_won:
        FLAVOR = [
            f"*The threat from the Whisperwood has been broken. {t_name} stands.*",
            f"*Decisive defense. The perimeter of {t_name} held under pressure.*",
            f"*The creatures fell back into the treeline. The gate is secure.*",
        ]
        return FLAVOR[secrets.randbelow(len(FLAVOR))]
    else:
        FLAVOR = [
            f"*Oakhaven took a heavy toll. {casualty_count} defender(s) fell at the perimeter.*",
            f"*The lines crumbled. Scorched stonework and broken barricades remain.*",
            f"*The gate was breached. The Shrine is filled with wounded.*",
        ]
        return FLAVOR[secrets.randbelow(len(FLAVOR))]
