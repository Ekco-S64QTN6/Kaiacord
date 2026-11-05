"""Navigation and location inspection commands for Aethelgard."""
import asyncio
import re
import uuid as _uuid

import discord

from utils.infrastructure.logging.kaia_logger import log_error
from utils.infrastructure.system.yaml_config import config
from utils.social.kaia_social_responder import load_persona_async
from utils.ttrpg.narration import finish_cleanly
from utils.ttrpg.rpg_views import LOCATION_COLORS, RPGFullLocationView, no_character


def _names(phrase: str, text: str) -> bool:
    """`phrase` appears in `text` as whole words."""
    return bool(re.search(rf"\b{re.escape(phrase)}\b", text))

async def _handle_go(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character):
    from utils.ttrpg.world import LOCATION_DATA, resolve_location

    sheet = await load_character(uid)
    if not sheet: return await msg.channel.send(embed=discord.Embed(description="No character found.", color=0xcc4444))

    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})

    if not rest.strip():
        color = LOCATION_COLORS.get(current_loc_key, 0x888888)
        embed = discord.Embed(
            title=f"📍 {current_loc.get('name', current_loc_key)}",
            description=f"*{current_loc.get('short', '')}*",
            color=color
        )
        view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, current_loc_key)
        return await msg.channel.send(embed=embed, view=view)

    target = resolve_location(rest.strip())
    if not target or target not in LOCATION_DATA:
        return await msg.channel.send(embed=discord.Embed(description=f"Unknown location: `{rest.strip()}`", color=0xcc4444))

    if target == current_loc_key:
        return await msg.channel.send(embed=discord.Embed(description="You're already there.", color=0x888888))

    # Gate check for locked locations
    target_data = LOCATION_DATA.get(target, {})
    locked_quest = target_data.get("locked_until_quest")
    if locked_quest:
        sheet = await load_character(uid)
        if sheet:
            completed = sheet.get("completed_quests", [])
            if locked_quest not in completed:
                from utils.ttrpg.quest_registry import get_quest
                q = get_quest(locked_quest)
                q_name = q["name"] if q else locked_quest.replace("_", " ").title()
                return await msg.channel.send(embed=discord.Embed(
                    title="⛔ Road Barricaded",
                    description=(
                        f"*The Trade Road north is blocked. Ironclad Guild barricades, "
                        f"reinforced with something that isn't just wood and iron.*\n\n"
                        f"A guard in grey wool waves you back without making eye contact.\n\n"
                        f"*There may be a way through. Elara might know. The Hooded Figure "
                        f"certainly does.*\n\n"
                        f"*(Complete quest: **{q_name}** to unlock this location.)*"
                    ),
                    color=0x8B0000
                ))

    # --- Auto-path: BFS to find shortest route ---
    def _find_path(start, end, completed_quests):
        from collections import deque
        visited = {start}
        queue = deque([(start, [start])])
        while queue:
            node, path = queue.popleft()
            for neighbor in LOCATION_DATA.get(node, {}).get("exits", []):
                # Check if neighbor is locked
                n_data = LOCATION_DATA.get(neighbor, {})
                n_lock = n_data.get("locked_until_quest")
                if n_lock and n_lock not in completed_quests:
                    continue  # Cannot traverse through locked locations
                    
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    direct = target in current_loc.get("exits", [])
    
    # Ensure we have the completed quests list for pathfinding
    completed_quests = []
    sheet = await load_character(uid)
    if sheet:
        completed_quests = sheet.get("completed_quests", [])
        
    path = [current_loc_key, target] if direct else _find_path(current_loc_key, target, completed_quests)

    if not path:
        return await msg.channel.send(embed=discord.Embed(description=f"There's no route from here to **{LOCATION_DATA.get(target, {}).get('name', target)}**.", color=0xcc4444))

    # Move player to final destination
    sheet["location"] = target
    
    from utils.ttrpg.micro_events import trigger_micro_event
    event_triggered, event_text = trigger_micro_event(sheet)
    await save_character(sheet)

    # Build arrival embed
    loc_data = LOCATION_DATA.get(target, {})
    name = loc_data.get("name", target)
    actions = ["`!rpg look` — observe the surroundings"]
    color = LOCATION_COLORS.get(target, 0x888888)

    # Show travel path if multi-hop
    if len(path) > 2:
        via_names = [LOCATION_DATA.get(p, {}).get("name", p) for p in path[1:-1]]
        desc = f"*Traveling via {', '.join(via_names)}...*\n\n*{loc_data.get('short', '')}*"
    else:
        desc = f"*{loc_data.get('short', '')}*"

    if event_triggered and event_text:
        desc = f"{event_text}\n\n{desc}"

    embed = discord.Embed(
        title=f"📍 {name}",
        description=desc,
        color=color
    )
    rec = loc_data.get("recommended_level")
    if rec and sheet["level"] < rec - 1:
        embed.set_footer(text=f"⚠️ Recommended level {rec}+ — proceed with caution")

    view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, target)
    await msg.channel.send(embed=embed, view=view)

    # Back from hunting grounds: the trip is over, and Kaia tells it once
    # (utils/ttrpg/outing.py). Walking between hunting grounds is one trip.
    from utils.ttrpg import outing
    if outing.is_hunting_ground(current_loc_key) and not outing.is_hunting_ground(target):
        await outing.close(ctx, msg.channel, uid, uname, sheet, reason=f"came back to {name}")

