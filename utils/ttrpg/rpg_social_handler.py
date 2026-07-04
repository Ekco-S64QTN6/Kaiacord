import asyncio
import time
import uuid as _uuid
import os
import json
import traceback
import discord
import secrets
from utils.infrastructure.logging.kaia_logger import log_info, log_error, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.ttrpg.world_state import get_current_state
from utils.ttrpg.character_manager import load, save, create, format_sheet, load_all
from utils.ttrpg.session_manager import load_session, save_session, create_session, end_session
from utils.ttrpg.progression import check_and_reset_hunts, hunts_remaining, check_level_up, MAX_HUNTS_PER_DAY, get_max_hunts, xp_to_next_level, XP_THRESHOLDS
from utils.ttrpg.class_advancement import (
    apply_advanced_class_to_combat, apply_advanced_class_to_sheet,
    get_advanced_options, get_title, ADVANCED_CLASSES
)
from utils.ttrpg.dungeon import _scale_boss_to_level, load_dungeon, save_dungeon
from utils.ttrpg.rpg_ui import TIER_ICONS, colored_bar, hp_bar, hp_label, CLASS_ICONS, LOCATION_ICONS, ANSI_GREEN, ANSI_RESET
from utils.social.kaia_social_responder import load_persona_async
from utils.ttrpg.world import LOCATION_DATA
from utils.ttrpg.encounter_tables import random_encounter
import utils.ttrpg.dice_engine as dice_engine
from utils.ttrpg.monster_registry import get as get_monster
from utils.ttrpg.shop import find_item
from utils.ttrpg.loot_tables import get_loot
from utils.ttrpg.broadcast import (
    log_world_event as _log_world_event,
    broadcast_world_event as _broadcast_world_event,
    level_up_flavor as _level_up_flavor,
    rare_loot_flavor as _rare_loot_flavor,
    _boss_approach_flavor
)

def _make_interaction_send(interaction: discord.Interaction):
    async def _send(channel, text, use_code_block=None):
        if use_code_block is None: use_code_block = False
        await interaction.followup.send(text)
    return _send

class _InteractionMsg:
    def __init__(self, interaction: discord.Interaction):
        self.channel = interaction.channel
        self.author = interaction.user


from utils.ttrpg.rpg_views import *

