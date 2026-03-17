"""
!rpg command handler — Aethelgard Persistent World System

WORLD & MOVEMENT
  !rpg                       — status and location
  !rpg go <location>         — travel
  !rpg look                  — narrate current location
  !rpg map                   — show accessible locations

CHARACTER
  !rpg new <Name> <Race> <Class>  — create character
  !rpg sheet [@user]              — view sheet

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
from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning
from utils.infrastructure.system.yaml_config import config

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
    if not sheet:
        await send(msg.channel, "you do not exist in Aethelgard. type `!rpg new <Name> <Race> <Class>` to begin.")
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
    
    footer_text = "!rpg look · !rpg map · !rpg shop"
    if loc_data.get("hunting"):
        footer_text += " · !rpg hunt"
    embed.set_footer(text=footer_text)
    
    await msg.channel.send(embed=embed)


# ── Character Management ─────────────────────────────────────────────────────

async def _handle_new(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, create, format_sheet
    from utils.ttrpg.dice_engine import roll, CLASSES
    
    existing = await asyncio.to_thread(load, uid)
    if existing:
        await send(msg.channel,
            f"you already have a character: **{existing['character_name']}**. "
            f"sheets are permanent.")
        return
    
    args = rest.split()
    if len(args) < 3:
        class_list = ", ".join(CLASSES.keys())
        await send(msg.channel,
            f"usage: `!rpg new <Name> <Race> <Class>`\nclasses: {class_list}")
        return
    
    char_name = args[0]
    race = args[1].title()
    class_name = args[2].title()
    
    if class_name not in CLASSES:
        class_list = ", ".join(CLASSES.keys())
        await send(msg.channel, f"unknown class. options: {class_list}")
        return
    
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
    
    await send(msg.channel,
        f"**{char_name}**, the {race} {class_name}, has entered Aethelgard.\n\n"
        f"**Stat rolls (4d6 drop lowest + Race bonuses):**\n```\n" +
        "\n".join(roll_log) + "\n```\n\n" +
        f"\nYou awaken in Oakhaven Town Square. Type `!rpg` to view your HUD.")

async def _handle_sheet(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, format_sheet
    target_id = str(msg.mentions[0].id) if msg.mentions else uid
    sheet = await asyncio.to_thread(load, target_id)
    if not sheet:
        await send(msg.channel, "character not found.")
        return
    await send(msg.channel, format_sheet(sheet))


# ── World & Movement ─────────────────────────────────────────────────────────

async def _handle_go(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.world import LOCATION_DATA, resolve_location
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return await send(msg.channel, "No character found.")
    
    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})

    if not rest.strip():
        exits = current_loc.get("exits", [])
        exit_lines = "\n".join(
            f"  `!rpg go {key}` — {LOCATION_DATA[key]['name']}"
            for key in exits
            if key in LOCATION_DATA
        )
        return await send(msg.channel,
            f"**{current_loc.get('name', current_loc_key)}** — where to?\n\n{exit_lines}")
        
    target = resolve_location(rest.strip())
    current = sheet.get("location", "oakhaven")
    current_data = LOCATION_DATA.get(current, {})
    
    if not target or target not in current_data.get("exits", []):
        available = " · ".join(LOCATION_DATA.get(e, {}).get("name", e) for e in current_data.get("exits", []))
        return await send(msg.channel, f"You can't reach that from here. Available exits:\n{available}")
        
    sheet["location"] = target
    await asyncio.to_thread(save, sheet)
    
    name = LOCATION_DATA.get(target, {}).get("name", target)
    await send(msg.channel, f"🚶 **{sheet['character_name']}** travels to **{name}**.\nType `!rpg look` to observe the surroundings.")

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
    
    await send(msg.channel,
        f"**{current_loc.get('name', current_loc_key)}** — nearby locations:\n\n{exit_lines}\n\n"
        f"*(Use `!rpg go <location>` to travel)*")


# ── Economy / NPCs / World Iterations ───────────────────────────────────────

async def _handle_rest(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    if sheet.get("location") != "stone_hearth":
        return await send(msg.channel, "You need to be at the Stone Hearth inn to rest. (`!rpg go stone_hearth`)")
        
    cost = 5
    if sheet.get("gil", 0) < cost:
        return await send(msg.channel, f"Mira shakes her head. \"Beds aren't free.\"\nYou need {cost} gil. You have {sheet.get('gil', 0)}g.")
        
    hp_cur = sheet["hp"]["current"]
    hp_max = sheet["hp"]["max"]
    
    has_ale = "ale_warmth" in sheet.get("conditions", [])
    if hp_cur >= hp_max and not has_ale:
        return await send(msg.channel, f"**{sheet['character_name']}** is already at maximum health.\nMira raises an eyebrow. *\"You're paying for a room you won't use?\"*")

    # Clear ale temp HP and condition BEFORE healing
    if "ale_warmth" in sheet.get("conditions", []):
        sheet["conditions"].remove("ale_warmth")
        sheet["hp"]["max"] -= 3  # remove the temp bonus
        sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])

    healed = sheet["hp"]["max"] - sheet["hp"]["current"]
    sheet["hp"]["current"] = sheet["hp"]["max"]
    sheet["gil"] -= cost

    await asyncio.to_thread(save, sheet)
    
    await send(msg.channel, f"🛏️ **{sheet['character_name']}** rests at the Stone Hearth. (-{cost} gil)\nHP restored: **+{healed}** (Full)\nRemaining gil: {sheet['gil']}g")

async def _handle_rumor(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.rpg_prompt_builder import build_rumor_prompt
    from utils.social.kaia_social_responder import load_persona_async
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await asyncio.to_thread(load, uid)
    if sheet and sheet.get("location") != "stone_hearth":
        return await send(msg.channel, "You must be at the Stone Hearth to hear rumors. (`!rpg go stone_hearth`)")
        
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
            if rumor: await send(msg.channel, f"*{rumor}*")
        except Exception as e:
            log_error(f"[rpg rumor] {e}")

async def _handle_shop(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.shop import get_shop_inventory
    sheet = await asyncio.to_thread(load, uid)
    if sheet and sheet.get("location") != "hemlocks_store":
        return await send(msg.channel, "You must be at Hemlock's Store to view inventory. (`!rpg go hemlocks_store`)")
        
    weapons, armor, consumables = get_shop_inventory()
    
    lines = ["🛒 **Hemlock's General Store**"]
    lines.append("──────────────────────────────")
    lines.append("**Weapons**")
    for k, v in weapons.items(): lines.append(f"  `{k:<15}` {v['name']:<20} {v['value']}g")
    lines.append("\n**Armor**")
    for k, v in armor.items(): lines.append(f"  `{k:<15}` {v['name']:<20} {v['value']}g")
    lines.append("\n**Consumables**")
    for k, v in consumables.items(): lines.append(f"  `{k:<15}` {v['name']:<20} {v['value']}g")
    
    if sheet:
        lines.append(f"\nYour Gil: **{sheet.get('gil', 0)}g**  |  `!rpg buy <item>` or `!rpg sell <item>`")
        
    await send(msg.channel, "```\n" + "\n".join(lines) + "\n```")

async def _handle_buy(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import process_purchase
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    if sheet.get("location") != "hemlocks_store":
        return await send(msg.channel, "You must be at Hemlock's Store to buy items.")
        
    if not rest.strip():
        return await send(msg.channel, "Buy what? Use `!rpg shop` for items.")
        
    item_key = rest.strip().lower()
    success, purchase_msg, updated_sheet = process_purchase(sheet, item_key)
    
    if success:
        from utils.ttrpg.shop import find_item
        item = find_item(item_key)
        
        # Determine specific response with optional soft warnings
        final_msg = purchase_msg
        if item and "classes" in item and updated_sheet["class"] not in item["classes"]:
            final_msg = (
                f"Purchased **{item['name']}** for {item['value']}g. (Remaining: {updated_sheet['gil']}g)\n"
                f"*Note: this is typically used by {'/'.join(item['classes'])} — you can equip it but it may feel awkward.*"
            )
            
        if item and item["category"] in ["weapon", "armor"]:
            slot = item["category"]
            if not updated_sheet["equipment"].get(slot):
                updated_sheet["inventory"].remove(item_key)
                updated_sheet["equipment"][slot] = item
                final_msg += f"\nAuto-equipped **{item['name']}**."
        
        await asyncio.to_thread(save, updated_sheet)
        await send(msg.channel, final_msg)
    else:
        await send(msg.channel, purchase_msg)

async def _handle_sell(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import process_sell
    
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    if sheet.get("location") != "hemlocks_store":
        return await send(msg.channel, "You must remain at Hemlock's Store to sell items.")
        
    if not rest.strip():
        return await send(msg.channel, "Sell what? Use `!rpg inventory` for items.")
        
    item_key = rest.strip().lower()
    success, resp_msg, updated_sheet = process_sell(sheet, item_key)
    
    if success:
        await asyncio.to_thread(save, updated_sheet)
    await send(msg.channel, resp_msg)

async def _handle_talk(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.npc_registry import get_npc, NPCS
    from utils.ttrpg.rpg_prompt_builder import build_npc_prompt
    from utils.social.kaia_social_responder import load_persona_async
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await asyncio.to_thread(load, uid)
    
    args = rest.strip().split(maxsplit=1)
    if not args:
        return await send(msg.channel, f"Talk to who? Known NPCs: {', '.join(NPCS.keys())}")
        
    npc_key = args[0].lower()
    npc = get_npc(npc_key)
    if not npc:
        return await send(msg.channel, f"Nobody by that name. Known NPCs: {', '.join(NPCS.keys())}")
        
    loc = sheet.get("location", "oakhaven") if sheet else "oakhaven"
    if npc["location"] != "any" and npc["location"] != loc:
        from utils.ttrpg.world import LOCATION_DATA
        target = LOCATION_DATA.get(npc['location'], {}).get('name', npc['location'])
        return await send(msg.channel, f"**{npc['name']}** isn't here. They're usually at **{target}**.")
        
    player_msg = args[1] if len(args) > 1 else "(Approach silently)"
    
    prompt = build_npc_prompt(sheet, npc, player_msg)
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
            if dialogue: await send(msg.channel, f"*{dialogue}*")
        except Exception as e:
            log_error(f"[rpg talk] {e}")


# ── Items and Equipment ──────────────────────────────────────────────────────

async def _handle_inventory(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    inv = "\n".join(f"  • {i}" for i in sheet.get("inventory", [])) or "  (empty)"
    await send(msg.channel, f"**{sheet['character_name']}'s inventory:**\n{inv}")

async def _handle_equip(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import find_item
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    if not rest.strip():
        return await send(msg.channel, "Equip what? `!rpg equip <item>`")
        
    item_key = rest.strip().lower()
    if item_key not in sheet.get("inventory", []):
        return await send(msg.channel, f"You don't have `{item_key}` in your inventory.")
        
    item = find_item(item_key)
    if not item or item["category"] not in ["weapon", "armor"]:
        return await send(msg.channel, f"`{item_key}` cannot be equipped.")
        
    # Unequip existing if slot filled
    slot = item["category"]
    if sheet["equipment"].get(slot):
        old = sheet["equipment"][slot]["key"]
        sheet["inventory"].append(old)
        
    # Equip new
    sheet["inventory"].remove(item_key)
    sheet["equipment"][slot] = item
    await asyncio.to_thread(save, sheet)
    
    await send(msg.channel, f"Equipped **{item['name']}** as {slot}.")

async def _handle_use(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.shop import find_item
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    
    item_key = rest.strip().lower()
    if item_key not in sheet.get("inventory", []):
        return await send(msg.channel, f"You don't have `{item_key}`.")
        
    item = find_item(item_key)
    if not item or item["category"] != "consumable":
        return await send(msg.channel, f"You can't use `{item_key}`.")
        
    if "hp_restore" in item:
        before = sheet["hp"]["current"]
        sheet["hp"]["current"] = min(sheet["hp"]["current"] + item["hp_restore"], sheet["hp"]["max"])
        healed = sheet["hp"]["current"] - before
        sheet["inventory"].remove(item_key)
        await asyncio.to_thread(save, sheet)
        await send(msg.channel, f"Used **{item['name']}**. Restored {healed} HP ({before} → {sheet['hp']['current']})")
    else:
        await send(msg.channel, f"**{item['name']}** can't be used. Try selling it: `!rpg sell {item_key}`")


# ── Combat ───────────────────────────────────────────────────────────────────

async def _handle_hunts(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.character_manager import load
    from utils.ttrpg.progression import hunts_remaining, MAX_HUNTS_PER_DAY
    sheet = await asyncio.to_thread(load, uid)
    if not sheet: return
    r = hunts_remaining(sheet)
    await send(msg.channel, f"**{sheet['character_name']}** has {r} hunts remaining today. Reset is at midnight server time.")

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
    if not ld.get("hunting"):
        return await send(msg.channel, f"You can't hunt in **{ld.get('name', loc)}**.\nTravel somewhere wild first.")
        
    sheet = check_and_reset_hunts(sheet)
    if hunts_remaining(sheet) <= 0:
        return await send(msg.channel, f"You have exhausted your stamina for the day. (0/{MAX_HUNTS_PER_DAY} hunts remaining)")
        
    if sheet["hp"]["current"] <= 0:
        return await send(msg.channel, f"You are far too weak to hunt right now. Go rest.")
        
    # Engage tracking
    chan_id = str(msg.channel.id)
    s = await asyncio.to_thread(load_session, chan_id)
    if not s:
        s = {"channel_id": chan_id, "monsters": [], "combat_active": False}
    
    # Are we already fighting something?
    my_fights = [m for m in s.get("monsters", []) if m.get("aggro_uid") == uid]
    if my_fights:
        m_name = my_fights[0].get("name", "Unknown Monster")
        m_key = my_fights[0].get("key", "monster")
        return await send(msg.channel, f"You are already fighting a **{m_name}**!\nUse `!rpg attack {m_key}` or `!rpg flee`.")
    
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

    # Spawn monster
    m_key = random_encounter(loc)
    m_data = get_monster(m_key)
    if not m_data:
        return await send(msg.channel, f"Wait... you hear a sound, but nothing emerges. (Error: Monster {m_key} not found)")
        
    m_temp = m_data.copy()
    m_temp["key"] = m_key
    m_temp["hp"] = {"current": m_temp["hp"], "max": m_temp["hp"]}
    m_temp["id"] = f"{m_key}_{_uuid.uuid4().hex[:4]}"
    m_temp["aggro_uid"] = uid  # personal instance
    
    s.setdefault("channel_id", chan_id)
    s["monsters"].append(m_temp)
    s["combat_active"] = True
    await asyncio.to_thread(save_session, s)
    
    import discord
    from utils.ttrpg.rpg_ui import TIER_ICONS
    
    rec = ld.get("recommended_level", 1)
    warn = f"⚠️ *{sheet['character_name']} is underleveled for this area.*\n" if sheet["level"] < rec - 1 else ""
    
    monster_desc = m_temp.get("desc", m_temp.get("description", "A dangerous creature."))
    tier_icon = TIER_ICONS.get(m_temp.get("tier", "medium"), "🟠")
    
    embed = discord.Embed(
        title=f"⚔️ Encounter: {m_temp['name']} {tier_icon}",
        description=f"{warn}*{monster_desc}*",
        color=0xFF4500
    )
    embed.add_field(name="❤️ HP", value=str(m_temp['hp']['max']), inline=True)
    embed.add_field(name="🗡️ ATK", value=str(m_temp['attack']), inline=True)
    embed.add_field(name="🛡️ DEF", value=str(m_temp['defense']), inline=True)
    
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
    if sheet["hp"]["current"] <= 0:
        return await send(msg.channel, "You are incapacitated.")
        
    s = await asyncio.to_thread(load_session, str(msg.channel.id))
    if not s or not s.get("combat_active") or not s.get("monsters"):
        return await send(msg.channel, "No active combat. `!rpg hunt` to find something.")
        
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
        return await send(msg.channel, "Cannot identify monster.")
        
    # Execute deterministic combat math loop
    res = _resolve_combat(sheet, monster)
    
    sheet = res["sheet"]
    monster = res["monster"]

    # After combat resolves, consume the blessing
    if "blessed" in sheet.get("conditions", []):
        sheet["conditions"].remove("blessed")
    
    # Handle state cleanup
    if res["monster_defeated"]:
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
            
        sheet["xp"] += xp_gain
        sheet["gil"] += gil_gain
        leveled, n_lvl = check_level_up(sheet)
        if leveled: level_up_msg = f"\n🎉 **LEVEL UP! {sheet['character_name']} grew to level {n_lvl}!**"
        
    await asyncio.to_thread(save, sheet)
    
    # Emit Math block
    m_block = "\n".join(res["exchanges"])
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
        sheet["location"] = "oakhaven"
        m_block += f"\n\n🚨 **You blacked out.** Townspeople dragged you back to the Shrine of the Silent Ones in Oakhaven. You dropped {xp_loss} XP and {gil_loss} Gil in the dirt."
        
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
    from utils.ttrpg.character_manager import load, save
    
    sheet = await asyncio.to_thread(load, uid)
    if sheet:
        sheet["hunt_streak"] = 0
        await asyncio.to_thread(save, sheet)
    from utils.ttrpg.session_manager import load_session, save_session
    import secrets
    s = await asyncio.to_thread(load_session, str(msg.channel.id))
    if not s or not s.get("combat_active"): return
    
    to_flee = -1
    for i, m in enumerate(s.get("monsters", [])):
        if m.get("aggro_uid") == uid:
            to_flee = i
            break
            
    if to_flee == -1: return await send(msg.channel, "You have nothing chasing you.")
    
    roll = secrets.randbelow(20) + 1
    if roll >= 10:
        s["monsters"].pop(to_flee)
        if not s["monsters"]: s["combat_active"] = False
        await asyncio.to_thread(save_session, s)
        await send(msg.channel, f"🏃 **{uname}** scrambled to safety! (d20 = {roll})")
    else:
        await send(msg.channel, f"❌ Flee failed! (d20 = {roll}) You trip. They close the distance.")


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

    # Post mechanical result
    xp_next = xp_to_next_level(sheet["level"])
    lines = [
        f"**{result['title']}**",
        f"*{result['outcome']}*",
    ]
    if result["xp"]:
        lines.append(f"+{result['xp']} XP ({sheet['xp']}/{xp_next})")
    if result["gil"]:
        lines.append(f"+{result['gil']} Gil (total: {sheet['gil']}g)")
    if result["hp_change"] > 0:
        lines.append(f"+{result['hp_change']} HP ({sheet['hp']['current']}/{sheet['hp']['max']})")
    if result["hp_change"] < 0:
        lines.append(f"{result['hp_change']} HP ({sheet['hp']['current']}/{sheet['hp']['max']})")
    if result["extra_hunt"]:
        lines.append(f"Hunts remaining: {hunts_remaining(sheet)}/{MAX_HUNTS_PER_DAY}")

    await send(msg.channel, "\n".join(lines))

    if leveled_up:
        await send(msg.channel, f"🎉 **{sheet['character_name']} reached Level {new_level}!**")

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
                    await send(msg.channel, f"*{narration}*")
            except Exception as e:
                log_error(f"[rpg event narration] {e}")


async def _handle_drink(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg drink — buy an ale at the Stone Hearth. Costs 2 gil, +3 temporary HP."""
    from utils.ttrpg.character_manager import load, save

    sheet = await asyncio.to_thread(load, uid)
    if not sheet:
        return await send(msg.channel, "no character found.")

    if sheet.get("location") != "stone_hearth":
        return await send(msg.channel,
            "you need to be at the Stone Hearth to drink.\n"
            "`!rpg go stone_hearth`")

    DRINK_COST = 2
    if sheet.get("gil", 0) < DRINK_COST:
        return await send(msg.channel,
            f"Mira glances at your coin purse and shakes her head.\n"
            f"An ale costs {DRINK_COST} gil. You have {sheet.get('gil', 0)}g.")

    # Grant temp HP by raising max temporarily (tracked via condition)
    TEMP_HP = 3
    already_drinking = any("ale" in c.lower() for c in sheet.get("conditions", []))
    if already_drinking:
        return await send(msg.channel,
            f"*Mira refills the tankard without comment.*\n"
            f"You're already feeling the first one. Another won't stack.")

    sheet["gil"] -= DRINK_COST
    sheet["hp"]["max"] += TEMP_HP
    sheet["hp"]["current"] = min(sheet["hp"]["current"] + TEMP_HP, sheet["hp"]["max"])
    sheet.setdefault("conditions", []).append("ale_warmth")  # removed on next rest
    await asyncio.to_thread(save, sheet)

    await send(msg.channel,
        f"🍺 Mira slides a tankard across the bar. (-{DRINK_COST} gil)\n"
        f"*Temporary HP: +{TEMP_HP}* (HP: {sheet['hp']['current']}/{sheet['hp']['max']})\n"
        f"*Clears when you next rest.*")


