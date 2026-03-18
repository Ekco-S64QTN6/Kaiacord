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
            
        log_action("Core background tasks started via CoreTaskManager.")

    def stop(self):
        self.news_refresh_task.stop()
        self.dream_engine_task.stop()
        self.evening_reflection_task.stop()
        self.aethelgard_dawn_task.stop()

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
