"""
!rpg command handler — Aethelgard Persistent World System

WORLD & MOVEMENT
  !rpg                       — status and location
  !rpg go <location>         — travel (auto-paths through town)
  !rpg look                  — narrate current location
  !rpg map                   — show accessible locations

CHARACTER
  !rpg new <Name> <Race> <Class>  — create character
  !rpg sheet [@user]              — view sheet
  !rpg leaderboard / lb           — adventurer rankings

OAKHAVEN ACTIONS
  !rpg rest                  — sleep at inn (costs gil)
  !rpg rumor                 — hear an inn rumor
  !rpg buy <item>            — buy from Hemlock
  !rpg sell <item>           — sell to Hemlock
  !rpg shop                  — view Hemlock's stock
  !rpg use <item>            — use consumable
  !rpg talk <npc>           — speak with NPC
  !rpg drink              — Stone Hearth: Buy an ale (2g, +3 temp HP)
  !rpg gamble             — Stone Hearth: Dice game (10g buy-in)
  !rpg pray               — Shrine: Daily blessing (+2 next hunt)
  !rpg offer <amount>     — Shrine: Donate gil for XP (cap 20/day)
  !rpg fountain           — Shrine: Sacred spring heal (every other day)
  !rpg scout              — Watchtower: Preview monster activity
  !rpg deliver            — Turn in a mognet letter (Oakhaven)

COMBAT
  !rpg hunt                  — fight random monster at location (costs 1 hunt)
  !rpg attack <monster>      — attack current monster (during hunt)
  !rpg flee                  — attempt to escape

UTILITY
  !rpg hunts                 — hunts remaining today
  !rpg inventory             — list items
  !rpg equip <item>          — equip weapon/armor
  !rpg roll <dice>           — pure dice roll
  !rpg bestiary              — dm reference
  !rpg help                  — this list

ADMIN
  !rpg xp <amount> [@user]   — award milestone XP
  !rpg give <item> [@user]   — grant item
  !rpg heal <amount> [@user] — restore HP
  !rpg event <description>   — global narrative event
"""

import asyncio
import time
import uuid as _uuid
import os
import json
import random
import discord
from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning
from utils.infrastructure.system.yaml_config import config

LOCATION_ACTIONS = {
    "oakhaven": [
        "`!rpg look` — observe the square",
        "`!rpg talk elara` — speak with Elder Elara",
        "`!rpg map` — view the world map",
        "`!rpg calendar` — view current season and upcoming events",
    ],
    "stone_hearth": [
        "`!rpg rest` — full heal (5 gil)",
        "`!rpg drink` — buy an ale, +3 temp HP (2 gil)",
        "`!rpg gamble` — dice game, 10 gil buy-in",
        "`!rpg rumor` — hear gossip from the bar",
        "`!rpg talk barkeep` — speak with Mira",
        "`!rpg talk hooded_figure` — speak with the figure in the corner",
    ],
    "hemlocks_store": [
        "`!rpg shop` — browse Hemlock's inventory",
        "`!rpg buy <item>` — purchase an item",
        "`!rpg sell <item>` — sell something",
        "`!rpg talk hemlock` — speak with Old Man Hemlock",
    ],
    "shrine": [
        "`!rpg pray` — receive a daily blessing (free)",
        "`!rpg offer <amount>` — donate gil for XP",
        "`!rpg fountain` — drink from the sacred spring (full heal, every other day)",
    ],
    "watchtower": [
        "`!rpg scout` — preview monster activity at all hunting grounds (once/day)",
        "`!rpg talk guard` — speak with the guards",
    ],
    "whisperwood_edge": [
        "`!rpg hunt` — fight a random monster (costs 1 hunt)",
        "`!rpg look` — observe the treeline",
    ],
    "whisperwood_deep": [
        "`!rpg hunt` — fight a random monster (costs 1 hunt, lvl 4+ recommended)",
        "`!rpg look` — observe the deep forest",
    ],
    "aeridor_ruins": [
        "`!rpg hunt` — fight a random monster (costs 1 hunt, lvl 7+ recommended)",
        "`!rpg look` — observe the ruins",
    ],
    "trade_road": [
        "`!rpg hunt` — encounter a road threat (costs 1 hunt)",
        "`!rpg look` — observe the road",
    ],
}

LOCATION_COLORS = {
    "oakhaven":          0x8b7355,   # muddy brown — the square
    "stone_hearth":      0xc0622f,   # warm ember orange — the fire
    "hemlocks_store":    0x6b8e6b,   # muted green — herbs and iron
    "shrine":            0x9b9bc8,   # pale violet — the Silent Ones
    "watchtower":        0x8aacbf,   # steel blue — sky and wood
    "whisperwood_edge":  0x4a7c4e,   # forest green
    "whisperwood_deep":  0x2d5a35,   # deep dark green
    "aeridor_ruins":     0x7a6a9a,   # resonance purple
    "trade_road":        0xa08050,   # dust and dirt
}

async def handle_rpg_command(ctx, msg, send_kaia_response):
    """Main !rpg dispatcher."""
    parts = msg.content.strip().split(maxsplit=2)
    # !rpg with no args = status board
    sub = parts[1].lower() if len(parts) > 1 else "status_board"
    rest = parts[2] if len(parts) > 2 else ""
    
    author_id = str(msg.author.id)
    author_name = msg.author.display_name
    is_owner = ctx.config.is_owner(msg.author.name, author_name, author_id)
    
    handlers = {
        "status_board": _handle_status,
        "new":       _handle_new,
        "sheet":     _handle_sheet,
        "go":        _handle_go,
        "look":      _handle_look,
        "map":       _handle_map,
        "rest":      _handle_rest,
        "rumor":     _handle_rumor,
        "buy":       _handle_buy,
        "sell":      _handle_sell,
        "shop":      _handle_shop,
        "use":       _handle_use,
        "talk":      _handle_talk,
        "calendar":  _handle_calendar,
        "hunt":      _handle_hunt,
        "attack":    _handle_attack,
        "flee":      _handle_flee,
        "hunts":     _handle_hunts,
        "inventory": _handle_inventory,
        "equip":     _handle_equip,
        "roll":      _handle_roll,
        "bestiary":  _handle_bestiary,
        "help":      _handle_rpg_help,
        "xp":        _handle_xp,
        "give":      _handle_give,
        "heal":      _handle_heal,
        "event":     _handle_event,
        "drink":     _handle_drink,
        "gamble":    _handle_gamble,
        "pray":      _handle_pray,
        "offer":     _handle_offer,
        "scout":     _handle_scout,
        "deliver":   _handle_deliver,
        "fountain":  _handle_fountain,
        "leaderboard": _handle_leaderboard,
        "lb":        _handle_leaderboard,
        "notices":   _handle_notices,
        "quests":    _handle_quests,
        "quest":     _handle_quest_detail,
        "accept":    _handle_accept,
        "brew":      _handle_brew,
    }
    async def _auto_send(channel, text, use_code_block=None):
        if use_code_block is None:
            use_code_block = "```" not in str(text)
        return await send_kaia_response(channel, text, use_code_block=use_code_block)

    handler = handlers.get(sub, _handle_rpg_help)
    try:
        await handler(ctx, msg, _auto_send, rest, author_id, author_name, is_owner)
    except Exception as e:
        log_error(f"[rpg] Handler error in '{sub}': {e}")
        await _auto_send(msg.channel, f"system fault in `{sub}`. check logs.")


# ── HUD / Status ─────────────────────────────────────────────────────────────