async def _handle_gamble(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg gamble — dice game at the Stone Hearth. 10 gil buy-in."""
    import secrets as _sec
    from utils.ttrpg.character_manager import load, save

    sheet = await asyncio.to_thread(load, uid)
    if not sheet:
        return await send(msg.channel, "no character found.")

    if sheet.get("location") != "stone_hearth":
        return await send(msg.channel,
            "the dice game only happens at the Stone Hearth.\n"
            "`!rpg go stone_hearth`")

    BUY_IN = 10
    if sheet.get("gil", 0) < BUY_IN:
        return await send(msg.channel,
            f"the buy-in is {BUY_IN} gil. you have {sheet.get('gil', 0)}g.\n"
            f"*A weathered man across the table doesn't look up from his cards.*")

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
    await send(msg.channel, f"{result_line}\n{gil_line}")


async def _handle_pray(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg pray — once per day blessing at the Shrine of the Silent Ones."""
    from utils.ttrpg.character_manager import load, save
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    if not sheet:
        return await send(msg.channel, "no character found.")

    if sheet.get("location") != "shrine":
        return await send(msg.channel,
            "you need to be at the Shrine of the Silent Ones to pray.\n"
            "`!rpg go shrine`")

    # Once per day check
    today = date.today().strftime("%Y-%m-%d")
    last_pray = sheet.get("last_pray_date", "")
    if last_pray == today:
        return await send(msg.channel,
            "🕯️ *The shrine is still. You've already made your offering today.*\n"
            "The Silent Ones do not answer twice.")

    # Check if already blessed
    if "blessed" in sheet.get("conditions", []):
        return await send(msg.channel,
            "🕯️ *You are already carrying the blessing of the Silent Ones.*\n"
            "Use it before asking for more.")

    sheet.setdefault("conditions", []).append("blessed")
    sheet["last_pray_date"] = today
    await asyncio.to_thread(save, sheet)

    await send(msg.channel,
        "🕯️ **Blessed** — *the shrine acknowledges you.*\n"
        "Your next hunt grants +2 to all attack and stat rolls.\n"
        "*The condition clears after your next combat.*")


async def _handle_offer(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg offer <amount> — donate gil to the shrine for XP."""
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    if not sheet:
        return await send(msg.channel, "no character found.")

    if sheet.get("location") != "shrine":
        return await send(msg.channel,
            "you need to be at the Shrine of the Silent Ones.\n"
            "`!rpg go shrine`")

    try:
        amount = int(rest.strip())
        assert 1 <= amount <= 9999
    except:
        return await send(msg.channel, "usage: `!rpg offer <amount>`\nexample: `!rpg offer 20`")

    if sheet.get("gil", 0) < amount:
        return await send(msg.channel,
            f"you only have {sheet.get('gil', 0)} gil.\n"
            f"*The shrine doesn't judge. It just waits.*")

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

    await send(msg.channel, "\n".join(msg_lines))


async def _handle_scout(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg scout — use the Watchtower to preview monster activity."""
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.monster_registry import MONSTERS, ENCOUNTER_TABLES
    from datetime import date

    sheet = await asyncio.to_thread(load, uid)
    if not sheet:
        return await send(msg.channel, "no character found.")

    if sheet.get("location") != "watchtower":
        return await send(msg.channel,
            "you need to be at the Watchtower to scout.\n"
            "`!rpg go watchtower`")

    # Once per day
    today = date.today().strftime("%Y-%m-%d")
    if sheet.get("last_scout_date") == today:
        return await send(msg.channel,
            "🗼 *The guards shrug. You've already had your look today.*\n"
            "Come back tomorrow.")

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

    await send(msg.channel, "\n".join(lines))


async def _handle_deliver(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg deliver — turn in a mognet letter in Oakhaven."""
    from utils.ttrpg.character_manager import load, save

    sheet = await asyncio.to_thread(load, uid)
    if not sheet:
        return await send(msg.channel, "no character found.")

    if sheet.get("location") not in ("oakhaven", "stone_hearth"):
        return await send(msg.channel,
            "you need to be in Oakhaven to deliver the letter.")

    if "mognet_letter" not in sheet.get("inventory", []):
        return await send(msg.channel,
            "you don't have a mognet letter to deliver.")

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
    await send(msg.channel,
        f"📬 **Mognet letter delivered.**\n"
        f"*A moogle materialises briefly, takes the letter, says 'kupo' with "
        f"visible relief, and presses a coin purse into your hand before vanishing.*\n"
        f"+{reward_xp} XP ({sheet['xp']}/{xp_next})  +{reward_gil} Gil")

    if leveled_up:
        await send(msg.channel,
            f"🎉 **{sheet['character_name']} reached Level {new_level}!**")


# ── Administration & Overrides ───────────────────────────────────────────────


async def _handle_roll(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.dice_engine import roll
    try:
        total, breakdown = roll(rest.strip() or "d20")
        await send(msg.channel, f"🎲 **{uname}** rolled `{rest.strip() or 'd20'}`: {breakdown}")
    except:
        await send(msg.channel, "invalid syntax")

async def _handle_bestiary(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.monster_registry import format_bestiary
    await send(msg.channel, format_bestiary(), use_code_block=False)

async def _handle_xp(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    # Basic static stub for admin xp
    await send(msg.channel, "Developer override required to assign arbitrary XP in Aethelgard. Go hunt.")

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
        await send(msg.channel, f"Admin granted `{args[0]}` to {sheet['character_name']}.")

async def _handle_heal(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    from utils.ttrpg.character_manager import load, save
    sheet = await asyncio.to_thread(load, str(msg.mentions[0].id) if msg.mentions else uid)
    if not sheet: return
    sheet["hp"]["current"] = sheet["hp"]["max"]
    await asyncio.to_thread(save, sheet)
    await send(msg.channel, f"Admin fully healed {sheet['character_name']}.")

async def _handle_event(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return
    if not rest.strip(): return
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
    await send(msg.channel, "```\n" + __doc__ + "\n```")