async def _handle_look(ctx, msg, send, rest, uid, uname, is_owner, *, load_character, save_character):
    from utils.ttrpg.world import LOCATION_DATA
    from utils.ttrpg.rpg_prompt_builder import build_look_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await load_character(uid)
    if not sheet: return await no_character(msg)
    
    loc = sheet.get("location", "oakhaven")
    data = LOCATION_DATA.get(loc, {})

    # ── Handle `!rpg look at <target>` ───────────────────────────────────────
    look_target = rest.strip().lower()
    if look_target.startswith("at "):
        look_target = look_target[3:].strip()

    if look_target:
        from utils.ttrpg.look_targets import LOCATION_LOOK_TARGETS
        loc_targets = LOCATION_LOOK_TARGETS.get(loc, {})
        result = loc_targets.get(look_target)
        matched = look_target if result else None
        if not result:
            # fuzzy match — "the flame" → "flame", "offering" → "offering bowl"
            for key in loc_targets:
                if _names(key, look_target) or _names(look_target, key):
                    result = loc_targets[key]
                    matched = key
                    break
        if result:
            if callable(result):
                result = result(sheet)
            embed = discord.Embed(description=result, color=LOCATION_COLORS.get(loc, 0x888888))

            # A quest task to look at something ("look_crystals").
            from utils.ttrpg.quest_registry import get_quest
            for active_id in sheet.get("active_quests", []):
                q = get_quest(active_id)
                task = f"look_{matched}"
                if q and task in q["tasks"]:
                    prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                    if task not in prog:
                        prog.append(task)
                        embed.add_field(name="📜 Quest Progress", value=q["name"], inline=False)
                        await save_character(sheet)
            
            # Secret puzzle trigger. Keyed on what matched, not what was typed:
            # "look at the flame" showed the flame and its "Acquired" line but
            # recorded nothing, so the secret could only be found by typing
            # the bare word.
            if loc == "shrine" and matched in ("flame", "altar"):
                secrets = sheet.setdefault("secrets", [])
                if f"look_{matched}" not in secrets:
                    secrets.append(f"look_{matched}")
                    embed.set_footer(text="A piece of the pattern clicks into place.")

                    if "look_flame" in secrets and "look_altar" in secrets and "symbol_of_the_silent_ones" not in sheet.get("inventory", []):
                        from utils.ttrpg.inventory_capacity import grant_item_or_mail
                        delivery = grant_item_or_mail(
                            sheet, "symbol_of_the_silent_ones", "Shrine Secret"
                        )
                        delivery_text = (
                            "Acquired: symbol_of_the_silent_ones"
                            if delivery == "inventory"
                            else "Sent to Moogle Mail because your inventory is full"
                        )
                        embed.add_field(
                            name="Secret Unlocked",
                            value=(
                                "You understand the pattern now. You can picture the seal perfectly in your mind.\n"
                                f"*({delivery_text})*"
                            ),
                            inline=False
                        )
                # Persist the looked-at secret and its reward together. Saving the
                # first half before the item/mailbox grant could strand the
                # second half of the puzzle and permanently lose the reward.
                await save_character(sheet)

            return await msg.channel.send(embed=embed)
        else:
            return await msg.channel.send(embed=discord.Embed(
                description=f"*{sheet['character_name']} studies the {look_target} carefully. Nothing unusual stands out.*",
                color=0x888888,
            ))

    # ── Generic location narration via Ollama ─────────────────────────────────
    
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
            narration = finish_cleanly(resp["message"]["content"].strip().replace("```", ""))
            if narration: 
                # Create narration embed
                embed = discord.Embed(
                    title=f"📍 {data.get('name', loc)}",
                    description=f"*{narration}*",
                    color=LOCATION_COLORS.get(loc, 0x888888)
                )
                
                view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, loc)
                await msg.channel.send(embed=embed, view=view)
        except Exception as e:
            log_error(f"[rpg look] {e}")

async def _handle_map(ctx, msg, send, rest, uid, uname, is_owner, *, load_character):
    from utils.ttrpg.world import LOCATION_DATA

    sheet = await load_character(uid)
    if not sheet: return await no_character(msg)

    current_loc_key = sheet.get("location", "oakhaven")
    current_loc = LOCATION_DATA.get(current_loc_key, {})

    exits = current_loc.get("exits", [])
    exit_lines = []
    for key in exits:
        if key not in LOCATION_DATA: continue
        ld = LOCATION_DATA[key]
        name = ld.get("name", key.replace("_", " ").title())
        if ld.get("hunting"):
            name += "  ⚔️"
        rec = ld.get("recommended_level")
        if rec:
            name += f"  *(Lv.{rec}+)*"
        exit_lines.append(f"• {name}")

    desc = "\n".join(exit_lines) if exit_lines else "*No exits from here.*"
    desc += "\n\n*Select a destination from the dropdown below.*"

    embed = discord.Embed(
        title=f"🗺️ From {current_loc.get('name', current_loc_key)}",
        description=desc,
        color=0x4488cc
    )

    view = RPGFullLocationView(ctx, msg, uid, uname, is_owner, current_loc_key)
    await msg.channel.send(embed=embed, view=view)