async def _handle_status(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.progression import hunts_remaining, MAX_HUNTS_PER_DAY, xp_to_next_level
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.session_manager import load_session
    from utils.ttrpg.rpg_ui import colored_bar, hp_label, CLASS_ICONS, LOCATION_ICONS, ANSI_GREEN, ANSI_RESET
    import discord
    
    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        await msg.channel.send(embed=discord.Embed(
            description="You do not exist in Aethelgard. Type `!rpg new <Name> <Race> <Class>` to begin.",
            color=0xcc4444
        ))
        return
        
    loc = sheet.get("location", "oakhaven")
    loc_data = LOCATION_DATA.get(loc, {})
    loc_name = loc_data.get("name", loc.replace("_", " ").title())
    
    hp_cur = sheet["hp"].get("current", 1)
    hp_max = sheet["hp"].get("max", 1)
    
    xp_cur = sheet["xp"]
    xp_next = xp_to_next_level(sheet["level"])
    if xp_next:
        from utils.ttrpg.progression import XP_THRESHOLDS
        floor = XP_THRESHOLDS.get(sheet["level"], 0)
        progress = xp_cur - floor
        req = xp_next - floor
        xp_bar_str = colored_bar(progress, req, 14) + f" → Lv.{sheet['level'] + 1}"
    else:
        xp_bar_str = f"{ANSI_GREEN}██████████████{ANSI_RESET} (MAX)"
        
    gil = sheet.get("gil", 0)
    
    eq = sheet.get("equipment", {})
    w = eq.get("weapon")
    a = eq.get("armor")
    w_str = f"{w['name']} (+{w['attack_bonus']} ATK, d{w['damage_die']})" if w else "Unarmed"
    a_str = f"{a['name']} (+{a['defense_bonus']} DEF)" if a else "Unarmored"
    
    hunts = hunts_remaining(sheet)
    
    exits = loc_data.get("exits", [])
    nearby = []
    for e in exits:
        ld = LOCATION_DATA.get(e, {})
        n = ld.get("name", e)
        if ld.get("hunting"): n += " *(hunting)*"
        nearby.append(n)
    nearby_str = " · ".join(nearby) if nearby else "None"
    
    s = await asyncio.to_thread(load_session, str(msg.channel.id))
    in_combat = False
    if s and s.get("combat_active"):
        for m in s.get("monsters", []):
            if m.get("aggro_uid") == uid:
                in_combat = True
                break
                
    pct_hp = hp_cur / hp_max if hp_max > 0 else 0
    if hp_cur <= 0:
        color = 0x8B0000   # dark red - dead
    elif in_combat:
        color = 0xFF4500   # orange-red - fighting
    elif pct_hp <= 0.3:
        color = 0xFF6B6B   # red - critical
    else:
        color = 0x2D5A27   # deep forest green - normal
        
    embed = discord.Embed(
        title=f"{CLASS_ICONS.get(sheet.get('class'), '⚔️')}  {sheet['character_name'].upper()}",
        description=f"*{sheet.get('class')} Lv.{sheet['level']}  ·  {LOCATION_ICONS.get(loc, '🗺️')} {loc_name}*",
        color=color
    )
    
    embed.add_field(
        name="❤️ HP",
        value=f"```ansi\n{colored_bar(hp_cur, hp_max, 14)}\n``` {hp_label(hp_cur, hp_max)}",
        inline=False
    )
    embed.add_field(
        name="✨ XP",
        value=f"```ansi\n{xp_bar_str}\n``` {xp_cur}/{xp_next or 'MAX'}",
        inline=True
    )
    embed.add_field(name="💰 Gil", value=f"{gil}g", inline=True)
    
    # Empty field for grid alignment if needed, or rely on Discord's 3-column layout
    
    embed.add_field(name="🗡️ Weapon", value=w_str, inline=True)
    embed.add_field(name="🛡️ Armor",  value=a_str, inline=True)
    embed.add_field(name="🎯 Hunts", value=f"{hunts}/{MAX_HUNTS_PER_DAY} remaining", inline=True)
    
    embed.add_field(name="🗺️ Nearby", value=nearby_str, inline=False)
    
    conds = sheet.get("conditions", [])
    if conds:
        cond_str = ", ".join(c.title() for c in conds)
        embed.add_field(name="⚠️ Status Effects", value=cond_str, inline=False)
    
    loc_hints = LOCATION_ACTIONS.get(loc, ["`!rpg look`"])
    hint_labels = [h.split("` —")[0].replace("`", "").strip() for h in loc_hints]
    footer_text = " · ".join(hint_labels)
    if loc_data.get("hunting"):
        footer_text += " · !rpg hunt"
    embed.set_footer(text=footer_text)
    
    await msg.channel.send(embed=embed)


# ── Character Management ─────────────────────────────────────────────────────

async def _handle_new(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, create, format_sheet
    from utils.ttrpg.dice_engine import roll, CLASSES
    
    import discord
    existing = await asyncio.to_thread(load, uid)
    if existing:
        return await msg.channel.send(embed=discord.Embed(
            description=f"You already have a character: **{existing['character_name']}**.\nSheets are permanent.",
            color=0x888888
        ))
    
    args = rest.split()
    if len(args) < 3:
        class_list = ", ".join(CLASSES.keys())
        return await msg.channel.send(embed=discord.Embed(
            description=f"Usage: `!rpg new <Name> <Race> <Class>`\nClasses: {class_list}",
            color=0x888888
        ))
    
    char_name = args[0]
    race = args[1].title()
    class_name = args[2].title()
    
    if class_name not in CLASSES:
        class_list = ", ".join(CLASSES.keys())
        return await msg.channel.send(embed=discord.Embed(
            description=f"Unknown class. Options: {class_list}",
            color=0xcc4444
        ))
    
    RACE_BONUSES = {
        "Human":    {"str": 1, "dex": 1, "con": 1, "int": 1, "wis": 1, "cha": 1},
        "Elf":      {"dex": 2, "int": 1, "wis": 1},
        "Silvani":  {"dex": 2, "wis": 2},
        "Dwarf":    {"con": 2, "str": 1},
        "Glimmerkin": {"cha": 2, "int": 1, "dex": 1},
        "Veiled":   {"int": 2, "cha": 2},
    }
    bonus_dict = RACE_BONUSES.get(race, {})
    
    stats_order = ["str", "dex", "con", "int", "wis", "cha"]
    rolled_stats = {}
    roll_log = []
    for stat in stats_order:
        dice = [roll("d6")[0] for _ in range(4)]
        base = sum(sorted(dice)[1:])  # drop lowest
        bonus = bonus_dict.get(stat, 0)
        rolled_stats[stat] = base + bonus
        bonus_str = f" (+{bonus} race)" if bonus else ""
        roll_log.append(f"{stat.upper()}: {sorted(dice)[1:]} = {base}{bonus_str} -> {rolled_stats[stat]}")
    
    sheet = await asyncio.to_thread(create, uid, uname, char_name, race, class_name, rolled_stats)
    
    embed = discord.Embed(
        title="✨ New Adventurer Registered",
        description=f"**{char_name}**, the {race} {class_name}, has entered Aethelgard.\n\n**Stat rolls (4d6 drop lowest + Race):**\n```\n" + "\n".join(roll_log) + "\n```\n\nYou awaken in Oakhaven Town Square. Type `!rpg` to view your HUD.",
        color=0xddcc88
    )
    await msg.channel.send(embed=embed)

async def _handle_sheet(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, format_sheet
    target_id = str(msg.mentions[0].id) if msg.mentions else uid
    sheet = await asyncio.to_thread(load, target_id)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="Character not found.", color=0xcc4444))
    await send(msg.channel, format_sheet(sheet), use_code_block=True)


# ── World & Movement ─────────────────────────────────────────────────────────

async def _handle_go(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.world import LOCATION_DATA, resolve_location
    import discord

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet: return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})

    # --- No args: show "where to?" embed ---
    if not rest.strip():
        exits = current_loc.get("exits", [])
        exit_lines = "\n".join(
            f"`!rpg go {key}` — {LOCATION_DATA[key]['name']}"
            for key in exits
            if key in LOCATION_DATA
        )
        color = LOCATION_COLORS.get(current_loc_key, 0x888888)
        embed = discord.Embed(
            title=f"📍 {current_loc.get('name', current_loc_key)}",
            description=f"*{current_loc.get('short', '')}*",
            color=color
        )
        embed.add_field(name="Where to?", value=exit_lines or "No exits.", inline=False)
        return await msg.channel.send(embed=embed)

    target = resolve_location(rest.strip())
    if not target or target not in LOCATION_DATA:
        return await msg.channel.send(embed=discord.Embed(description=f"Unknown location: `{rest.strip()}`", color=0xcc4444))

    if target == current_loc_key:
        return await msg.channel.send(embed=discord.Embed(description="You're already there.", color=0x888888))

    # --- Auto-path: BFS to find shortest route ---
    def _find_path(start, end):
        from collections import deque
        visited = {start}
        queue = deque([(start, [start])])
        while queue:
            node, path = queue.popleft()
            for neighbor in LOCATION_DATA.get(node, {}).get("exits", []):
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    direct = target in current_loc.get("exits", [])
    path = [current_loc_key, target] if direct else _find_path(current_loc_key, target)

    if not path:
        return await msg.channel.send(embed=discord.Embed(description=f"There's no route from here to **{LOCATION_DATA.get(target, {}).get('name', target)}**.", color=0xcc4444))

    # Move player to final destination
    sheet["location"] = target
    await asyncio.to_thread(save, sheet)

    # Build arrival embed
    loc_data = LOCATION_DATA.get(target, {})
    name = loc_data.get("name", target)
    actions = LOCATION_ACTIONS.get(target, ["`!rpg look` — observe the surroundings"])
    color = LOCATION_COLORS.get(target, 0x888888)

    # Show travel path if multi-hop
    if len(path) > 2:
        via_names = [LOCATION_DATA.get(p, {}).get("name", p) for p in path[1:-1]]
        desc = f"*Traveling via {', '.join(via_names)}...*\n\n*{loc_data.get('short', '')}*"
    else:
        desc = f"*{loc_data.get('short', '')}*"

    embed = discord.Embed(
        title=f"📍 {name}",
        description=desc,
        color=color
    )

    embed.add_field(
        name="Available actions",
        value="\n".join(actions),
        inline=False
    )

    rec = loc_data.get("recommended_level")
    if rec and sheet["level"] < rec - 1:
        embed.set_footer(text=f"⚠️ Recommended level {rec}+ — proceed with caution")

    await msg.channel.send(embed=embed)

async def _handle_look(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.rpg_prompt_builder import build_look_prompt
    from utils.social.kaia_social_responder import load_persona_async
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    loc = sheet.get("location", "oakhaven")
    data = LOCATION_DATA.get(loc, {})
    
    prompt = build_look_prompt(
        sheet, 
        data.get("name", loc), 
        data.get("short", ""), 
        data.get("atmosphere", "generic outdoors")
    )
    
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": f"{sheet['character_name']} looks around the area."}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 150
    opts["temperature"] = 0.85
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=45.0
                ),
                task_id=f"rpg_look_{_uuid.uuid4().hex[:8]}"
            )
            narration = resp["message"]["content"].strip().replace("```", "")
            if narration: await send(msg.channel, f"*{narration}*")
        except Exception as e:
            log_error(f"[rpg look] {e}")

async def _handle_map(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.world import LOCATION_DATA
    import discord

    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})
    
    exits = current_loc.get("exits", [])
    exit_lines = "\n".join(
        f"  `!rpg go {key}` — {LOCATION_DATA[key]['name']}"
        for key in exits
        if key in LOCATION_DATA
    )
    
    embed = discord.Embed(
        title=f"🗺️ {current_loc.get('name', current_loc_key)} — Map",
        description="*(Use `!rpg go <location>` to travel)*",
        color=0x4488cc
    )
    embed.add_field(name="Accessible Locations", value=exit_lines or "Nowhere else to go.", inline=False)
    await msg.channel.send(embed=embed)


# ── Economy / NPCs / World Iterations ───────────────────────────────────────