async def _handle_bard_song(ctx, msg, send, rest, uid, uname, is_owner):
    """Request a song from the Bard — generates a ballad about recent Oakhaven events."""
    import os, json
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority

    sheet = await load(uid)
    if sheet and sheet.get("location") != "stone_hearth":
        return await msg.channel.send(embed=discord.Embed(
            description="The Bard isn't here. Head to the Stone Hearth. (`!rpg go stone_hearth`)",
            color=0xcc4444
        ))

    events_path = os.path.join("memory", "ttrpg", "world_events.json")
    recent_events = []
    if os.path.exists(events_path):
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                recent_events = json.load(f)[-6:]
        except Exception:
            pass

    all_sheets = await load_all()
    top_adventurers = sorted(all_sheets, key=lambda s: s.get("xp", 0), reverse=True)[:4]
    names = [s["character_name"] for s in top_adventurers]

    events_str = "\n".join([f"- {e}" for e in recent_events]) if recent_events else "- A quiet season. The forest waits."
    names_str = ", ".join(names) if names else uname

    persona = await load_persona_async()
    prompt = (
        f"You are Caelindra the Bard performing at the Stone Hearth Inn in Oakhaven.\n"
        f"Recent events:\n{events_str}\n\n"
        f"Notable adventurers: {names_str}\n\n"
        f"Write a ballad (4-10 lines) about these deeds. "
        f"Voice: dry, specific, sardonic — like a journalist who found melody. "
        f"It MUST name at least one adventurer. Reference a specific event. "
        f"Output only the ballad, no preamble."
    )

    async with msg.channel.typing():
        song_text = "*The Bard strikes a chord... then shrugs. Nothing comes.*"
        try:
            gpu_manager = OllamaGPUManager(config.chat_model)
            opts = gpu_manager.get_gpu_options(for_chat=True)
            opts["num_predict"] = 180
            opts["temperature"] = 0.95

            resp = await gpu_memory_manager.run_with_gpu_guard(
                model_name=config.chat_model,
                priority=GPUTaskPriority.CHAT,
                coro=asyncio.wait_for(
                    ctx.ollama_client.chat(
                        model=config.chat_model,
                        messages=[
                            {"role": "system", "content": persona + "\n\n" + prompt},
                            {"role": "user", "content": "Perform the song."}
                        ],
                        options=opts,
                        keep_alive=-1
                    ),
                    timeout=45.0
                ),
                task_id=f"bard_song_{_uuid.uuid4().hex[:8]}"
            )
            raw = resp["message"]["content"].strip().replace("```", "")
            if raw:
                song_text = raw
        except Exception as e:
            log_error(f"[bard song] {e}")

    embed = discord.Embed(
        title="🎵 Caelindra Performs",
        description=f"*{song_text}*",
        color=0x9b59b6
    )
    embed.set_footer(text="The Stone Hearth goes quiet for a moment. Then Mira refills something.")
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_talk(ctx, msg, send, rest, uid, uname, is_owner):
    from utils.ttrpg.npc_registry import get_npc, NPCS
    from utils.ttrpg.rpg_prompt_builder import build_npc_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    
    sheet = await load(uid)
    
    # Format a curated, player-friendly list of known NPC names for display
    display_names = []
    seen_ids = set()
    preferred_keys = ["elara", "hemlock", "mira", "hooded", "guard", "maren", "caelindra", "merchant", "barnaby", "pip", "gregor"]
    for pk in preferred_keys:
        if pk in NPCS:
            npc_id = NPCS[pk].get("id")
            if npc_id not in seen_ids:
                display_names.append(pk)
                if npc_id:
                    seen_ids.add(npc_id)
    for k, v in NPCS.items():
        npc_id = v.get("id")
        if npc_id not in seen_ids:
            display_names.append(k)
            if npc_id:
                seen_ids.add(npc_id)
    known_npcs_str = ", ".join(display_names)
    
    rest_clean = rest.strip()
    # Strip common prepositions to allow "!rpg talk to Mira" or "!rpg talk with Hemlock"
    if rest_clean.lower().startswith("to "):
        rest_clean = rest_clean[3:].strip()
    elif rest_clean.lower().startswith("with "):
        rest_clean = rest_clean[5:].strip()
        
    args = rest_clean.split(maxsplit=1)
    if not args or not args[0]:
        return await msg.channel.send(embed=discord.Embed(description=f"Talk to who? Known NPCs: {known_npcs_str}", color=0x888888))
        
    npc_key = args[0].lower()
    npc = get_npc(npc_key)
    if not npc:
        return await msg.channel.send(embed=discord.Embed(description=f"Nobody by that name. Known NPCs: {known_npcs_str}", color=0xcc4444))
        
    # Resolve aliases to canonical key ID
    npc_key = npc.get("id", npc_key)
        
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
    if npc_key == "bard" or npc.get("role") == "bard":
        import os, json
        path = os.path.join("memory", "ttrpg", "world_events.json")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
            recent = events[-5:] if events else ["The world has been quiet lately."]
            topic = "Recent Events: " + " | ".join(recent)
        except Exception:
            topic = "An ancient tale of Aeridor's fall."
    elif "topics" in npc and npc["topics"]:
        import secrets
        topic = secrets.choice(npc["topics"])
        
    # Quest Integration
    from utils.ttrpg.quest_registry import get_npc_quests, get_quest
    available_quests = []
    active_quests_info = []
    quest_progress_msgs = []
    
    if sheet:
        # 1. Available Quests
        all_npc_quests = get_npc_quests(npc_key)
        completed = sheet.get("completed_quests", [])
        active_ids = sheet.get("active_quests", [])
        for q in all_npc_quests:
            if q["id"] not in completed and q["id"] not in active_ids:
                if sheet["level"] >= q["requirements"].get("level", 1):
                    available_quests.append(q)
                    
        # 2. Active Quest Progress & Completion
        for active_id in list(active_ids):
            q = get_quest(active_id)
            if q:
                if q["npc"] == npc_key:
                    active_quests_info.append(q)
                
                # Update progress if this is a talk task
                task_id = f"talk_{npc_key}"
                prog = sheet.setdefault("quest_progress", {}).setdefault(active_id, [])
                if task_id in q["tasks"]:
                    if task_id not in prog:
                        prog.append(task_id)

                # Check for completion (even if talk task was already done)
                if all(t in prog for t in q["tasks"]):
                    # Complete — apply rewards
                    xp_reward  = q["rewards"].get("xp", 0)
                    gil_reward = q["rewards"].get("gil", 0)
                    sheet["xp"]  = sheet.get("xp",  0) + xp_reward
                    sheet["gil"] = sheet.get("gil", 0) + gil_reward

                    if "item" in q["rewards"]:
                        sheet.setdefault("inventory", []).append(q["rewards"]["item"])
                    if "recipe" in q["rewards"]:
                        rk = q["rewards"]["recipe"]
                        if rk not in sheet.setdefault("recipes", []):
                            sheet.setdefault("recipes", []).append(rk)

                    if active_id in sheet.get("active_quests", []):
                        sheet["active_quests"].remove(active_id)
                    sheet.setdefault("completed_quests", []).append(active_id)
                    await save(sheet)

                    leveled, new_level = check_level_up(sheet)
                    if leveled:
                        await save(sheet)

                    from utils.ttrpg.progression import xp_to_next_level
                    xp_next = xp_to_next_level(sheet["level"])
                    completion_lines = [
                        f"**{q['name']}** — complete.",
                        f"+{xp_reward} XP ({sheet['xp']}/{xp_next})  ·  +{gil_reward} Gil",
                    ]
                    if "item" in q["rewards"]:
                        completion_lines.append(f"🎁 Received: **{q['rewards']['item'].replace('_',' ').title()}**")
                    if leveled:
                        completion_lines.append(f"🎉 **Level Up! Now Lv.{new_level}!**")

                    await msg.channel.send(embed=discord.Embed(
                        title="✅ Quest Complete",
                        description="\n".join(completion_lines),
                        color=0x2ecc71
                    ))
                    await _log_world_event(
                        f"✅ **{sheet['character_name']}** completed '**{q['name']}**'."
                    )
                    quest_embed = discord.Embed(
                        title=f"✅ Quest Complete — {q['name']}",
                        description=f"*{sheet['character_name']} closed the book on another chapter.*",
                        color=0x2ecc71
                    )
                    quest_embed.set_footer(text=f"+{xp_reward} XP · +{gil_reward} Gil")
                    await _broadcast_world_event(ctx, quest_embed)
                    if q["npc"] == npc_key:
                        quest_progress_msgs.append(f"'{q['name']}': COMPLETED")
                else:
                    # Not complete, show current progress
                    total = len(q["tasks"])
                    if q["npc"] == npc_key:
                        quest_progress_msgs.append(f"'{q['name']}': {len(prog)}/{total} tasks done: {', '.join(prog)}")
                    await save(sheet)

            
        # Generic turn-in check is covered by the talk task tracking above.
        # If an NPC has a specific inventory turn-in (like Maren), we can add it here.

    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2 if sheet else 0
    from utils.ttrpg.furniture import get_home_bonuses
    from utils.ttrpg.housing import load_housing_async
    housing = await load_housing_async(uid)
    bonuses = get_home_bonuses(housing) if housing else {}
    if sheet and sheet.get("location") == "housing_district":
        cha_mod += bonuses.get("home_cha", 0)
        
    talk_xp = bonuses.get("talk_xp", 0)
    if sheet and talk_xp:
        sheet["xp"] = sheet.get("xp", 0) + talk_xp
        check_level_up(sheet)  # enforce L15 XP cap
        await save(sheet)

    context = {
        "season": season,
        "special_day": special_day,
        "time_of_day": time_of_day,
        "blacked_out": blacked_out,
        "topic": topic,
        "available_quests": available_quests,
        "active_quests_info": active_quests_info,
        "quest_progress_msgs": quest_progress_msgs,
        "cha_mod": cha_mod,
    }
    
    prompt = build_npc_prompt(sheet, npc, player_msg, context)
    persona = await load_persona_async()
    messages = [
        {"role": "system", "content": f"{persona}\n\n{prompt}"},
        {"role": "user", "content": f"The player says: {player_msg}"}
    ]
    
    gpu_manager = OllamaGPUManager(config.chat_model)
    opts = gpu_manager.get_gpu_options(for_chat=True)
    opts["num_predict"] = 300
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
                view = discord.ui.View(timeout=180)

                # Quest accept buttons
                if available_quests:
                    for i, q in enumerate(available_quests[:2]):
                        btn = discord.ui.Button(
                            label=f"❓ Ask about: {q['name'][:24]}",
                            style=discord.ButtonStyle.primary,
                            row=0
                        )
                        async def _accept(interaction: discord.Interaction, quest=q):
                            if str(interaction.user.id) != uid:
                                await interaction.response.send_message("not yours.", ephemeral=True)
                                return
                            await interaction.response.defer()
                            s = await load(uid)
                            active_quests = s.get("active_quests", [])
                            if len(active_quests) >= 3:
                                await interaction.followup.send(embed=discord.Embed(
                                    description=f"You already have 3 active quests. Complete or abandon one first.",
                                    color=0xcc4444), ephemeral=True)
                                return
                            if quest["id"] in active_quests:
                                await interaction.followup.send(embed=discord.Embed(
                                    description=f"Already on quest: **{quest['name']}**.",
                                    color=0xcc4444), ephemeral=True)
                                return
                            s.setdefault("active_quests", []).append(quest["id"])
                            await save(s)
                            await interaction.followup.send(embed=discord.Embed(
                                title="📜 Quest Accepted",
                                description=f"**{quest['name']}**\n\n*{quest['description']}*\n\n"
                                            f"**Reward:** {quest['rewards'].get('xp',0)} XP · "
                                            f"{quest['rewards'].get('gil',0)} Gil",
                                color=0x2ecc71))
                        btn.callback = _accept
                        view.add_item(btn)

                # Active quest turn-in hint
                if any("COMPLETED" in msg for msg in quest_progress_msgs):
                    view.add_item(discord.ui.Button(
                        label="Quest Complete ✓", style=discord.ButtonStyle.success,
                        row=0, disabled=True))

                # Sister Maren's seed shop is now on the location HUD.

                view.add_item(_make_status_btn(ctx, uid, uname, is_owner))

                await msg.channel.send(embed=embed, view=view)
        except Exception as e:
            log_error(f"[rpg talk] {e}")


