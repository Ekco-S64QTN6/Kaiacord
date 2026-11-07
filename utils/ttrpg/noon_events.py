"""
noon_events.py — noon events that drive the rare content.

Each sets a ``*_until`` timestamp in world state through
``update_world_state`` and announces itself in #aethelgard. Readers compare the
timestamp with the clock (forest_events_rare.adjust_table, rare_spawns.roll_variant),
so nothing needs a separate expiry pass. They join the noon pool in
background_tasks and the ``!rpg event`` keys in rpg_social_handler.
"""
import time

import discord

from utils.infrastructure.logging.kaia_logger import log_action

DAY = 24 * 3600


async def _set_until(**keys):
    from utils.ttrpg.world_state import update_world_state
    until = time.time() + DAY
    await update_world_state(lambda state: state.update({k: until for k in keys}))


async def _announce(channel, title, text, footer, color, log_line):
    from utils.ttrpg.broadcast import log_world_event
    embed = discord.Embed(title=title, description=text, color=color)
    embed.set_footer(text=footer)
    await channel.send(embed=embed)
    await log_world_event(log_line)


async def run_starfall(bot_ctx, channel):
    """Fallen stars can be found by day as well as by night, three times as often."""
    await _set_until(starfall_until=True)
    await _announce(
        channel, "🌠 STARFALL",
        "*At noon the sky over the Whisperwood went dark for the space of a breath, and then it started "
        "raining light.*\n\nFallen stars are coming down all over the wilds. **Fallen Star** events can happen "
        "**by day as well as by night, three times as often**, until the next noon event.",
        "They are cold to the touch. Bring gloves anyway.", 0x5b6ee1,
        "🌠 **Starfall** — fallen stars in the wilds, by day and night, until the next noon event.")
    log_action("Noon Event: Starfall")


async def run_wandering_scholar(bot_ctx, channel):
    """Lore events (cairns, couriers, songstones, lantern shrines) are twice as likely."""
    await _set_until(lore_scholar_until=True)
    await _announce(
        channel, "📚 THE WANDERING ARCHIVIST",
        "*Archivist Venn arrived on the noon cart with three trunks of loose pages and no luggage.* "
        "\"Somewhere out there,\" she says, \"are the pages that go between these. I pay in gratitude, "
        "which is to say badly.\"\n\nLore discoveries in the wilds are **twice as likely** until the next "
        "noon event. `!rpg lore` shows what you've found.",
        "Venn takes her tea with ink in it. Nobody has corrected her.", 0xc8a86b,
        "📚 **The Wandering Archivist** — lore finds twice as likely until the next noon event.")
    log_action("Noon Event: Wandering Archivist")


async def run_gilded_migration(bot_ctx, channel):
    """Rare monster variants are four times as common."""
    await _set_until(rare_spawn_boost_until=True)
    await _announce(
        channel, "🪙 THE GILDED MIGRATION",
        "*The watchtower reports animals moving in the wrong direction, all of them toward Oakhaven, "
        "and several of them glittering.*\n\nRare creatures — **Gilded, Elder, Pale, Whispering and Resonant** "
        "— are **four times as common** on hunts until the next noon event.",
        "The rare ones carry something worth having.", 0xd4a843,
        "🪙 **The Gilded Migration** — rare creatures four times as common until the next noon event.")
    log_action("Noon Event: Gilded Migration")


async def run_hollow_sun(bot_ctx, channel):
    """An eclipse: harder encounters, more undead, and rare creatures four times as common."""
    from utils.ttrpg.world_state import update_world_state
    until = time.time() + DAY
    await update_world_state(lambda state: state.update({
        "encounter_mod": {"tier_shift": 1, "undead_bonus": True},
        "encounter_mod_expiry": until,
        "rare_spawn_boost_until": until,
    }))
    await _announce(
        channel, "🌑 THE HOLLOW SUN",
        "*At noon the sun went out like a lamp. It is still up there — you can see the ring of it — but "
        "it gives no light, and the Shrine bell is ringing on its own.*\n\nUntil the next noon event: "
        "**monsters are a tier stronger, the dead walk more often, and rare creatures are four times as common.**",
        "Elara has asked everyone to stay indoors. Nobody has.", 0x2c2c54,
        "🌑 **The Hollow Sun** — stronger monsters, more undead, rare creatures ×4 until the next noon event.")
    log_action("Noon Event: Hollow Sun")


async def run_ghost_caravan(bot_ctx, channel):
    """The lost caravan walks the road: more undead and more forest events everywhere."""
    from utils.ttrpg.world_state import update_world_state
    until = time.time() + DAY
    await update_world_state(lambda state: state.update({
        "encounter_mod": {"undead_bonus": True},
        "encounter_mod_expiry": until,
        "forest_event_bonus": 0.10,
        "forest_event_bonus_expiry": until,
    }))
    await _announce(
        channel, "🕯️ THE GHOST CARAVAN",
        "*A caravan came up the Trade Road at noon: twelve wagons, no drivers, and lanterns lit in daylight. "
        "It passed through the gate without opening it.*\n\nUntil the next noon event the dead walk more often, "
        "and **forest events are 10% more likely** everywhere — the wagons dropped things as they went.",
        "Hemlock says it comes every forty years. Hemlock says a lot of things.", 0x7f8fa6,
        "🕯️ **The Ghost Caravan** — more undead and +10% forest events until the next noon event.")
    log_action("Noon Event: Ghost Caravan")