async def _handle_rest(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    import discord
    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(description="You need to be at the Stone Hearth inn to rest. (`!rpg go stone_hearth`)", color=0xcc4444))
        
    cost = 5
    if sheet.get("gil", 0) < cost:
        return await msg.channel.send(embed=discord.Embed(description=f"Mira shakes her head. \"Beds aren't free.\"\nYou need {cost} gil. You have {sheet.get('gil', 0)}g.", color=0xcc4444))
        
    hp_cur = sheet["hp"]["current"]
    hp_max = sheet["hp"]["max"]
    
    has_ale = "ale_warmth" in sheet.get("conditions", [])
    if hp_cur >= hp_max and not has_ale:
        return await msg.channel.send(embed=discord.Embed(description=f"**{sheet['character_name']}** is already at maximum health.\nMira raises an eyebrow. *\"You're paying for a room you won't use?\"*", color=0x888888))

    # Clear ale temp HP and condition BEFORE healing
    if "ale_warmth" in sheet.get("conditions", []):
        sheet["conditions"].remove("ale_warmth")
        sheet["hp"]["max"] -= 3  # remove the temp bonus
        sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

    healed = sheet["hp"]["max"] - sheet["hp"]["current"]
    sheet["hp"]["current"] = sheet["hp"]["max"]
    sheet["gil"] -= cost

    await asyncio.to_thread(save, sheet)
    
    await msg.channel.send(embed=discord.Embed(
        description=f"🛏️ **{sheet['character_name']}** rests at the Stone Hearth. (-{cost} gil)\nHP restored: **+{healed}** (Full)\nRemaining gil: {sheet['gil']}g",
        color=0x44aa44
    ))

async def _handle_rumor(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.rpg_prompt_builder import build_rumor_prompt
    from utils.social.kaia_social_responder import load_persona_async
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await asyncio.to_thread(load, uid)
    import discord
    if sheet and sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(description="You must be at the Stone Hearth to hear rumors. (`!rpg go stone_hearth`)", color=0xcc4444))
        
    prompt = build_rumor_prompt()
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": "I sit at the bar. What are people talking about?"}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 100
    opts["temperature"] = 0.95
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=30.0
                ),
                task_id=f"rpg_rumor_{_uuid.uuid4().hex[:8]}"
            )
            rumor = resp["message"]["content"].strip().replace("```", "")
            if rumor:
                embed = discord.Embed(
                    title="🗣️ Rumor Heard",
                    description=f"*{rumor}*",
                    color=0x888888
                )
                await msg.channel.send(embed=embed)
        except Exception as e:
            log_error(f"[rpg rumor] {e}")

async def _handle_shop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.shop import get_shop_inventory
    import discord
    sheet = await asyncio.to_thread(load, uid)
    if sheet and sheet.get("location") != "hemlocks_store":
        return await msg.channel.send(embed=discord.Embed(description="You must be at Hemlock's Store to view inventory. (`!rpg go hemlocks_store`)", color=0xcc4444))
        
    weapons, armor, consumables = get_shop_inventory()

    lines = []
    lines.append("**Weapons**")
    for k, v in weapons.items(): lines.append(f"  `{k:<15}` {v['name']:<20} {v['value']}g")
    lines.append("\n**Armor**")
    for k, v in armor.items(): lines.append(f"  `{k:<15}` {v['name']:<20} {v['value']}g")
    lines.append("\n**Consumables**")
    for k, v in consumables.items(): lines.append(f"  `{k:<15}` {v['name']:<20} {v['value']}g")

    footer_text = ""
    if sheet:
        footer_text = f"Your Gil: {sheet.get('gil', 0)}g  |  !rpg buy <item> or !rpg sell <item>"

    embed = discord.Embed(
        title="🛒 Hemlock's Store",
        description="```\n" + "\n".join(lines) + "\n```",
        color=0x4488cc
    )
    if footer_text:
        embed.set_footer(text=footer_text)

    await msg.channel.send(embed=embed)