async def _handle_notices(ctx, msg, send, rest, uid, uname, is_owner):
    import os
    path = os.path.join("memory", "ttrpg", "world_events.json")
    events = []
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                events = json.load(f)
        except Exception:
            pass
            
    if not events:
        desc = "*The board is currently empty. Oakhaven is quiet.*"
    else:
        desc = "\n".join([f"• {e}" for e in reversed(events)])
        
    embed = discord.Embed(
        title="📝 Oakhaven Notice Board",
        description=desc,
        color=0x8b7355
    )
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_quests(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    if not sheet: return
    
    active = sheet.get("active_quests", [])
    completed = sheet.get("completed_quests", [])
    
    desc = ""
    if active:
        from utils.ttrpg.quest_registry import get_quest
        for a_id in active:
            q = get_quest(a_id)
            if q:
                prog = sheet.get("quest_progress", {}).get(a_id, [])
                done = len(prog)
                total = len(q["tasks"])
                bar = "█" * done + "░" * (total - done)
                desc += f"📜 **{q['name']}**\n> {q['description']}\n> Progress: `{bar}` {done}/{total} tasks\n\n"
            else:
                desc += f"📜 **{a_id}** (invalid ID)\n\n"
    else:
        desc += "📜 **Active Quests:** None\n\n"
            
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
    view = discord.ui.View(timeout=120)
    if active:
        # Give a drop-down menu if multiple, or a single button if 1
        if len(active) == 1:
            abandon_btn = discord.ui.Button(label="🗑️ Abandon Quest", style=discord.ButtonStyle.danger, row=0)
            async def _abandon_single(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("```\nnot your quest log.\n```", ephemeral=True)
                    return
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_abandon(ctx, fake_msg, send_fn, active[0], uid, uname, is_owner)
            abandon_btn.callback = _abandon_single
            view.add_item(abandon_btn)
        else:
            options = [discord.SelectOption(label=f"Abandon: {get_quest(a)['name'][:25] if get_quest(a) else a}", value=a) for a in active]
            select = discord.ui.Select(placeholder="Select a quest to abandon...", options=options, row=0)
            async def _abandon_select(interaction: discord.Interaction):
                if str(interaction.user.id) != uid:
                    await interaction.response.send_message("not yours.", ephemeral=True)
                    return
                await interaction.response.defer()
                fake_msg = _InteractionMsg(interaction)
                send_fn = _make_interaction_send(interaction)
                await _handle_abandon(ctx, fake_msg, send_fn, select.values[0], uid, uname, is_owner)
            select.callback = _abandon_select
            view.add_item(select)
        
    view.add_item(_make_status_btn(ctx, uid, uname, is_owner, row=1))
    await msg.channel.send(embed=embed, view=view)


async def _handle_abandon(ctx, msg, send, rest, uid, uname, is_owner):
    sheet = await load(uid)
    active = sheet.get("active_quests", []) if sheet else []
    if not sheet or not active:
        return await msg.channel.send(embed=discord.Embed(description="No active quest to abandon.", color=0x888888))
    
    quest_id = rest.strip().lower()
    if not quest_id and len(active) == 1:
        quest_id = active[0]
    elif not quest_id:
        return await msg.channel.send(embed=discord.Embed(description="Specify which quest to abandon.", color=0x888888))
        
    if quest_id not in active:
        return await msg.channel.send(embed=discord.Embed(description="You don't have that quest active.", color=0x888888))
        
    sheet["active_quests"].remove(quest_id)
    sheet["quest_progress"] = {k: v for k, v in sheet.get("quest_progress", {}).items() if k != quest_id}
    await save(sheet)
    await msg.channel.send(embed=discord.Embed(
        description=f"Quest **{quest_id.replace('_', ' ').title()}** abandoned. No rewards. The notice board doesn't care.",
        color=0x888888
    ))


async def _handle_quest_detail(ctx, msg, send, rest, uid, uname, is_owner):
    # !rpg quest <quest_id> or just !rpg quest for current
    sheet = await load(uid)
    if not sheet: return
    
    quest_id = rest.strip().lower()
    if not quest_id:
        return await send(msg.channel, "Specify a quest ID or use `!rpg quest` to see your log.")
        
    from utils.ttrpg.quest_registry import get_quest
    q = get_quest(quest_id)
    if not q:
        return await send(msg.channel, f"Quest `{quest_id}` not found.")
        
    embed = discord.Embed(
        title=f"📜 {q['name']}",
        description=q['description'],
        color=0x4a90e2
    )
    embed.add_field(name="Rewards", value=f"• {q['rewards'].get('xp', 0)} XP\n• {q['rewards'].get('gil', 0)} Gil")
    if "item" in q['rewards']: embed.add_field(name="Bonus", value=f"🎁 {q['rewards']['item'].replace('_', ' ').title()}")
    
    view = _make_status_view(ctx, msg, uid, uname, is_owner)
    await msg.channel.send(embed=embed, view=view)


async def _handle_mail(ctx, msg, send, rest, uid, uname, is_owner):
    """!rpg mail — Moogle Mail system in Oakhaven."""
    sheet = await load(uid)
    if not sheet: return

    if sheet.get("location") not in ("oakhaven", "stone_hearth"):
        return await msg.channel.send(embed=discord.Embed(
            description="You need to be in Oakhaven (or at the Inn) to access the Moogle Mail post.",
            color=0xcc4444
        ))

    # 1. Existing Quest Delivery logic (Silent but rewarding)
    if "mognet_letter" in sheet.get("inventory", []):
        reward_gil = 25
        reward_xp  = 20
        sheet["inventory"].remove("mognet_letter")
        if "mognet_pending" in sheet.get("conditions", []):
            sheet["conditions"].remove("mognet_pending")
        sheet["gil"] += reward_gil
        sheet["xp"]  += reward_xp
        leveled_up, new_level = check_level_up(sheet)
        await save(sheet)
        
        xp_next = xp_to_next_level(sheet["level"])
        quest_msg = f"📬 **Mognet letter delivered.**\n*A moogle materialises briefly, takes the letter, says 'kupo' with visible relief, and vanishes.*\n+{reward_xp} XP ({sheet['xp']}/{xp_next})  +{reward_gil} Gil"
        await msg.channel.send(embed=discord.Embed(description=quest_msg, color=0xf4a460))
        if leveled_up:
            await msg.channel.send(embed=discord.Embed(description=f"🎉 **{sheet['character_name']} reached Level {new_level}!**", color=0xffcc00))

    # 2. Main Mail Interface
    mailbox = sheet.get("mailbox", [])
    mail_count = len(mailbox)
    status_text = f"You have **{mail_count}** package(s) waiting." if mail_count > 0 else "Your mailbox is empty."
    
    embed = discord.Embed(
        title="📬 Moogle Mail Post",
        description=f"\"Kupo! Welcome to the mail post! Do you have something to send, or are you checking for a delivery?\"\n\n{status_text}",
        color=0xf4a460
    )
    
    view = MailMenuView(ctx, msg, uid, uname, is_owner, sheet)
    await msg.channel.send(embed=embed, view=view)


async def _handle_event(ctx, msg, send, rest, uid, uname, is_owner):
    if not is_owner: return

    from utils.core.background_tasks import (
        run_village_raid, run_oracle_speaks, run_moogle_festival,
        run_aeridorian_tremor, run_tonberry_procession, run_spine_storm,
        run_caravan_arrival, run_bard_performance,
        run_construct_breach, run_caravan_ambush, run_market_glut,
        run_whisperwood_bloom, run_shrine_vigil, run_missing_persons
    )

    EVENTS = {
        "raid":       run_village_raid,
        "invasion":   run_village_raid,
        "oracle":     run_oracle_speaks,
        "moogle":     run_moogle_festival,
        "mail":       run_moogle_festival,
        "tremor":     run_aeridorian_tremor,
        "aeridor":    run_aeridorian_tremor,
        "tonberry":   run_tonberry_procession,
        "procession": run_tonberry_procession,
        "storm":      run_spine_storm,
        "caravan":    run_caravan_arrival,
        "bard":       run_bard_performance,
        "construct":  run_construct_breach,
        "ambush":     run_caravan_ambush,
        "market":     run_market_glut,
        "bloom":      run_whisperwood_bloom,
        "vigil":      run_shrine_vigil,
        "missing":    run_missing_persons,
        "random":     None,
    }

    key = rest.strip().lower()

    if key in EVENTS:
        import secrets as _sec
        fn = EVENTS[key]
        if fn is None:  # random
            fn = _sec.choice([f for k, f in EVENTS.items() if f is not None])
        await send(msg.channel, f"triggering: **{key}**...")
        await fn(ctx, msg.channel)
        return

    if not key:
        # Show available events
        available = ", ".join(f"`{k}`" for k in EVENTS)
        await msg.channel.send(embed=discord.Embed(
            description=f"**Available events:**\n{available}\n\nUsage: `!rpg event raid`",
            color=0x888888
        ))
        return

    # Legacy: free-form narrative event
    description = rest.strip()
    from utils.ttrpg.rpg_prompt_builder import build_event_prompt
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority
    await _log_world_event(f"📣 **WORLD EVENT:** {description}")
    prompt = build_event_prompt(description)
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
