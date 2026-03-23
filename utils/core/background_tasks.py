import asyncio
import time
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_action, log_success, log_error, log_info, log_warning
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.shutdown_fixed import shutdown_manager

class CoreTaskManager:
    """Manager for core background loops with dependency injection and error handling."""
    def __init__(self, ctx):
        self.ctx = ctx
        self.news_refresh_task = self._make_news_refresh_task()
        self.dream_engine_task = self._make_dream_engine_task()
        self.evening_reflection_task = self._make_evening_reflection_task()
        self.aethelgard_dawn_task = self._make_aethelgard_dawn_task()
        self.noon_raid_task = self._make_noon_raid_task()
        
    def _make_news_refresh_task(self):
        @tasks.loop(hours=12)
        async def news_refresh_task():
            if shutdown_manager.shutting_down: return
            try:
                log_action("Running periodic news refresh...")
                import os
                from tools.maintenance.update_kaia_news import KaiaNewsUpdater
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    updater = KaiaNewsUpdater(api_key)
                    await asyncio.to_thread(updater.run, skip_backfill=True)
                    log_success("Periodic news refresh completed.")
                else:
                    log_warning("News refresh skipped: GEMINI_API_KEY not set.")
            except Exception as e:
                log_error(f"News refresh task failed: {e}")
                
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    log_error("CRITICAL: Gemini quota exhausted during news refresh. Kaia cannot ingest news today.")
                    # Removed Discord channel alert to prevent spam loops during quota lockouts

        @news_refresh_task.error
        async def news_refresh_error(error):
            log_error(f"CRITICAL: News refresh task died: {error}")
            
        return news_refresh_task

    def _make_dream_engine_task(self):
        @tasks.loop(hours=1)
        async def dream_engine_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot_state or not self.ctx.config: return
            
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            if not self.ctx.config.get('features.dream_mode_enabled', True): return
            if not self.ctx.dream_engine or not self.ctx.rag: return

            now = datetime.now()
            start_hour = self.ctx.config.get('dream_mode.schedule_start_hour', 3)
            end_hour = self.ctx.config.get('dream_mode.schedule_end_hour', 5)
            
            if start_hour <= now.hour < end_hour:
                # Guard: skip if a user chat is actively generating
                if getattr(self.ctx.bot_state, 'is_generating', False):
                    log_info("Dream cycle deferred: user chat generation in progress.")
                    return

                last_dream = getattr(self.ctx.bot_state, 'last_dream_date', "")
                today = now.strftime('%Y-%m-%d')
                
                if last_dream != today:
                    log_action("Nightly dream processing starting...")
                    try:
                        from utils.social.kaia_social_responder import load_persona_async
                        persona_content = await load_persona_async()
                        await self.ctx.dream_engine.nightly_dream_processing(persona_content)
                        
                        from utils.core.rag_executor import run_rag as run_rag_func
                        
                        # Wait for any in-progress refresh to clear, then ensure dream files are indexed
                        for _ in range(6):  # up to 3 minutes
                            if not getattr(self.ctx.rag, '_indexing_in_progress', False):
                                break
                            await asyncio.sleep(30)
                            
                        try:
                            await asyncio.wait_for(
                                run_rag_func(self.ctx.rag.refresh_knowledge_base),
                                timeout=300.0  # 5 min max for post-dream reindex
                            )
                        except asyncio.TimeoutError:
                            log_warning("[Dream] Post-dream RAG refresh timed out. Index will catch up on next !reindex.")
                        
                        self.ctx.bot_state.last_dream_date = today
                        self.ctx.bot_state.save()
                    except Exception as e:
                        log_error(f"Nightly dream task failed: {e}")

        @dream_engine_task.error
        async def dream_engine_error(error):
            log_error(f"CRITICAL: Dream engine task died: {error}")
            
        return dream_engine_task

    def _make_evening_reflection_task(self):
        @tasks.loop(minutes=30)
        async def evening_reflection_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot_state or not self.ctx.config: return
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            if not self.ctx.config.get('dream_mode.evening_reflection_enabled', True): return
            if not getattr(self.ctx, 'dream_engine', None): return

            now = datetime.now()
            start_hour = self.ctx.config.get('dream_mode.evening_reflection_start_hour', 22)
            end_hour = self.ctx.config.get('dream_mode.evening_reflection_end_hour', 23)
            
            if start_hour <= now.hour <= end_hour:
                if getattr(self.ctx.bot_state, 'is_generating', False): return

                # ADD THIS: minimum 5 minutes after boot before first reflection
                boot_time = getattr(self.ctx.bot_state, 'boot_complete_time', 0)
                time_since_boot = time.time() - boot_time
                if not self.ctx.bot_state.boot_complete or time_since_boot < 300:
                    return

                last_reflection = getattr(self.ctx.bot_state, 'last_evening_reflection', "")
                today = now.strftime('%Y-%m-%d')
                
                if last_reflection != today:
                    try:
                        from utils.social.kaia_social_responder import load_persona_async
                        persona_content = await load_persona_async()
                        await self.ctx.dream_engine.evening_reflection(persona_content)
                        self.ctx.bot_state.last_evening_reflection = today
                        self.ctx.bot_state.save()
                    except Exception as e:
                        log_error(f"Evening reflection task failed: {type(e).__name__}: {e}")

        @evening_reflection_task.error
        async def evening_reflection_error(error):
            log_error(f"Evening reflection task died: {type(error).__name__}: {error}")
            
        return evening_reflection_task

    def _make_aethelgard_dawn_task(self):
        import discord
        from datetime import datetime, timedelta

        @tasks.loop(hours=24)
        async def aethelgard_dawn_task():
            if shutdown_manager.shutting_down:
                return
            if not self.ctx or not self.ctx.bot_state:
                return

            today = datetime.now().strftime("%Y-%m-%d")

            # Dedup guard — in case the bot restarts right at midnight
            if getattr(self.ctx.bot_state, 'last_dawn_date', "") == today:
                return

            try:
                import os
                import json
                import random
                from utils.ttrpg.calendar import get_today_summary
                from utils.ttrpg.world_state import load_world_state, save_world_state

                characters_dir = os.path.join("memory", "ttrpg", "characters")
                if not os.path.exists(characters_dir):
                    return

                # Tick World State
                state = load_world_state()
                from utils.ttrpg.calendar import get_weather
                weather = get_weather()
                
                state["weather"] = weather["key"]
                state["weather_desc"] = weather["desc"]
                state["weather_name"] = weather["name"]
                state["weather_emoji"] = weather["emoji"]
                
                # Base modifiers from weather
                state["atk_mod"] = 0
                state["def_mod"] = 0
                state["xp_mult"] = 1.0
                state["gil_mult"] = 1.0
                
                effect = weather.get("effect")
                if effect:
                    if "atk" in effect: state["atk_mod"] += effect["atk"]
                    if "def" in effect: state["def_mod"] += effect["def"]
                    if "xp" in effect: state["xp_mult"] *= effect["xp"]
                    if "gil" in effect: state["gil_mult"] *= effect["gil"]

                # Roll for world event (15% chance)
                if random.random() < 0.15:
                    EVENTS = [
                        ("monster_surge", "Roars echo from the Whisperwood. Activity is high.", 1.2, 1.0),
                        ("economic_boom", "A wealthy merchant caravan has arrived.", 1.0, 1.5),
                        ("ritual_night", "The Silent Ones are restless. XP flows freely.", 1.5, 0.8),
                    ]
                    e_key, e_desc, e_xp_mult, e_gil_mult = random.choice(EVENTS)
                    state["event"] = e_key
                    state["event_desc"] = e_desc
                    state["xp_mult"] *= e_xp_mult
                    state["gil_mult"] *= e_gil_mult
                else:
                    state["event"] = "none"
                    state["event_desc"] = "Oakhaven is peaceful today."

                state["last_tick"] = time.time()
                save_world_state(state)

                files = [f for f in os.listdir(characters_dir) if f.endswith(".json")]
                reset_count = 0
                total_interest = 0

                for fname in files:
                    path = os.path.join(characters_dir, fname)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            sheet = json.load(f)
                        
                        modified = False
                        # Reset hunts
                        if sheet.get("hunts_today", 0) > 0:
                            sheet["hunts_today"] = 0
                            sheet["hunts_reset_date"] = today
                            modified = True
                            reset_count += 1
                        
                        # Bank Interest (2%, max 10g)
                        bank_bal = sheet.get("bank_balance", 0)
                        if bank_bal > 0:
                            interest = min(10, int(bank_bal * 0.02))
                            if interest > 0:
                                sheet["bank_balance"] += interest
                                total_interest += interest
                                modified = True
                        
                        if modified:
                            tmp = path + ".tmp"
                            with open(tmp, 'w', encoding='utf-8') as f:
                                json.dump(sheet, f, indent=2)
                            os.replace(tmp, path)

                    except Exception as e:
                        log_warning(f"[dawn] Failed to process {fname}: {e}")

                # Build announcement
                summary = get_today_summary()
                season_emoji = summary["season_emoji"]
                season_name  = summary["season_name"]
                date_str     = summary["date"]
                special      = summary["special_day"]

                if reset_count > 0:
                    lines = [
                        f"🌅 **A new day dawns in Aethelgard.**",
                        f"{season_emoji} **{season_name}** — {date_str}",
                        f"",
                        f"{state['weather_emoji']} **Weather:** {state['weather_name']} — *{state['weather_desc']}*",
                        f"",
                        f"All hunters restored to 5/5 hunts."
                        f" ({reset_count} refreshed)"
                    ]
                    if total_interest > 0:
                        lines.append(f"💰 **Interest Paid:** {total_interest}g distributed to savers.")
                else:
                    lines = [
                        f"🌅 **A new day dawns in Aethelgard.**",
                        f"{season_emoji} **{season_name}** — {date_str}",
                        f"",
                        f"{state['weather_emoji']} **Weather:** {state['weather_name']} — *{state['weather_desc']}*",
                    ]
                    if state["event"] != "none":
                        lines.append(f"📣 **Event:** {state['event_desc']}")
                    
                    lines.extend([
                        f"",
                        f"*{summary['season_flavor']}*",
                    ])

                # Special day announcement appended if applicable
                if special:
                    lines.append("")
                    lines.append(special["announcement"])
                    # If there's a buff, spell it out
                    if special.get("buff_desc"):
                        lines.append(f"✨ **Today:** {special['buff_desc']}")

                # Find the rpg broadcast channel by name
                rpg_channel_name = self.ctx.config.get(
                    'discord.rpg_channel', 'aethelgard'
                ).lower()
                channel = discord.utils.get(
                    self.ctx.bot.get_all_channels(),
                    name=rpg_channel_name
                )

                if channel:
                    await channel.send("\n".join(lines))
                    log_success(
                        f"[dawn] Announced. "
                        f"Season: {season_name}. "
                        f"Special: {special['name'] if special else 'none'}. "
                        f"Resets: {reset_count}."
                    )
                else:
                    log_warning(
                        f"[dawn] RPG channel '{rpg_channel_name}' not found."
                    )

                self.ctx.bot_state.last_dawn_date = today
                self.ctx.bot_state.save()

            except Exception as e:
                log_error(f"[dawn] Task failed: {e}")

        @aethelgard_dawn_task.before_loop
        async def before_dawn():
            """Sleep until exactly midnight before starting the 24h loop."""
            await self.ctx.bot.wait_until_ready()
            now = datetime.now()
            tomorrow_midnight = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            seconds_until_midnight = (tomorrow_midnight - now).total_seconds()
            log_info(
                f"[dawn] First fire in "
                f"{int(seconds_until_midnight // 3600)}h "
                f"{int((seconds_until_midnight % 3600) // 60)}m — "
                f"aligned to midnight."
            )
            await asyncio.sleep(seconds_until_midnight)

        @aethelgard_dawn_task.error
        async def dawn_error(error):
            log_error(f"[dawn] Task died: {type(error).__name__}: {error}")

        return aethelgard_dawn_task

    def _make_noon_raid_task(self):
        import discord
        from datetime import datetime, timedelta

        RAID_POOL = [
            ("wolf",     30),
            ("skeleton", 25),
            ("goblin",   20),
            ("bandit",   15),
            ("ghoul",    10),
        ]

        TOWN_LOCATIONS = {
            "oakhaven", "stone_hearth", "hemlocks_store",
            "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
        }

        @tasks.loop(hours=24)
        async def noon_raid_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot: return
            try:
                rpg_channel_name = self.ctx.config.get('discord.rpg_channel', 'aethelgard').lower()
                channel = discord.utils.get(self.ctx.bot.get_all_channels(), name=rpg_channel_name)
                if channel:
                    await run_village_raid(self.ctx, channel)
            except Exception as e:
                log_error(f"[noon-raid] Task failed: {e}")

        @noon_raid_task.before_loop
        async def before_noon_raid():
            await self.ctx.bot.wait_until_ready()
            now = datetime.now()
            today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
            next_noon = today_noon if now < today_noon else today_noon + timedelta(days=1)
            secs = (next_noon - now).total_seconds()
            log_info(
                f"[noon-raid] First fire in "
                f"{int(secs // 3600)}h {int((secs % 3600) // 60)}m — aligned to noon."
            )
            await asyncio.sleep(secs)

        @noon_raid_task.error
        async def noon_raid_error(error):
            log_error(f"[noon-raid] Task died: {type(error).__name__}: {error}")

        return noon_raid_task

    async def run_news_update(self):
        """Run integrated news refresh."""
        if not self.ctx: return
        try:
            log_action("Starting integrated news refresh...")
            import os
            import sys
            import asyncio
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                # Run as a separate process using the same python executable to assure environment consistency.
                script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools", "maintenance", "update_kaia_news.py")
                log_debug(f"Invoking {script_path} via {sys.executable}")
                process = await asyncio.create_subprocess_exec(
                    sys.executable, script_path, "--skip-backfill", "--no-prompt",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=os.environ.copy()
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                     log_success("External news update process completed successfully.")
                     if stdout:
                        for line in stdout.decode().splitlines():
                             if line.strip(): log_debug(f"[News] {line}")
                else:
                     log_error(f"External news update process failed with return code {process.returncode}")
                     if stderr:
                         for line in stderr.decode().splitlines():
                              if line.strip(): log_error(f"[News] {line}")
            else:
                log_warning("Integrated news update skipped: GEMINI_API_KEY not set.")
            
            from utils.core.rag_executor import run_rag as run_rag_func
            if self.ctx.rag:
                await run_rag_func(self.ctx.rag.refresh_knowledge_base)
                
            if self.ctx.news_manager:
                self.ctx.news_manager.refresh()
            log_success("Integrated news update completed.")
        except Exception as e:
            log_error(f"Failed to run news update: {e}")

    def start(self):
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        # self.news_refresh_task.start()
        # tasks.loop objects are not asyncio.Task, use get_task()
        # if self.news_refresh_task.get_task():
        #     task_registry.register("news_refresh_task", self.news_refresh_task.get_task())
        self.dream_engine_task.start()
        if self.dream_engine_task.get_task():
            task_registry.register("dream_engine_task", self.dream_engine_task.get_task())
            
        self.evening_reflection_task.start()
        if self.evening_reflection_task.get_task():
            task_registry.register("evening_reflection_task", self.evening_reflection_task.get_task())
            
        self.aethelgard_dawn_task.start()
        if self.aethelgard_dawn_task.get_task():
            task_registry.register("aethelgard_dawn_task", self.aethelgard_dawn_task.get_task())
            
        self.noon_raid_task.start()
        if self.noon_raid_task.get_task():
            task_registry.register("noon_raid_task", self.noon_raid_task.get_task())
            
        log_action("Core background tasks started via CoreTaskManager.")

    def stop(self):
        self.news_refresh_task.stop()
        self.dream_engine_task.stop()
        self.evening_reflection_task.stop()
        self.aethelgard_dawn_task.stop()
        self.noon_raid_task.stop()

# Helper for backward compatibility
_task_manager = None

def start_background_core_tasks(app_ctx):
    global _task_manager
    _task_manager = CoreTaskManager(app_ctx)
    _task_manager.start()

def stop_background_core_tasks():
    if _task_manager:
        _task_manager.stop()

async def run_news_update():
    if _task_manager:
        await _task_manager.run_news_update()

async def run_village_raid(bot_ctx, channel):
    """Shared raid logic — called by noon task and admin command."""
    import secrets
    import discord
    import asyncio
    from utils.ttrpg.character_manager import load_all, save
    from utils.ttrpg.monster_registry import get as get_monster
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from utils.commands.rpg_handler import _log_world_event

    RAID_POOL = [
        ("wolf",     30),
        ("skeleton", 25),
        ("goblin",   20),
        ("bandit",   15),
        ("ghoul",    10),
    ]
    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
    }

    await channel.send(embed=discord.Embed(
        title="🔔 VILLAGE ALARM",
        description=(
            "*Three rings from the Watchtower bell. The invasion signal.*\n\n"
            "A guard shouts from the parapet: **\"Something's coming out of the Whisperwood!\"**\n\n"
            "Elder Elara appears in the square, hands folded, expression unreadable.\n"
            "*\"Adventurers. To me. Now.\"*"
        ),
        color=0xFF4500
    ))
    await asyncio.sleep(3)

    all_sheets = await load_all()
    defenders = [
        s for s in all_sheets
        if s.get("location") in TOWN_LOCATIONS
        and s.get("hp", {}).get("current", 0) > 0
    ]

    if not defenders:
        await channel.send(embed=discord.Embed(
            description=(
                "*No adventurers were present. The village guard held the perimeter alone.*\n\n"
                "The threat is repelled. Oakhaven endures. Barely."
            ),
            color=0x888888
        ))
        return

    num_creatures = secrets.randbelow(2) + 2
    creatures = []
    total_xp = 0
    total_gil = 0

    for _ in range(num_creatures):
        total_weight = sum(w for _, w in RAID_POOL)
        r = secrets.randbelow(total_weight)
        cumulative = 0
        chosen_key = RAID_POOL[0][0]
        for key, weight in RAID_POOL:
            cumulative += weight
            if r < cumulative:
                chosen_key = key
                break
        m = get_monster(chosen_key)
        if m:
            creatures.append(m)
            total_xp += m.get("xp", 25)
            total_gil += m.get("gil", 10)

    total_xp = int(total_xp * 1.5)
    total_gil = int(total_gil * 1.2)
    creature_names = ", ".join(m["name"] for m in creatures)
    defenders_list = "\n".join(
        f"⚔️ **{s['character_name']}** (Lv.{s['level']} {s['class']})"
        for s in defenders
    )

    await channel.send(embed=discord.Embed(
        title="⚔️ Village Defense — Battle Joined",
        description=(
            f"**Attacking:** {creature_names}\n"
            f"**Defenders in Oakhaven:**\n{defenders_list}\n\n"
            "*The battle is joined at the village perimeter...*"
        ),
        color=0xCC4400
    ))
    await asyncio.sleep(4)

    contributions = []
    for s in defenders:
        roll = secrets.randbelow(20) + 1
        lvl_bonus = s.get("level", 1)
        contributions.append((s, roll, roll + lvl_bonus))
    contributions.sort(key=lambda x: x[2], reverse=True)

    avg = sum(c[2] for c in contributions) / len(contributions)
    OUTCOMES_DECISIVE = [
        "The attackers are routed decisively. The Whisperwood falls silent.",
        "Clean. The defenders held the perimeter without giving ground. Whatever came out of the wood went back into it.",
        "Decisive repulsion. The creatures didn't make it past the square's edge.",
        "Not even close. Oakhaven's defenders broke the assault before it fully formed.",
    ]
    OUTCOMES_HARD = [
        "Hard-fought. The creatures are driven off, but not without cost.",
        "The line held, barely. The attackers retreat into the treeline.",
        "A grinding defense. Oakhaven stands, though not without bruises.",
        "They pushed back. It took everything, but the square is clear.",
    ]
    OUTCOMES_RAGGED = [
        "Ragged but sufficient. Oakhaven holds — for now.",
        "The creatures pull back, and nobody's sure if it's victory or a pause.",
        "The defenders held the gate. The margin was uncomfortably thin.",
        "It's over. The square is quiet. Nobody's celebrating.",
    ]

    if avg >= 16:
        outcome = OUTCOMES_DECISIVE[secrets.randbelow(len(OUTCOMES_DECISIVE))]
        color = 0x2D5A27
    elif avg >= 11:
        outcome = OUTCOMES_HARD[secrets.randbelow(len(OUTCOMES_HARD))]
        color = 0x44aa44
    else:
        outcome = OUTCOMES_RAGGED[secrets.randbelow(len(OUTCOMES_RAGGED))]
        color = 0xf5c842

    xp_each = max(1, total_xp // len(defenders))
    gil_each = max(1, total_gil // len(defenders))

    result_lines = []
    level_ups = []
    for s, roll, contribution in contributions:
        s["xp"] = s.get("xp", 0) + xp_each
        s["gil"] = s.get("gil", 0) + gil_each
        leveled, new_lvl = check_level_up(s)
        await save(s)
        result_lines.append(
            f"⚔️ **{s['character_name']}** — d20({roll})+{s.get('level',1)} = **{contribution}**"
        )
        if leveled:
            level_ups.append(f"🎉 **{s['character_name']}** reached **Level {new_lvl}!**")

    result_embed = discord.Embed(
        title="🛡️ Oakhaven Holds",
        description=(
            f"*{outcome}*\n\n"
            + "\n".join(result_lines)
            + f"\n\n**Spoils divided equally:** +{xp_each} XP · +{gil_each} Gil each"
        ),
        color=color
    )
    if level_ups:
        result_embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)

    await channel.send(embed=result_embed)
    await _log_world_event(
        f"🛡️ **Village Defense:** Oakhaven repelled a raid ({creature_names}). "
        f"{len(defenders)} defender(s) rewarded."
    )

async def run_oracle_speaks(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all, save
    from utils.commands.rpg_handler import _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
    }
    BUFFS = [
        ("battle_focus",    "STR checks +1 until next combat"),
        ("forest_sight",    "DEX checks +1 until next combat"),
        ("resonance_link",  "INT checks +2 until next combat"),
        ("shadow_step",     "DEX checks +2 until next combat"),
        ("divine_clarity",  "WIS checks +2 until next combat"),
        ("sharp_mind",      "INT +2 on next check"),
        ("veiled_blessing", "+1 to next roll"),
    ]

    await channel.send(embed=discord.Embed(
        title="👁️ A Veiled Elder Appears",
        description=(
            "*She was not there a moment ago.*\n\n"
            "A pale figure stands at the center of the square, silver hair catching no light. "
            "She does not speak — not in any language that can be written.\n\n"
            "*Everyone present understands her anyway.*"
        ),
        color=0xc0c0d8
    ))
    await asyncio.sleep(4)

    all_sheets = await load_all()
    present = [s for s in all_sheets if s.get("location") in TOWN_LOCATIONS]

    if not present:
        await channel.send(embed=discord.Embed(
            description="*No one was there to receive it. The elder folded into shadow and was gone.*",
            color=0x888888
        ))
        return

    result_lines = []
    for s in present:
        buff_key, buff_desc = BUFFS[secrets.randbelow(len(BUFFS))]
        conds = s.setdefault("conditions", [])
        if buff_key not in conds:
            conds.append(buff_key)
        await save(s)
        result_lines.append(f"✨ **{s['character_name']}** — *{buff_desc}*")

    await channel.send(embed=discord.Embed(
        title="✨ The Elder's Gift",
        description=(
            "*She was gone before anyone could speak.*\n\n"
            + "\n".join(result_lines)
        ),
        color=0xc0c0d8
    ))
    await _log_world_event("👁️ **A Veiled Elder** visited Oakhaven. Those present were blessed.")

async def run_moogle_festival(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all, save
    from utils.commands.rpg_handler import _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
    }
    # Curated drop pool — useful but not overpowered
    DROP_POOL = [
        ("healing_herb", "Healing Herb", 40),
        ("bandage",       "Bandage",      30),
        ("tonic",         "Tonic",        20),
        ("aeridor_shard", "Aeridor Crystal Shard", 5),
        ("lucky_charm",   "Lucky Charm",  5),
    ]

    def roll_drop():
        total = sum(w for _, _, w in DROP_POOL)
        r = secrets.randbelow(total)
        cum = 0
        for key, name, w in DROP_POOL:
            cum += w
            if r < cum:
                return key, name
        return DROP_POOL[0][0], DROP_POOL[0][1]

    await channel.send(embed=discord.Embed(
        title="📬 Moogle Mail Drop",
        description=(
            "*The sound of bells. Then more bells.*\n\n"
            "Seventeen moogles appear over the rooftops of Oakhaven simultaneously, "
            "each carrying an overstuffed satchel. They descend with tremendous ceremony "
            "and no explanation.\n\n*\"Kupo!\"*"
        ),
        color=0xf4a460
    ))
    await asyncio.sleep(3)

    all_sheets = await load_all()
    present = [s for s in all_sheets if s.get("location") in TOWN_LOCATIONS]

    if not present:
        await channel.send(embed=discord.Embed(
            description="*No one to deliver to. The moogles left the packages on the ground and flew away, visibly offended.*",
            color=0x888888
        ))
        return

    result_lines = []
    for s in present:
        key, name = roll_drop()
        s.setdefault("inventory", []).append(key)
        await save(s)
        result_lines.append(f"📦 **{s['character_name']}** received **{name}**")

    await channel.send(embed=discord.Embed(
        title="📦 Packages Delivered",
        description="\n".join(result_lines) + "\n\n*The moogles left without waiting for thanks.*",
        color=0xf4a460
    ))
    await _log_world_event("📬 **Moogle Mail Drop** — packages delivered to all present in Oakhaven.")

async def run_aeridorian_tremor(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all, save
    from utils.ttrpg.progression import check_level_up, xp_to_next_level
    from utils.commands.rpg_handler import _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
    }

    await channel.send(embed=discord.Embed(
        title="💎 Aeridorian Tremor",
        description=(
            "*The ground hums. Not an earthquake — something deliberate.*\n\n"
            "The Aeridor ruins are doing something. Elara locks her door. "
            "The Shrine flame turns blue.\n\n"
            "*Whatever it's broadcasting, it's reaching everyone in range.*"
        ),
        color=0x9988dd
    ))
    await asyncio.sleep(4)

    all_sheets = await load_all()
    present = [s for s in all_sheets if s.get("location") in TOWN_LOCATIONS]

    if not present:
        await channel.send(embed=discord.Embed(
            description="*The pulse washed over an empty square. Oakhaven's cats all looked east at the same time.*",
            color=0x888888
        ))
        return

    result_lines = []
    level_ups = []
    for s in present:
        roll = secrets.randbelow(100)
        if roll < 40:
            # XP surge
            gain = secrets.randbelow(30) + 20
            s["xp"] = s.get("xp", 0) + gain
            leveled, new_lvl = check_level_up(s)
            await save(s)
            result_lines.append(f"✨ **{s['character_name']}** — resonance surge (+{gain} XP)")
            if leveled:
                level_ups.append(f"🎉 **{s['character_name']}** reached **Level {new_lvl}!**")
        elif roll < 65:
            # HP restore
            hp_gain = min(10, s["hp"]["max"] - s["hp"]["current"])
            s["hp"]["current"] = min(s["hp"]["current"] + hp_gain, s["hp"]["max"])
            await save(s)
            result_lines.append(f"💚 **{s['character_name']}** — the pulse closes old wounds (+{hp_gain} HP)")
        elif roll < 80:
            # Item drop
            s.setdefault("inventory", []).append("aeridor_shard")
            await save(s)
            result_lines.append(f"💎 **{s['character_name']}** — a crystal shard lands at their feet")
        else:
            # Minor HP drain
            drain = secrets.randbelow(4) + 2
            s["hp"]["current"] = max(1, s["hp"]["current"] - drain)
            await save(s)
            result_lines.append(f"⚡ **{s['character_name']}** — rejection. The pulse pushed back (-{drain} HP)")

    embed = discord.Embed(
        title="💎 The Pulse Fades",
        description="\n".join(result_lines),
        color=0x9988dd
    )
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    await channel.send(embed=embed)
    await _log_world_event("💎 **Aeridorian Tremor** — resonance pulse swept through Oakhaven.")

async def run_tonberry_procession(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all, save
    from utils.commands.rpg_handler import _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
    }

    await channel.send(embed=discord.Embed(
        title="🔪 The Tonberry Procession",
        description=(
            "*Single file. Lanterns lit. Moving with tremendous dignity through the square.*\n\n"
            "Nobody knows where they're going. Nobody asks. "
            "Mira has locked the Stone Hearth door from the inside.\n\n"
            "*Elara's note, slipped under every door in town: **Do not make eye contact.***"
        ),
        color=0x88bb88
    ))
    await asyncio.sleep(4)

    all_sheets = await load_all()
    present = [s for s in all_sheets if s.get("location") in TOWN_LOCATIONS]

    if not present:
        await channel.send(embed=discord.Embed(
            description="*They marched through an empty Oakhaven. Left a single coin on the well. Nobody knows why.*",
            color=0x888888
        ))
        return

    result_lines = []
    for s in present:
        # 80% watched quietly, 20% disturbed them
        roll = secrets.randbelow(10)
        if roll < 8:
            xp = secrets.randbelow(15) + 10
            gil = secrets.randbelow(20) + 10
            s["xp"] = s.get("xp", 0) + xp
            s["gil"] = s.get("gil", 0) + gil
            await save(s)
            result_lines.append(
                f"🕯️ **{s['character_name']}** watched in silence. A tonberry dropped a coin purse as it passed. (+{xp} XP, +{gil}g)"
            )
        else:
            dmg = secrets.randbelow(8) + 5
            s["hp"]["current"] = max(1, s["hp"]["current"] - dmg)
            await save(s)
            result_lines.append(
                f"🔪 **{s['character_name']}** made eye contact. The closest tonberry stopped walking. (-{dmg} HP)"
            )

    await channel.send(embed=discord.Embed(
        title="🔪 They Have Passed",
        description="\n".join(result_lines) + "\n\n*The last tonberry disappeared around the corner. The lanterns went out.*",
        color=0x88bb88
    ))
    await _log_world_event("🔪 **The Tonberry Procession** passed through Oakhaven.")

async def run_spine_storm(bot_ctx, channel):
    import discord, secrets
    from utils.ttrpg.character_manager import load_all, save
    from utils.ttrpg.progression import check_level_up
    from utils.commands.rpg_handler import _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut"
    }
    CLASS_EFFECTS = {
        "Warrior": ("battle_focus",   "The cold sharpens something. STR +1 until next combat."),
        "Ranger":  ("forest_sight",   "The storm light clarifies distance. DEX +1 until next combat."),
        "Mage":    ("resonance_link", "The charged air sings. INT +2 until next combat."),
        "Rogue":   ("shadow_step",    "The fog gives excellent cover. DEX +2 until next combat."),
        "Cleric":  ("divine_clarity", "The storm feels deliberate. WIS +2 until next combat."),
    }

    await channel.send(embed=discord.Embed(
        title="⛈️ Storm of the Spine",
        description=(
            "*It came from the Spine of the World and it has opinions.*\n\n"
            "Lightning that hits the same stone twice. Wind that changes direction mid-gust. "
            "The Watchtower crew came down twenty minutes ago and haven't said why.\n\n"
            "*Elara is standing in the square. In the rain. Looking pleased.*"
        ),
        color=0x4a4a7a
    ))
    await asyncio.sleep(4)

    all_sheets = await load_all()
    present = [s for s in all_sheets if s.get("location") in TOWN_LOCATIONS]

    if not present:
        await channel.send(embed=discord.Embed(
            description="*The storm broke over an empty square. The puddles glow faintly. Nobody saw it.*",
            color=0x888888
        ))
        return

    result_lines = []
    level_ups = []
    for s in present:
        cls = s.get("class", "Warrior")
        buff_key, buff_desc = CLASS_EFFECTS.get(cls, ("sharp_mind", "+1 to next roll."))
        conds = s.setdefault("conditions", [])
        if buff_key not in conds:
            conds.append(buff_key)
        xp_bonus = secrets.randbelow(10) + 5
        s["xp"] = s.get("xp", 0) + xp_bonus
        leveled, new_lvl = check_level_up(s)
        await save(s)
        result_lines.append(f"⚡ **{s['character_name']}** — *{buff_desc}* (+{xp_bonus} XP)")
        if leveled:
            level_ups.append(f"🎉 **{s['character_name']}** reached **Level {new_lvl}!**")

    embed = discord.Embed(
        title="⛈️ The Storm Passes",
        description="\n".join(result_lines),
        color=0x4a4a7a
    )
    if level_ups:
        embed.add_field(name="\u200b", value="\n".join(level_ups), inline=False)
    
    await channel.send(embed=embed)
    await _log_world_event("⛈️ **Storm of the Spine** swept through Oakhaven.")