async def _handle_buy(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import process_purchase
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    import discord
    if sheet.get("location") != "hemlocks_store":
        return await msg.channel.send(embed=discord.Embed(description="You must be at Hemlock's Store to buy items.", color=0xcc4444))
        
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Buy what? Use `!rpg shop` for items.", color=0x888888))
        
    args = rest.strip().split()
    if len(args) > 1 and args[-1].isdigit() and int(args[-1]) > 0:
        quantity = int(args[-1])
        item_key = " ".join(args[:-1]).lower()
    else:
        quantity = 1
        item_key = rest.strip().lower()
        
    success, purchase_msg, updated_sheet = process_purchase(sheet, item_key, quantity)
    
    if success:
        from utils.ttrpg.shop import find_item
        item = find_item(item_key)
        
        # Determine specific response with optional soft warnings
        final_msg = purchase_msg
        if item and "classes" in item and updated_sheet["class"] not in item["classes"]:
            final_msg += f"\n*Note: this is typically used by {'/'.join(item['classes'])} — you can equip it but it may feel awkward.*"
            
        if item and item["category"] in ["weapon", "armor"] and quantity == 1:
            slot = item["category"]
            if not updated_sheet["equipment"].get(slot):
                updated_sheet["inventory"].remove(item["key"])
                updated_sheet["equipment"][slot] = item
                final_msg += f"\nAuto-equipped **{item['name']}**."
        
        await asyncio.to_thread(save, updated_sheet)
        await msg.channel.send(embed=discord.Embed(description=final_msg, color=0x44aa44))
    else:
        await msg.channel.send(embed=discord.Embed(description=purchase_msg, color=0xcc4444))

async def _handle_sell(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import process_sell
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    import discord
    if sheet.get("location") != "hemlocks_store":
        return await msg.channel.send(embed=discord.Embed(description="You must remain at Hemlock's Store to sell items.", color=0xcc4444))
        
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Sell what? Use `!rpg inventory` for items.", color=0x888888))
        
    item_key = rest.strip().lower()
    success, resp_msg, updated_sheet = process_sell(sheet, item_key)
    
    if success:
        await asyncio.to_thread(save, updated_sheet)
        color = 0x44aa44
    else:
        color = 0xcc4444
    await msg.channel.send(embed=discord.Embed(description=resp_msg, color=color))

async def _handle_calendar(ctx, msg, send, rest, uid, uname, is_owner):
    import discord
    from utils.ttrpg.calendar import get_today_summary, SPECIAL_DAYS
    from datetime import date

    summary = get_today_summary()
    season = summary["season"]
    special = summary["special_day"]

    # Build upcoming events (next 14 days)
    today = date.today()
    upcoming = []
    for i in range(1, 15):
        from datetime import timedelta
        check = today + timedelta(days=i)
        day_data = SPECIAL_DAYS.get((check.month, check.day))
        if day_data:
            upcoming.append(f"**{check.strftime('%b %d')}** — {day_data['name']}")

    color_map = {
        "spring": 0x88cc88,
        "summer": 0xf5c842,
        "autumn": 0xd4703c,
        "winter": 0x88aacc,
    }

    embed = discord.Embed(
        title=f"{summary['season_emoji']} {summary['season_name']} — {summary['date']}",
        description=f"*{summary['season_flavor']}*",
        color=color_map[season]
    )

    if special:
        embed.add_field(
            name=f"✨ {special['name']}",
            value=f"{special['desc']}\n\n**Today's effect:** {special.get('buff_desc', 'None')}",
            inline=False
        )
    else:
        embed.add_field(
            name="Today",
            value="An ordinary day. The Whisperwood does not care about ordinary days.",
            inline=False
        )

    if upcoming:
        embed.add_field(
            name="Upcoming",
            value="\n".join(upcoming[:5]),
            inline=False
        )

    embed.set_footer(text="!rpg calendar — updated daily at dawn")
    await msg.channel.send(embed=embed)

async def _handle_talk(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.npc_registry import get_npc, NPCS
    from utils.ttrpg.rpg_prompt_builder import build_npc_prompt
    from utils.ttrpg.character_manager import load, save
    from utils.social.kaia_social_responder import load_persona_async
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await asyncio.to_thread(load, uid)
    
    args = rest.strip().split(maxsplit=1)
    import discord
    if not args:
        return await msg.channel.send(embed=discord.Embed(description=f"Talk to who? Known NPCs: {', '.join(NPCS.keys())}", color=0x888888))
        
    npc_key = args[0].lower()
    npc = get_npc(npc_key)
    if not npc:
        return await msg.channel.send(embed=discord.Embed(description=f"Nobody by that name. Known NPCs: {', '.join(NPCS.keys())}", color=0xcc4444))
        
    loc = sheet.get("location", "oakhaven") if sheet else "oakhaven"
    if npc["location"] != "any" and npc["location"] != loc:
        from utils.ttrpg.world import LOCATION_DATA
        target = LOCATION_DATA.get(npc['location'], {}).get('name', npc['location'])
        return await msg.channel.send(embed=discord.Embed(description=f"**{npc['name']}** isn't here. They're usually at **{target}**.", color=0xcc4444))
        
    player_msg = args[1] if len(args) > 1 else "(Approach silently)"
    
    # Dynamic Context Calculation
    from utils.ttrpg.calendar import get_today_summary
    cal_summary = get_today_summary()
    season = cal_summary["season_name"]
    special_day = cal_summary["special_day"]["name"] if cal_summary["special_day"] else ""
    from datetime import datetime
    time_of_day_hour = datetime.now().hour
    
    if 5 <= time_of_day_hour < 12:
        time_of_day = "morning"
    elif 12 <= time_of_day_hour < 17:
        time_of_day = "afternoon"
    elif 17 <= time_of_day_hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
        
    blacked_out = False
    if sheet:
        if sheet.get("location") == "shrine" and sheet.get("hp", {}).get("current") == 1:
            blacked_out = True
            
    topic = ""
    if "topics" in npc and npc["topics"]:
        topic = random.choice(npc["topics"])
        
    # Quest Integration
    from utils.ttrpg.quest_registry import get_npc_quests, get_quest
    available_quests = []
    active_quest_info = None
    quest_progress_msg = ""
    
    if sheet:
        # Check for available quests
        all_npc_quests = get_npc_quests(npc_key)
        completed = sheet.get("completed_quests", [])
        for q in all_npc_quests:
            if q["id"] not in completed and q["id"] != sheet.get("active_quest"):
                if sheet["level"] >= q["requirements"].get("level", 1):
                    available_quests.append(q)
                    
        # Check active quest
        active_id = sheet.get("active_quest")
        if active_id:
            q = get_quest(active_id)
            if q and q["npc"] == npc_key:
                active_quest_info = q
                # Calculate progress message
                prog = sheet.get("quest_progress", {}).get(active_id, [])
                total = len(q["tasks"])
                quest_progress_msg = f"{len(prog)}/{total} tasks done: {', '.join(prog)}"
                
        # Update progress (Talk tasks)
        if active_id:
            q = get_quest(active_id)
            if q:
                task_id = f"talk_{npc_key}"
                if task_id in q["tasks"]:
                    prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                    if task_id not in prog:
                        prog.append(task_id)
                        # Check completion
                        if all(t in prog for t in q["tasks"]):
                            # Complete!
                            sheet["xp"] += q["rewards"].get("xp", 0)
                            sheet["gil"] += q["rewards"].get("gil", 0)
                            if "item" in q["rewards"]:
                                sheet.setdefault("inventory", []).append(q["rewards"]["item"])
                            if "recipe" in q["rewards"]:
                                r_key = q["rewards"]["recipe"]
                                if r_key not in sheet.setdefault("recipes", []):
                                    sheet.setdefault("recipes", []).append(r_key)
                                    quest_progress_msg += f" (Learned Recipe: {r_key})"
                            sheet["active_quest"] = None
                            sheet.setdefault("completed_quests", []).append(active_id)
                            await _log_world_event(f"**{sheet['character_name']}** completed '**{q['name']}**'.")
                            quest_progress_msg = "COMPLETED"
                        else:
                            await asyncio.to_thread(save, sheet)
            
        # Generic turn-in check is covered by the talk task tracking above.
        # If an NPC has a specific inventory turn-in (like Maren), we can add it here.
        if npc_key == "maren" and active_id == "maren_herbs":
            # This is optional if we only want kill_road_bandit + talk_maren.
            # But we could check for an item here if we wanted.
            pass

    context = {
        "season": season,
        "special_day": special_day,
        "time_of_day": time_of_day,
        "blacked_out": blacked_out,
        "topic": topic,
        "available_quests": available_quests,
        "active_quest_info": active_quest_info,
        "quest_progress_msg": quest_progress_msg
    }
    
    prompt = build_npc_prompt(sheet, npc, player_msg, context)
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": f"The player says: {player_msg}"}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 150
    opts["temperature"] = 0.85
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=45.0
                ),
                task_id=f"rpg_talk_{_uuid.uuid4().hex[:8]}"
            )
            dialogue = resp["message"]["content"].strip().replace("```", "")
            if dialogue: 
                embed = discord.Embed(
                    title=f"🗣️ {npc['name']}",
                    description=f"*{dialogue}*",
                    color=0x4488cc
                )
                await msg.channel.send(embed=embed)
        except Exception as e:
            log_error(f"[rpg talk] {e}")


async def _log_world_event(event_text):
    path = os.path.join("memory", "ttrpg", "world_events.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    events = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
        except:
            events = []
            
    if not isinstance(events, list):
        events = []
    events.append(event_text)
    if len(events) > 10:
        events = list(events)[-10:]
        
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2)

async def _handle_brew(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.alchemy import brew, get_recipe, ALCHEMY_RECIPES
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    loc = sheet.get("location", "oakhaven")
    if not LOCATION_DATA.get(loc, {}).get("brewing_allowed"):
        return await send(msg.channel, "You need a proper station to brew. Try the Herbalist's Hut.")
        
    recipe_id = rest.strip().lower()
    if not recipe_id:
        # List known recipes
        known = sheet.get("recipes", [])
        if not known:
            return await send(msg.channel, "You don't know any recipes yet. Speak with Sister Maren.")
        
        import discord
        embed = discord.Embed(title="📜 Known Recipes", color=0x2ecc71)
        for r_key in known:
            r = get_recipe(r_key)
            if r:
                ingredients = ", ".join(r["ingredients"])
                embed.add_field(name=r["name"], value=f"Ingredients: {ingredients}\n`!rpg brew {r_key}`", inline=False)
        return await msg.channel.send(embed=embed)
        
    success, result_msg = brew(sheet, recipe_id)
    if success:
        await asyncio.to_thread(save, sheet)
        import discord
        await msg.channel.send(embed=discord.Embed(description=result_msg, color=0x2ecc71))
    else:
        import discord
        await msg.channel.send(embed=discord.Embed(description=result_msg, color=0xcc4444))

async def _handle_notices(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    sheet = await asyncio.to_thread(load, uid)
    if sheet and sheet.get("location") != "notice_board":
        import discord
        return await msg.channel.send(embed=discord.Embed(description="You must be at the Notice Board to read it. (`!rpg go notice_board`)", color=0xcc4444))
        
    import os
    import json
    path = os.path.join("memory", "ttrpg", "world_events.json")
    events = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
        except:
            pass
            
    if not events:
        desc = "*The board is currently empty. Oakhaven is quiet.*"
    else:
        desc = "\n".join([f"• {e}" for e in reversed(events)])
        
    import discord
    embed = discord.Embed(
        title="📝 Oakhaven Notice Board",
        description=desc,
        color=0x8b7355
    )
    await msg.channel.send(embed=embed)


async def _handle_quests(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    import discord
    active = sheet.get("active_quest")
    completed = sheet.get("completed_quests", [])
    
    desc = ""
    if active:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active)
        if q:
            desc += f"📜 **Active Quest:** {q['name']}\n> {q['description']}\n\n"
        else:
            desc += f"📜 **Active Quest:** {active} (invalid ID)\n\n"
            
    if completed:
        desc += "✅ **Completed Quests:**\n"
        desc += "\n".join([f"• {q_id.replace('_', ' ').title()}" for q_id in completed])
    else:
        desc += "❌ **No completed quests.**"
        
    embed = discord.Embed(
        title=f"Quest Log — {sheet['character_name']}",
        description=desc,
        color=0x4a90e2
    )
    await msg.channel.send(embed=embed)

async def _handle_quest_detail(ctx, msg, send, rest, uid, uname, is_owner):
    # !rpg quest <quest_id> or just !rpg quest for current
    from utils.ttrpg.character_manager import load
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    quest_id = rest.strip().lower() or sheet.get("active_quest")
    if not quest_id:
        return await send(msg.channel, "You have no active quest. Speak with NPCs in Oakhaven for tasks.")
        
    from utils.ttrpg.quest_registry import get_quest
    q = get_quest(quest_id)
    if not q:
        return await send(msg.channel, f"Quest `{quest_id}` not found.")
        
    import discord
    embed = discord.Embed(
        title=f"📜 {q['name']}",
        description=q['description'],
        color=0x4a90e2
    )
    embed.add_field(name="Rewards", value=f"• {q['rewards'].get('xp', 0)} XP\n• {q['rewards'].get('gil', 0)} Gil")
    if "item" in q['rewards']: embed.add_field(name="Bonus", value=f"🎁 {q['rewards']['item'].replace('_', ' ').title()}")
    
    await msg.channel.send(embed=embed)

async def _handle_accept(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    quest_id = rest.strip().lower()
    if not quest_id:
        return await send(msg.channel, "Usage: `!rpg accept <quest_id>`")
        
    if sheet.get("active_quest"):
        return await send(msg.channel, f"You are already on a quest: `{sheet['active_quest']}`. Complete or abandon it first.")
        
    from utils.ttrpg.quest_registry import get_quest
    q = get_quest(quest_id)
    if not q:
        return await send(msg.channel, f"Quest `{quest_id}` not found.")
        
    if quest_id in sheet.get("completed_quests", []):
        return await send(msg.channel, "You have already completed this quest.")
        
    # Check level requirement
    if sheet['level'] < q['requirements'].get('level', 1):
        return await send(msg.channel, f"You must be at least Level {q['requirements']['level']} to accept this quest.")
        
    sheet["active_quest"] = quest_id
    await asyncio.to_thread(save, sheet)
    
    import discord
    embed = discord.Embed(
        title="Quest Accepted!",
        description=f"You have taken up the task: **{q['name']}**.\n\n*{q['description']}*",
        color=0x2ecc71
    )
    await msg.channel.send(embed=embed)


# ── Items and Equipment ──────────────────────────────────────────────────────

async def _handle_inventory(ctx, msg, send, rest, uid, uname, is_owner):
    import discord
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.shop import find_item

    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return

    inventory = sheet.get("inventory", [])
    if not inventory:
        return await msg.channel.send(embed=discord.Embed(
            title="🎒 Inventory",
            description="*Empty.*",
            color=0x888888
        ))

    lines = []
    
    from collections import Counter
    inv_counts = Counter(inventory)
    
    for key, count in inv_counts.items():
        item = find_item(key)
        count_str = f" x{count}" if count > 1 else ""
        if item:
            category = item["category"]
            if category == "consumable":
                if item.get("on_use") == "starter_kit":
                    lines.append(f"**{item['name']}**{count_str} — {item.get('description', 'starter pack type !rpg use pack to open')}")
                else:
                    hp = item.get("hp_restore", 0)
                    val = item.get("value", 0)
                    lines.append(f"**{item['name']}**{count_str} — restores {hp} HP  *(sell: {val // 2}g)*")
            elif category == "weapon":
                lines.append(f"**{item['name']}**{count_str} — +{item['attack_bonus']} ATK, d{item['damage_die']}  *(sell: {item['value'] // 2}g)*")
            elif category == "armor":
                lines.append(f"**{item['name']}**{count_str} — +{item['defense_bonus']} DEF  *(sell: {item['value'] // 2}g)*")
            else:
                lines.append(f"**{item['name']}**{count_str}")
        else:
            # Unknown/lore item — show raw with note
            display = key.replace("_", " ").title()
            lines.append(f"**{display}**{count_str} — *sell to Hemlock to find out*")

    embed = discord.Embed(
        title="🎒 Inventory",
        description="\n".join(lines),
        color=0x8b7355
    )
    embed.set_footer(text="!rpg use <item>  ·  !rpg equip <item>  ·  !rpg sell <item>")
    await msg.channel.send(embed=embed)

async def _handle_equip(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import find_item
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    import discord
    if not rest.strip():
        return await msg.channel.send(embed=discord.Embed(description="Equip what? `!rpg equip <item>`", color=0x888888))
        
    item_key = rest.strip().lower()
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = ALIASES.get(item_key, item_key)
    if item_key not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(description=f"You don't have `{item_key}` in your inventory.", color=0xcc4444))
        
    item = find_item(item_key)
    if not item or item["category"] not in ["weapon", "armor"]:
        return await msg.channel.send(embed=discord.Embed(description=f"`{item_key}` cannot be equipped.", color=0xcc4444))
        
    # Unequip existing if slot filled
    slot = item["category"]
    if sheet["equipment"].get(slot):
        old = sheet["equipment"][slot]["key"]
        sheet["inventory"].append(old)
        
    # Equip new
    sheet["inventory"].remove(item_key)
    sheet["equipment"][slot] = item
    await asyncio.to_thread(save, sheet)
    
    await msg.channel.send(embed=discord.Embed(description=f"Equipped **{item['name']}** as {slot}.", color=0x44aa44))

async def _handle_use(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import find_item
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    item_key = rest.strip().lower()
    from utils.ttrpg.equipment_registry import ALIASES
    item_key = ALIASES.get(item_key, item_key)
        
    import discord
    if item_key not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(description=f"You don't have `{item_key}`.", color=0xcc4444))
        
    item = find_item(item_key)
    if not item or item["category"] != "consumable":
        return await msg.channel.send(embed=discord.Embed(description=f"You can't use `{item_key}`.", color=0xcc4444))
        
    if "hp_restore" in item and item["hp_restore"] > 0:
        before = sheet["hp"]["current"]
        sheet["hp"]["current"] = min(sheet["hp"]["current"] + item["hp_restore"], sheet["hp"]["max"])
        healed = sheet["hp"]["current"] - before
        sheet["inventory"].remove(item_key)
        await asyncio.to_thread(save, sheet)
        await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. Restored {healed} HP ({before} → {sheet['hp']['current']})", color=0x44aa44))
    elif item.get("on_use") == "starter_kit":
        sheet["inventory"].remove(item_key)
        sheet["inventory"].extend(["bandage", "healing_herb", "torch"])
        await asyncio.to_thread(save, sheet)
        await msg.channel.send(embed=discord.Embed(description=f"You open the **{item['name']}**.\n\nObtained:\n• Bandage\n• Healing Herb\n• Torch (lore item)", color=0x44aa44))
    elif item.get("on_use") == "cure_poison":
        if "poisoned" in sheet.get("conditions", []):
            sheet["conditions"].remove("poisoned")
            sheet["inventory"].remove(item_key)
            await asyncio.to_thread(save, sheet)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. The venom fades from your veins.", color=0x44aa44))
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You aren't poisoned.", color=0xcc4444))
    elif item.get("on_use") == "luck_roll_bonus":
        if "lucky" not in sheet.get("conditions", []):
            if "conditions" not in sheet: sheet["conditions"] = []
            sheet["conditions"].append("lucky")
            sheet["inventory"].remove(item_key)
            await asyncio.to_thread(save, sheet)
            await msg.channel.send(embed=discord.Embed(description=f"Used **{item['name']}**. You feel a sudden surge of confidence. (+1 to next hit roll)", color=0x44aa44))
        else:
            await msg.channel.send(embed=discord.Embed(description=f"You are already feeling pretty lucky.", color=0xcc4444))
    else:
        await msg.channel.send(embed=discord.Embed(description=f"**{item['name']}** can't be used. Try selling it: `!rpg sell {item_key}`", color=0xcc4444))


# ── Combat ───────────────────────────────────────────────────────────────────

async def _handle_hunts(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.progression import hunts_remaining, MAX_HUNTS_PER_DAY
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    import discord
    await msg.channel.send(embed=discord.Embed(description=f"**{sheet['character_name']}** has {hunts_remaining(sheet)} hunts remaining today. Reset is at midnight server time.", color=0x888888))

async def _handle_hunt(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.monster_registry import random_encounter, get as get_monster
    from utils.ttrpg.progression import hunts_remaining, check_and_reset_hunts, MAX_HUNTS_PER_DAY
    from utils.ttrpg.session_manager import load_session, save_session
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    loc = sheet.get("location", "oakhaven")
    ld = LOCATION_DATA.get(loc, {})
    import discord
    if not ld.get("hunting"):
        return await msg.channel.send(embed=discord.Embed(description=f"You can't hunt in **{ld.get('name', loc)}**.\nTravel somewhere wild first.", color=0xcc4444))
        
    sheet = check_and_reset_hunts(sheet)
    if hunts_remaining(sheet) <= 0:
        return await msg.channel.send(embed=discord.Embed(description=f"You have exhausted your stamina for the day. (0/{MAX_HUNTS_PER_DAY} hunts remaining)", color=0xcc4444))
        
    if sheet["hp"]["current"] <= 0:
        return await msg.channel.send(embed=discord.Embed(description=f"You are far too weak to hunt right now. Go rest.", color=0xcc4444))
        
    # Engage tracking
    chan_id = str(msg.channel.id)
    s = await asyncio.to_thread(load_session, chan_id)
    if not s:
        s = {"channel_id": chan_id, "monsters": [], "combat_active": False}
    
    # Quest Task Tracking: Hunt Location
    active_id = sheet.get("active_quest")
    if active_id:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active_id)
        if q:
            task_id = f"hunt_{loc}"
            if task_id in q["tasks"]:
                prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                if task_id not in prog:
                    prog.append(task_id)
                    # Note: We don't check for quest completion here (likely multiple tasks)
                    # but we save the progress.
                    await asyncio.to_thread(save, sheet)

    # Are we already fighting something?
    my_fights = [m for m in s.get("monsters", []) if m.get("aggro_uid") == uid]
    if my_fights:
        m_name = my_fights[0].get("name", "Unknown Monster")
        m_key = my_fights[0].get("key", "monster")
        import discord
        return await msg.channel.send(embed=discord.Embed(
            title="⚔️ Already in combat",
            description=f"You are already fighting a **{m_name}**.\n`!rpg attack {m_key}` · `!rpg flee`",
            color=0xcc6622
        ))
    
    # Roll for special forest event before monster spawn
    from utils.ttrpg.encounter_tables import roll_for_event, random_event
    from utils.ttrpg.forest_events import resolve_event

    if roll_for_event(loc):
        event_key = random_event(loc)
        result = resolve_event(event_key, sheet)
        # Pay the hunt cost
        sheet["hunts_today"] = sheet.get("hunts_today", 0) + 1
        await _apply_and_narrate_event(ctx, msg, send, sheet, result, uname)
        return  # event consumed the hunt, done

    # Pay hunt cost BEFORE spawn (crash-safe: hunt is consumed even if spawn fails)
    sheet["hunts_today"] = sheet.get("hunts_today", 0) + 1
    await asyncio.to_thread(save, sheet)

    # Spawn monsters based on density
    density = ld.get("density", 1)
    dist_mult = ld.get("dist_mult", 1.0)
    
    num_to_spawn = 1
    if density > 1:
        import random
        spawn_roll = random.random()
        if density == 2 and spawn_roll < 0.25:
            num_to_spawn = 2
        elif density == 3:
            if spawn_roll < 0.15: num_to_spawn = 3
            elif spawn_roll < 0.40: num_to_spawn = 2
            
    s.setdefault("channel_id", chan_id)
    spawned_names = []
    
    for _ in range(num_to_spawn):
        m_key = random_encounter(loc)
        m_data = get_monster(m_key)
        if not m_data: continue
        
        m_temp = m_data.copy()
        m_temp["key"] = m_key
        # Apply distance difficulty scaling
        scaled_hp = int(m_temp["hp"] * dist_mult)
        m_temp["hp"] = {"current": scaled_hp, "max": scaled_hp}
        m_temp["attack"] = int(m_temp.get("attack", 0) * dist_mult)
        m_temp["id"] = f"{m_key}_{_uuid.uuid4().hex[:4]}"
        m_temp["aggro_uid"] = uid  # personal instance
        
        s["monsters"].append(m_temp)
        spawned_names.append(f"**{m_temp['name']}**")

    s["combat_active"] = True
    await asyncio.to_thread(save_session, s)
    
    from utils.ttrpg.rpg_ui import TIER_ICONS
    
    rec = ld.get("recommended_level", 1)
    warn = f"⚠️ *{sheet['character_name']} is underleveled for this area.*\n" if sheet["level"] < rec - 1 else ""
    
    monster_desc = m_data.get("desc", m_data.get("description", "A dangerous creature."))
    tier_icon = TIER_ICONS.get(m_data.get("tier", "medium"), "🟠")
    
    if num_to_spawn > 1:
        title = f"⚔️ Encounter: SWARM! {tier_icon}"
        description = f"{warn}You are surrounded by a group: {', '.join(spawned_names)}\n\n*{monster_desc}*"
    else:
        title = f"⚔️ Encounter: {m_data['name']} {tier_icon}"
        description = f"{warn}*{monster_desc}*"

    embed = discord.Embed(
        title=title,
        description=description,
        color=0xFF4500 if num_to_spawn == 1 else 0xCC3300
    )
    
    # Show stats of the primary (first) monster
    embed.add_field(name="❤️ HP", value=str(m_temp['hp']['max']), inline=True)
    embed.add_field(name="🗡️ ATK", value=str(m_data.get('attack', 0)), inline=True)
    embed.add_field(name="🛡️ DEF", value=str(m_data.get('defense', 0)), inline=True)
    
    embed.set_footer(text=f"Use !rpg attack  ·  1 hunt consumed")
    await msg.channel.send(embed=embed)

async def _handle_attack(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.session_manager import load_session, save_session
    from utils.ttrpg.combat_engine import _resolve_combat
    from utils.ttrpg.rpg_prompt_builder import build_combat_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    from utils.social.kaia_social_responder import load_persona_async
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from utils.ttrpg.loot_tables import get_loot
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    import discord
    if sheet["hp"]["current"] <= 0:
        return await msg.channel.send(embed=discord.Embed(description="You are incapacitated.", color=0xcc4444))
        
    s = await asyncio.to_thread(load_session, str(msg.channel.id))
    if not s or not s.get("combat_active") or not s.get("monsters"):
        return await msg.channel.send(embed=discord.Embed(description="No active combat. `!rpg hunt` to find something.", color=0x888888))
        
    target_key = rest.strip().lower()
    
    monster = None
    monster_idx = -1
    for i, m in enumerate(s["monsters"]):
        # Prioritize engaging enemies aggro'd onto THIS player
        m_key = m.get("key", "")
        if m.get("aggro_uid") == uid or (target_key and target_key in m_key):
            monster = m
            monster_idx = i
            break
            
    if not monster:
        return await msg.channel.send(embed=discord.Embed(description="Cannot identify monster.", color=0xcc4444))
        
    # Execute deterministic combat math loop
    res = _resolve_combat(sheet, monster)
    
    sheet = res["sheet"]
    monster = res["monster"]

    # After combat resolves, consume the blessing
    if "blessed" in sheet.get("conditions", []):
        sheet["conditions"].remove("blessed")
    
    # Handle state cleanup
    if res["monster_defeated"] or not res["player_alive"]:
        s["monsters"].pop(monster_idx)
        if not s["monsters"]: s["combat_active"] = False
    else:
        s["monsters"][monster_idx] = monster
        
    await asyncio.to_thread(save_session, s)
    
    xp_gain, gil_gain, level_up_msg, loot_msg, streak_msg = 0, 0, "", "", ""
    if res["monster_defeated"]:
        xp_gain = monster.get("xp", 10)
        gil_gain = monster.get("gil", 5)
        
        # Streak mechanics
        streak = sheet.get("hunt_streak", 0) + 1
        sheet["hunt_streak"] = streak
        if streak > 1:
            streak_bonus_gil = streak * 2
            gil_gain += streak_bonus_gil
            streak_msg = f"  🔥 Streak: {streak} (+{streak_bonus_gil}g)"
            
        # Loot mechanics
        loot = get_loot(monster.get("tier", "medium"))
        if loot:
            sheet.setdefault("inventory", []).append(loot)
            from utils.ttrpg.shop import find_item as _find_loot
            loot_info = _find_loot(loot)
            loot_display = loot_info["name"] if loot_info else loot
            loot_msg = f"\n🎁 **Looted:** {loot_display}"
            
            # Log rare drop if it's high tier or specific items
            tier = monster.get("tier", "medium")
            if tier in ["hard", "deadly", "boss"]:
                await _log_world_event(f"A **{loot_display}** was recovered from the {LOCATION_DATA.get(loc, {}).get('name', loc)}. Oakhaven listens carefully.")
            
        sheet["xp"] += xp_gain
        sheet["gil"] += gil_gain
        
        # Quest Task Tracking: Kill
        active_id = sheet.get("active_quest")
        if active_id:
            from utils.ttrpg.quest_registry import get_quest
            q = get_quest(active_id)
            if q:
                monster_id = monster.get("key")
                task_id = f"kill_{monster_id}"
                if task_id in q["tasks"]:
                    prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                    if task_id not in prog:
                        prog.append(task_id)
                        # Check Completion
                        if all(t in prog for t in q["tasks"]):
                            # Complete!
                            sheet["xp"] += q["rewards"].get("xp", 0)
                            sheet["gil"] += q["rewards"].get("gil", 0)
                            if "item" in q["rewards"]:
                                sheet.setdefault("inventory", []).append(q["rewards"]["item"])
                            if "recipe" in q["rewards"]:
                                r_key = q["rewards"]["recipe"]
                                if r_key not in sheet.setdefault("recipes", []):
                                    sheet.setdefault("recipes", []).append(r_key)
                            sheet["active_quest"] = None
                            sheet.setdefault("completed_quests", []).append(active_id)
                            await _log_world_event(f"**{sheet['character_name']}** completed '**{q['name']}**'.")
                            # Quest completion message will be added to m_block below
                        else:
                            await asyncio.to_thread(save, sheet)
        leveled, n_lvl = check_level_up(sheet)
        if leveled: 
            level_up_msg = f"\n🎉 **LEVEL UP! {sheet['character_name']} grew to level {n_lvl}!**"
            await _log_world_event(f"**{sheet['character_name']}** reached Level {n_lvl}. Oakhaven noted it cautiously.")
        
    await asyncio.to_thread(save, sheet)
    
    # Emit Math block
    m_block = "\n".join(res["exchanges"])
    
    # Add Quest completion message if it was finished in this attack
    if res["monster_defeated"] and active_id:
        from utils.ttrpg.quest_registry import get_quest
        q = get_quest(active_id)
        if q and q["id"] not in sheet.get("active_quest", ""): # active_quest is None if complete
             if active_id in sheet.get("completed_quests", []):
                 m_block += f"\n🏆 **Quest Complete: {q['name']}!**"

    if res["monster_defeated"]:
        nx = xp_to_next_level(sheet["level"])
        m_block += f"\n+{xp_gain} XP ({sheet['xp']}/{nx})  +{gil_gain} Gil{streak_msg}{loot_msg}{level_up_msg}"
    elif not res["player_alive"]:
        sheet["hunt_streak"] = 0
        xp_loss = int(sheet["xp"] * 0.10)
        gil_loss = int(sheet["gil"] * 0.05)
        sheet["xp"] = max(0, sheet["xp"] - xp_loss)
        sheet["gil"] = max(0, sheet["gil"] - gil_loss)
        sheet["hp"]["current"] = 1
        sheet["location"] = "shrine"
        sheet["deaths"] = sheet.get("deaths", 0) + 1
        m_block += f"\n\n🚨 **You blacked out.** Townspeople dragged you back to the Shrine of the Silent Ones in Oakhaven. You dropped {xp_loss} XP and {gil_loss} Gil in the dirt."
        await _log_world_event(f"**{sheet['character_name']}** was found at the Shrine threshold. Hemlock is taking bets.")
        
    await asyncio.to_thread(save, sheet)
    
    import discord
    embed_color = 0xFF4500 if res["monster_alive"] else 0x2D5A27
    if not res["player_alive"]:
        embed_color = 0x8B0000

        
    embed = discord.Embed(
        title="⚔️ Combat Log",
        description=m_block,
        color=embed_color
    )
    await msg.channel.send(embed=embed)
    
    # Kaia Narration Generation
    monster_desc = monster.get("desc", monster.get("description", "A dangerous creature."))
    truth = build_combat_prompt(
        sheet, monster["name"], monster_desc,
        res["player_hit"], res["player_crit"], res["player_fumble"], res.get("player_damage", 0),
        res["monster_alive"], res["monster_hit"], res["monster_damage"],
        res["player_alive"], sheet["hp"]["current"], sheet["hp"]["max"],
        sheet["hp"]["current"] / max(1, sheet["hp"]["max"])
    )
    
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{truth}"},
        {"role": "user", "content": f"{uname} engages."}
    ]
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 150
    opts["temperature"] = 0.85
    
    async with msg.channel.typing():
        try:
            nar = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=45.0
                ),
                task_id=f"rpg_fight_{_uuid.uuid4().hex[:8]}"
            )
            narr = nar["message"]["content"].strip().replace("```", "")
            if narr: await send(msg.channel, f"*{narr}*")
        except:
            pass

async def _handle_flee(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.session_manager import load_session, save_session
    import secrets
    import discord

    s = await asyncio.to_thread(load_session, str(msg.channel.id))
    if not s or not s.get("combat_active"): return
    
    to_flee = -1
    for i, m in enumerate(s.get("monsters", [])):
        if m.get("aggro_uid") == uid:
            to_flee = i
            break
            
    if to_flee == -1: return await msg.channel.send(embed=discord.Embed(description="You have nothing chasing you.", color=0xcc4444))
    
    roll = secrets.randbelow(20) + 1
    if roll >= 10:
        s["monsters"].pop(to_flee)
        if not s["monsters"]: s["combat_active"] = False
        await asyncio.to_thread(save_session, s)
        await msg.channel.send(embed=discord.Embed(description=f"🏃 **{uname}** scrambled to safety! (d20 = {roll})", color=0x44aa44))
    else:
        await msg.channel.send(embed=discord.Embed(description=f"❌ Flee failed! (d20 = {roll}) You trip. They close the distance.", color=0xcc4444))


async def _apply_and_narrate_event(ctx, msg, send, sheet, result, uname):
    """Apply a forest event's mechanical effects and trigger Kaia narration."""
    from utils.ttrpg.character_manager import save
    from utils.ttrpg.progression import check_level_up, xp_to_next_level, MAX_HUNTS_PER_DAY, hunts_remaining

    # Apply mechanical changes
    sheet["xp"]  = sheet.get("xp", 0) + result["xp"]
    sheet["gil"] = sheet.get("gil", 0) + result["gil"]

    if result["hp_change"] != 0:
        sheet["hp"]["current"] = max(0, min(
            sheet["hp"]["current"] + result["hp_change"],
            sheet["hp"]["max"]
        ))

    if result["condition_add"]:
        sheet.setdefault("conditions", [])
        if result["condition_add"] not in sheet["conditions"]:
            sheet["conditions"].append(result["condition_add"])

    if result["condition_remove"] and result["condition_remove"] in sheet.get("conditions", []):
        sheet["conditions"].remove(result["condition_remove"])

    if result["extra_hunt"]:
        sheet["hunts_today"] = max(0, sheet.get("hunts_today", 1) - 1)  # refund 1 hunt

    if result["item_add"]:
        sheet.setdefault("inventory", []).append(result["item_add"])

    leveled_up, new_level = check_level_up(sheet)
    await asyncio.to_thread(save, sheet)

    # Post mechanical result as embed (matches combat log card style)
    import discord
    xp_next = xp_to_next_level(sheet["level"])

    event_colors = {
        "sylvan_sprites":    0x88eea8,   # soft green
        "moogle_sighting":   0xf5c842,   # moogle yellow
        "injured_silvani":   0x7ec8e3,   # blue-grey
        "old_man_riddle":    0xb8a0d8,   # purple
        "chocobo_tracks":    0xf0d060,   # chocobo yellow
        "aeridor_fragment":  0x80d8ff,   # crystal blue
        "gilded_mushroom":   0xd4a843,   # gold
        "veiled_elder":      0xc0c0d8,   # silver-pale
        "timid_tonberry":    0x88bb88,   # muted green
        "mognet_delivery":   0xf4a460,   # sandy orange
        "crystal_resonance": 0x9988dd,   # resonance purple
    }
    color = event_colors.get(result.get("event_key", ""), 0xaaaaaa)

    body_lines = [f"*{result['outcome']}*"]
    if result["xp"]:
        body_lines.append(f"+{result['xp']} XP ({sheet['xp']}/{xp_next})")
    if result["gil"]:
        body_lines.append(f"+{result['gil']} Gil  (total: {sheet['gil']}g)")
    if result["hp_change"] > 0:
        body_lines.append(f"+{result['hp_change']} HP  ({sheet['hp']['current']}/{sheet['hp']['max']})")
    if result["hp_change"] < 0:
        body_lines.append(f"{result['hp_change']} HP  ({sheet['hp']['current']}/{sheet['hp']['max']})")
    if result["extra_hunt"]:
        body_lines.append(f"🎯 Hunts remaining: {hunts_remaining(sheet)}/{MAX_HUNTS_PER_DAY}")
    if result["item_add"]:
        body_lines.append(f"📦 Added to inventory: `{result['item_add']}`")

    embed = discord.Embed(
        title=result["title"],
        description="\n".join(body_lines),
        color=color
    )

    await msg.channel.send(embed=embed)

    if leveled_up:
        import discord
        await msg.channel.send(embed=discord.Embed(
            description=f"🎉 **{sheet['character_name']} reached Level {new_level}!**",
            color=0xffcc00
        ))

    # Kaia narrates
    if result.get("narration_hook"):
        from utils.ttrpg.rpg_prompt_builder import build_event_narration_prompt
        from utils.social.kaia_social_responder import load_persona_async
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
        from utils.infrastructure.system.yaml_config import config
        import uuid as _uuid

        prompt = build_event_narration_prompt(
            sheet=sheet,
            event_title=result["title"],
            narration_hook=result["narration_hook"],
        )
        persona = await load_persona_async()
        messages = [
            {"role": "system", "content": f"{persona}\n\n{prompt}"},
            {"role": "user",   "content": f"{uname} is in the {sheet.get('location', 'forest')}."}
        ]
        gpu_manager = OllamaGPUManager(config.chat_model)
        opts = gpu_manager.get_gpu_options(for_chat=True)
        opts["num_predict"] = 120
        opts["temperature"] = 0.9

        async with msg.channel.typing():
            try:
                resp = await gpu_memory_manager.run_with_gpu_guard(
                    model_name=config.chat_model,
                    priority=GPUTaskPriority.CHAT,
                    coro=asyncio.wait_for(
                        ctx.ollama_client.chat(
                            model=config.chat_model,
                            messages=messages,
                            options=opts,
                            keep_alive=-1
                        ),
                        timeout=45.0
                    ),
                    task_id=f"rpg_event_{_uuid.uuid4().hex[:8]}"
                )
                narration = resp["message"]["content"].strip().replace("```", "")
                if narration:
                    import discord
                    embed = discord.Embed(
                        description=f"*{narration}*",
                        color=0x4488cc
                    )
                    await msg.channel.send(embed=embed)
            except Exception as e:
                log_error(f"[rpg event narration] {e}")


async def _handle_drink(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg drink — buy an ale at the Stone Hearth. Costs 2 gil, +3 temporary HP."""
    from utils.ttrpg.character_manager import load, save

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Stone Hearth to drink.\n`!rpg go stone_hearth`", 
            color=0xcc4444
        ))

    DRINK_COST = 2
    if sheet.get("gil", 0) < DRINK_COST:
        return await msg.channel.send(embed=discord.Embed(
            description=f"Mira glances at your coin purse and shakes her head.\nAn ale costs {DRINK_COST} gil. You have {sheet.get('gil', 0)}g.",
            color=0xcc4444
        ))

    # Grant temp HP by raising max temporarily (tracked via condition)
    TEMP_HP = 3
    already_drinking = any("ale" in c.lower() for c in sheet.get("conditions", []))
    if already_drinking:
        return await msg.channel.send(embed=discord.Embed(
            description="*Mira refills the tankard without comment.*\nYou're already feeling the first one. Another won't stack.",
            color=0x888888
        ))

    sheet["gil"] -= DRINK_COST
    sheet["hp"]["max"] += TEMP_HP
    sheet["hp"]["current"] = min(sheet["hp"]["current"] + TEMP_HP, sheet["hp"]["max"])
    sheet.setdefault("conditions", []).append("ale_warmth")  # removed on next rest
    await asyncio.to_thread(save, sheet)

    await msg.channel.send(embed=discord.Embed(
        description=f"🍺 Mira slides a tankard across the bar. (-{DRINK_COST} gil)\n*Temporary HP: +{TEMP_HP}* (HP: {sheet['hp']['current']}/{sheet['hp']['max']})\n*Clears when you next rest.*",
        color=0x44aa44
    ))


async def _handle_fountain(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg fountain — drink from the healing spring at the Shrine. Once per day, full heal."""
    from utils.ttrpg.character_manager import load, save
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones to drink from the fountain.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    today = date.today().strftime("%Y-%m-%d")
    if sheet.get("last_fountain_date") == today:
        return await msg.channel.send(embed=discord.Embed(
            description="💧 *The spring's waters are still. You've already partaken today.*\nIts magic needs time to replenish.",
            color=0x888888
        ))

    sheet["hp"]["current"] = sheet["hp"]["max"]
    sheet["last_fountain_date"] = today
    await asyncio.to_thread(save, sheet)

    await msg.channel.send(embed=discord.Embed(
        description=f"💧 **{sheet['character_name']} drinks from the spring.**\nYour wounds stitch closed. You are fully recovered. (HP: {sheet['hp']['current']}/{sheet['hp']['max']})\n*Clears when you next rest.*",
        color=0x44aa44
    ))


async def _handle_gamble(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg gamble — dice game at the Stone Hearth. 10 gil buy-in."""
    import secrets as _sec
    from utils.ttrpg.character_manager import load, save

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="The dice game only happens at the Stone Hearth.\n`!rpg go stone_hearth`", 
            color=0xcc4444
        ))

    BUY_IN = 10
    if sheet.get("gil", 0) < BUY_IN:
        return await msg.channel.send(embed=discord.Embed(
            description=f"The buy-in is {BUY_IN} gil. you have {sheet.get('gil', 0)}g.\n*A weathered man across the table doesn't look up from his cards.*",
            color=0xcc4444
        ))

    # Roll d6 vs d6. Tie goes to house.
    player_roll = _sec.randbelow(6) + 1
    house_roll  = _sec.randbelow(6) + 1

    sheet["gil"] -= BUY_IN

    if player_roll > house_roll:
        winnings = BUY_IN * 2
        sheet["gil"] += winnings
        result_line = f"🎲 You rolled **{player_roll}**, they rolled **{house_roll}**. You win!"
        gil_line = f"+{BUY_IN} gil (net). Total: {sheet['gil']}g"
    elif player_roll < house_roll:
        result_line = f"🎲 You rolled **{player_roll}**, they rolled **{house_roll}**. You lose."
        gil_line = f"-{BUY_IN} gil. Total: {sheet['gil']}g"
    else:
        result_line = f"🎲 You both rolled **{player_roll}**. House takes ties."
        gil_line = f"-{BUY_IN} gil. Total: {sheet['gil']}g"

    await asyncio.to_thread(save, sheet)
    await msg.channel.send(embed=discord.Embed(
        description=f"{result_line}\n{gil_line}",
        color=0x44aa44 if player_roll > house_roll else 0xcc4444
    ))


async def _handle_pray(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg pray — once per day blessing at the Shrine of the Silent Ones."""
    from utils.ttrpg.character_manager import load, save
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones to pray.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    # Once per day check
    today = date.today().strftime("%Y-%m-%d")
    last_pray = sheet.get("last_pray_date", "")
    if last_pray == today:
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *The shrine is still. You've already made your offering today.*\nThe Silent Ones do not answer twice.",
            color=0x888888
        ))

    # Check if already blessed
    if "blessed" in sheet.get("conditions", []):
        return await msg.channel.send(embed=discord.Embed(
            description="🕯️ *You are already carrying the blessing of the Silent Ones.*\nUse it before asking for more.",
            color=0x888888
        ))

    sheet.setdefault("conditions", []).append("blessed")
    sheet["last_pray_date"] = today
    await asyncio.to_thread(save, sheet)

    await msg.channel.send(embed=discord.Embed(
        description="🕯️ **Blessed** — *the shrine acknowledges you.*\nYour next hunt grants +2 to all attack and stat rolls.\n*The condition clears after your next combat.*",
        color=0xaaddff
    ))


async def _handle_offer(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg offer <amount> — donate gil to the shrine for XP."""
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "shrine":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Shrine of the Silent Ones.\n`!rpg go shrine`",
            color=0xcc4444
        ))

    try:
        amount = int(rest.strip())
        assert 1 <= amount <= 9999
    except:
        return await msg.channel.send(embed=discord.Embed(description="Usage: `!rpg offer <amount>`\nExample: `!rpg offer 20`", color=0x888888))

    if sheet.get("gil", 0) < amount:
        return await msg.channel.send(embed=discord.Embed(
            description=f"You only have {sheet.get('gil', 0)} gil.\n*The shrine doesn't judge. It just waits.*",
            color=0xcc4444
        ))

    # XP reward: 1 per gil, capped at 20 per day
    today = date.today().strftime("%Y-%m-%d")
    offered_today = sheet.get("offered_today", {})
    if isinstance(offered_today, dict):
        already_offered = offered_today.get(today, 0)
    else:
        already_offered = 0

    DAILY_CAP = 20
    eligible = min(amount, max(0, DAILY_CAP - already_offered))
    xp_gained = eligible  # 1 XP per gil

    sheet["gil"] -= amount
    sheet["xp"] += xp_gained

    # Track daily offering
    sheet["offered_today"] = {today: already_offered + amount}

    leveled_up, new_level = check_level_up(sheet)
    await asyncio.to_thread(save, sheet)

    xp_next = xp_to_next_level(sheet["level"])
    msg_lines = [
        f"🕯️ **{sheet['character_name']}** offers {amount} gil to the Silent Ones.",
        f"*The coins vanish. The air shifts slightly.*",
        f"+{xp_gained} XP ({sheet['xp']}/{xp_next})",
    ]
    if eligible < amount:
        msg_lines.append(f"*(daily offering cap reached — {DAILY_CAP} XP max per day)*")
    if leveled_up:
        msg_lines.append(f"\n🎉 **{sheet['character_name']} reached Level {new_level}!**")

    await msg.channel.send(embed=discord.Embed(
        description="\n".join(msg_lines),
        color=0xaaddff
    ))


async def _handle_scout(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg scout — use the Watchtower to preview monster activity."""
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.monster_registry import MONSTERS, ENCOUNTER_TABLES
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") != "watchtower":
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be at the Watchtower to scout.\n`!rpg go watchtower`",
            color=0xcc4444
        ))

    # Once per day
    today = date.today().strftime("%Y-%m-%d")
    if sheet.get("last_scout_date") == today:
        return await msg.channel.send(embed=discord.Embed(
            description="🗼 *The guards shrug. You've already had your look today.*\nCome back tomorrow.",
            color=0x888888
        ))

    sheet["last_scout_date"] = today
    await asyncio.to_thread(save, sheet)

    # Build intel report from encounter tables
    HUNTING_LOCATIONS = {
        "whisperwood_edge": "Edge of the Whisperwood",
        "whisperwood_deep": "Whisperwood Deep",
        "aeridor_ruins":    "Aeridor Ruins",
        "trade_road":       "The Trade Road",
    }

    lines = ["🗼 **Scout Report** — *from the top of the Watchtower*\n"]

    for loc_key, loc_name in HUNTING_LOCATIONS.items():
        table = ENCOUNTER_TABLES.get(loc_key, [])
        if not table:
            continue

        # Tally tier distribution by weight
        tier_weights: dict[str, int] = {}
        total_weight = sum(w for _, w in table)
        for monster_key, weight in table:
            tier = MONSTERS.get(monster_key, {}).get("tier", "unknown")
            tier_weights[tier] = tier_weights.get(tier, 0) + weight

        # Most common tier
        dominant_tier = max(tier_weights, key=tier_weights.get)
        dominant_pct = int(tier_weights[dominant_tier] / total_weight * 100)

        # Named preview: highest-weight monster
        top_monster_key = max(table, key=lambda x: x[1])[0]
        top_monster = MONSTERS.get(top_monster_key, {})

        # Danger indicator
        danger = {
            "trivial": "🟢", "easy": "🟡",
            "medium": "🟠", "hard": "🔴", "deadly": "💀"
        }.get(dominant_tier, "⚪")

        lines.append(
            f"{danger} **{loc_name}**\n"
            f"   Mostly {dominant_tier} ({dominant_pct}%) — "
            f"*spotted: {top_monster.get('name', top_monster_key)}*"
        )

    lines.append(
        f"\n*A guard leans on his spear without looking at you.*\n"
        f"*\"Whisperwood's been louder than usual. Watch yourself.\"*"
    )

    await msg.channel.send(embed=discord.Embed(
        description="\n".join(lines),
        color=0x8888aa
    ))


async def _handle_deliver(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg deliver — turn in a mognet letter in Oakhaven."""
    from utils.ttrpg.character_manager import load, save

    sheet = await asyncio.to_thread(load, uid)
    import discord
    if not sheet:
        return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    if sheet.get("location") not in ("oakhaven", "stone_hearth"):
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be in Oakhaven to deliver the letter.",
            color=0xcc4444
        ))

    if "mognet_letter" not in sheet.get("inventory", []):
        return await msg.channel.send(embed=discord.Embed(
            description="You don't have a mognet letter to deliver.",
            color=0xcc4444
        ))

    reward_gil = 25
    reward_xp  = 20
    sheet["inventory"].remove("mognet_letter")
    if "mognet_pending" in sheet.get("conditions", []):
        sheet["conditions"].remove("mognet_pending")
    sheet["gil"] += reward_gil
    sheet["xp"]  += reward_xp

    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    leveled_up, new_level = check_level_up(sheet)
    await asyncio.to_thread(save, sheet)

    xp_next = xp_to_next_level(sheet["level"])
    embed = discord.Embed(
        description=f"📬 **Mognet letter delivered.**\n*A moogle materialises briefly, takes the letter, says 'kupo' with visible relief, and presses a coin purse into your hand before vanishing.*\n+{reward_xp} XP ({sheet['xp']}/{xp_next})  +{reward_gil} Gil",
        color=0xf4a460
    )
    await msg.channel.send(embed=embed)

    if leveled_up:
        await msg.channel.send(embed=discord.Embed(
            description=f"🎉 **{sheet['character_name']} reached Level {new_level}!**",
            color=0xffcc00
        ))


# ── Administration & Overrides ───────────────────────────────────────────────


async def _handle_roll(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dice_engine import roll
    try:
        total, breakdown = roll(rest.strip() or "d20")
        import discord
        await msg.channel.send(embed=discord.Embed(
            description=f"🎲 **{uname}** rolled `{rest.strip() or 'd20'}`: {breakdown}",
            color=0x4488cc
        ))
    except:
        await msg.channel.send(embed=discord.Embed(description="Invalid syntax", color=0xcc4444))

async def _handle_bestiary(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.monster_registry import format_bestiary
    await send(msg.channel, format_bestiary(), use_code_block=False)

async def _handle_xp(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    import discord
    await msg.channel.send(embed=discord.Embed(
        description="Developer override required to assign arbitrary XP in Aethelgard. Go hunt.",
        color=0xcc4444
    ))

async def _handle_give(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import find_item
    args = rest.strip().split()
    if not args: return
    sheet = await asyncio.to_thread(load, str(msg.mentions[0].id) if msg.mentions else uid)
    if not sheet: return
    item = find_item(args[0])
    if item:
        sheet["inventory"].append(args[0])
        await asyncio.to_thread(save, sheet)
        import discord
        await msg.channel.send(embed=discord.Embed(
            description=f"Admin granted `{args[0]}` to {sheet['character_name']}.",
            color=0x44aa44
        ))

async def _handle_heal(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.character_manager import load, save
    sheet = await asyncio.to_thread(load, str(msg.mentions[0].id) if msg.mentions else uid)
    if not sheet: return
    sheet["hp"]["current"] = sheet["hp"]["max"]
    await asyncio.to_thread(save, sheet)
    import discord
    await msg.channel.send(embed=discord.Embed(
        description=f"Admin fully healed {sheet['character_name']}.",
        color=0x44aa44
    ))


async def _handle_leaderboard(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg leaderboard — show all characters ranked by XP."""
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.rpg_ui import CLASS_ICONS, LOCATION_ICONS
    import discord

    sheets = await asyncio.to_thread(load_all)
    if not sheets:
        return await msg.channel.send(embed=discord.Embed(description="No adventurers have been created yet.", color=0x888888))

    # Sort by XP descending, then by level descending
    sheets.sort(key=lambda s: (s.get("xp", 0), s.get("level", 1)), reverse=True)

    MEDALS = ["🥇", "🥈", "🥉"]
    lines = []
    for i, s in enumerate(sheets[:15]):  # cap at 15 entries
        medal = MEDALS[i] if i < 3 else f"`{i+1}.`"
        cls_icon = CLASS_ICONS.get(s.get("class", ""), "⚔️")
        loc_key = s.get("location", "oakhaven")
        loc_icon = LOCATION_ICONS.get(loc_key, "🗟a️")
        loc_name = LOCATION_DATA.get(loc_key, {}).get("name", loc_key.replace("_", " ").title())
        deaths = s.get("deaths", 0)
        race = s.get("race", "Unknown")

        line = (
            f"{medal} {cls_icon} **{s.get('character_name', '???')}**\n"
            f"  {race} {s.get('class', '???')} · Lv.{s.get('level', 1)} · {s.get('xp', 0)} XP\n"
            f"  💀 {deaths} death{'s' if deaths != 1 else ''} · {loc_icon} {loc_name}"
        )
        lines.append(line)

    embed = discord.Embed(
        title="🏆  AETHELGARD LEADERBOARD",
        description="\n\n".join(lines),
        color=0xd4a843  # gold
    )
    embed.set_footer(text=f"{len(sheets)} adventurer{'s' if len(sheets) != 1 else ''} registered")

    await msg.channel.send(embed=embed)

async def _handle_event(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    if not rest.strip(): return
    description = rest.strip()
    
    # Log to Notice Board
    await _log_world_event(f"📣 **WORLD EVENT:** {description}")
    
    from utils.ttrpg.rpg_prompt_builder import build_event_prompt
    from utils.social.kaia_social_responder import load_persona_async
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    prompt = build_event_prompt(rest.strip())
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": "Narrate the event."}
    ]
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 250
    opts["temperature"] = 0.85
    
    async with msg.channel.typing():
        try:
            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(model=config.chat_model, messages=messages, options=opts, keep_alive=-1),
                    timeout=60.0
                ),
                task_id=f"rpg_event_{_uuid.uuid4().hex[:8]}"
            )
            narr = resp["message"]["content"].strip().replace("```", "")
            if narr: await send(msg.channel, f"🌍 **WORLD EVENT**\n*{narr}*")
        except Exception as e:
            log_error(f"[rpg event] {e}")

async def _handle_rpg_help(ctx, msg, send, rest, uid, uname, is_owner):
    import discord
    embed = discord.Embed(
        title="📜 Aethelgard Command List",
        description=__doc__.strip(),
        color=0x44aa88
    )
    await msg.channel.send(embed=embed)
