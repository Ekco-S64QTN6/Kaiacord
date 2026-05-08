import asyncio
import time
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_action, log_success, log_error, log_info, log_warning, log_debug
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
        self.afterthought_task = self._make_afterthought_task()
        
        # Inner Monologue — ephemeral thought buffer, injected into system prompt
        try:
            from utils.core.kaia_monologue import InnerMonologue
            self.monologue = InnerMonologue()
            ctx.monologue = self.monologue  # Expose to message_processor
            self.monologue_task = self._make_monologue_task()
        except Exception as e:
            log_warning(f"Monologue system init failed (non-fatal): {e}")
            self.monologue = None
            self.monologue_task = None

        # Proactive Initiation — Kaia speaks first, rate-limited
        try:
            from utils.core.kaia_proactive import ProactiveEngine
            self.proactive_engine = ProactiveEngine()
            self.proactive_task = self._make_proactive_task()
        except Exception as e:
            log_warning(f"Proactive engine init failed (non-fatal): {e}")
            self.proactive_engine = None
            self.proactive_task = None

        # Presence system — maps mood floats to visible Discord status
        self.presence_manager = None
        self.presence_task = None
        if ctx.bot and config.get('features.presence_enabled', True):
            from utils.core.kaia_presence import KaiaPresenceManager, make_presence_task
            self.presence_manager = KaiaPresenceManager(ctx.bot, ctx.bot_state)
            self.presence_task = make_presence_task(self.presence_manager)
            # Store on ctx so other modules (dream engine) can trigger overrides
            ctx.presence_manager = self.presence_manager
        
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

    def _make_afterthought_task(self):
        @tasks.loop(minutes=3)
        async def afterthought_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot_state: return
            
            # Guard: skip if a user chat is actively generating or if dreaming
            if getattr(self.ctx.bot_state, 'is_generating', False): return
            if getattr(self.ctx.bot_state, 'is_generating_image', False): return
            
            pending = getattr(self.ctx.bot_state, 'pending_afterthoughts', [])
            if not pending: return

            now = time.time()
            to_remove = []
            to_execute = None
            
            for i, p in enumerate(pending):
                age = now - p['timestamp']
                # Discard afterthoughts older than 1 hour (stale)
                if age >= 3600:
                    to_remove.append(i)
                    continue
                # Only trigger if 10 minutes have passed since queuing
                if age >= 600:
                    # Check per-channel activity to see if anyone spoke recently
                    chan_id = p['channel_id']
                    last_activity = self.ctx.bot_state.channel_last_activity.get(chan_id, 0)
                    if now - last_activity >= 600:
                        # Channel has been silent for 10+ minutes — deliver
                        to_execute = p
                        to_remove.append(i)
                        break  # Only do one at a time
                    # else: channel still active — leave it in the queue for next cycle
            
            # Clean up processed/stale
            for i in reversed(to_remove):
                pending.pop(i)
            self.ctx.bot_state.save()
            
            if to_execute:
                try:
                    channel = self.ctx.bot.get_channel(to_execute['channel_id'])
                    if not channel: return
                    
                    # Ensure it's not a DM
                    if hasattr(channel, 'guild') and channel.guild is None:
                        return
                    
                    from utils.social.kaia_social_responder import load_persona_async
                    from utils.infrastructure.gpu.gpu_memory_manager import gpu_memory_manager, GPUTaskPriority
                    import uuid
                    
                    persona = await load_persona_async()
                    prompt = (
                        f"You were speaking with {to_execute['user_name']} about: {to_execute['topic']}. "
                        f"It's been 10 minutes since the conversation ended. Generate a brief, unprompted follow-up "
                        f"thought or realization about it. Keep it under 2 sentences. "
                        f"Start naturally, like 'actually, thinking more about what you said...' or 'i just realized...'."
                    )
                    
                    async with channel.typing():
                        # Variable reading pause just like normal messages
                        import secrets
                        await asyncio.sleep(2.0 + secrets.randbelow(3))
                        
                        resp = await gpu_memory_manager.run_with_gpu_guard(
                            model_name=config.chat_model,
                            priority=GPUTaskPriority.CHAT,
                            coro=asyncio.wait_for(
                                self.ctx.ollama_client.chat(
                                    model=config.chat_model,
                                    messages=[
                                        {"role": "system", "content": persona},
                                        {"role": "user", "content": prompt}
                                    ],
                                    options={"temperature": 0.8},
                                    keep_alive=-1
                                ),
                                timeout=45.0
                            ),
                            task_id=f"afterthought_{uuid.uuid4().hex[:8]}"
                        )
                        
                        raw = resp["message"]["content"].strip()
                        if raw:
                            from utils.infrastructure.system.messaging import send_kaia_response
                            await send_kaia_response(channel, raw)
                            log_info(f"Delivered delayed afterthought to {to_execute['user_name']}")
                except Exception as e:
                    log_warning(f"Failed to generate afterthought: {e}")

        @afterthought_task.before_loop
        async def before_afterthought():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(15)

        return afterthought_task

    def _make_monologue_task(self):
        @tasks.loop(minutes=15)
        async def monologue_task():
            if shutdown_manager.shutting_down: return
            if not self.monologue: return
            if not self.ctx or not self.ctx.bot_state: return
            if getattr(self.ctx.bot_state, 'is_generating', False): return

            # Only generate when bot is fully booted
            if not getattr(self.ctx.bot_state, 'boot_complete', False): return

            try:
                await self.monologue.generate_thought(
                    channel_memory=self.ctx.bot_state.channel_memory,
                    bot_state=self.ctx.bot_state,
                    ollama_client=self.ctx.ollama_client,
                    chat_model=config.chat_model,
                )
            except Exception as e:
                log_debug(f"Monologue task error (non-fatal): {e}")

        @monologue_task.before_loop
        async def before_monologue():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(60)  # Wait 1 min after boot

        @monologue_task.error
        async def monologue_error(error):
            log_debug(f"Monologue task died (non-fatal): {error}")

        return monologue_task

    def _make_proactive_task(self):
        @tasks.loop(minutes=30)
        async def proactive_task():
            if shutdown_manager.shutting_down: return
            if not self.proactive_engine: return
            if not self.ctx or not self.ctx.bot_state: return
            if getattr(self.ctx.bot_state, 'is_generating', False): return
            if not getattr(self.ctx.bot_state, 'boot_complete', False): return

            try:
                trigger = await self.proactive_engine.evaluate_triggers(
                    bot_state=self.ctx.bot_state,
                    dream_engine=getattr(self.ctx, 'dream_engine', None),
                )

                if not trigger:
                    return

                channel = self.ctx.bot.get_channel(trigger.channel_id)
                if not channel:
                    return

                # Ensure it's a guild channel, not a DM
                if hasattr(channel, 'guild') and channel.guild is None:
                    return

                from utils.social.kaia_social_responder import load_persona_async
                persona = await load_persona_async()

                message = await self.proactive_engine.generate_opener(
                    trigger=trigger,
                    ollama_client=self.ctx.ollama_client,
                    chat_model=config.chat_model,
                    persona=persona,
                )

                if message:
                    import secrets as _secrets
                    async with channel.typing():
                        # Natural reading pause before sending
                        await asyncio.sleep(2.0 + _secrets.randbelow(4))

                    from utils.infrastructure.system.messaging import send_kaia_response
                    await send_kaia_response(channel, message)
                    self.proactive_engine.record_sent(self.ctx.bot_state, trigger)
                    log_success(f"Proactive message sent ({trigger.trigger_type})")

            except Exception as e:
                log_warning(f"Proactive task error (non-fatal): {e}")

        @proactive_task.before_loop
        async def before_proactive():
            if getattr(self.ctx, 'bot', None):
                await self.ctx.bot.wait_until_ready()
                await asyncio.sleep(120)  # Wait 2 min after boot

        @proactive_task.error
        async def proactive_error(error):
            log_warning(f"Proactive task died: {error}")

        return proactive_task

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
                    
                    # Signal presence: dreaming
                    pm = getattr(self.ctx, 'presence_manager', None)
                    if pm:
                        pm.set_override("dreaming...", duration_seconds=7200)
                        await pm.update_presence()
                    
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
                        
                        # Signal presence: post-dream
                        if pm:
                            pm.set_override("just woke up. processing.", duration_seconds=1800)
                            await pm.update_presence()
                    except Exception as e:
                        log_error(f"Nightly dream task failed: {e}")
                    finally:
                        # Clear dream override after processing (or on failure)
                        if pm and pm._override_text in ("dreaming...",):
                            pm.clear_override()

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
                from utils.ttrpg.world_state import load_world_state, async_save_world_state

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
                
                # Disable Caravan at Dawn
                state["caravan_active"] = False

                # Base modifiers from weather
                state["atk_mod"] = 0
                state["def_mod"] = 0
                state["xp_mult"] = 1.0
                state["gil_mult"] = 1.0
                
                effect = weather.get("effect")
                if effect:
                    effect_type  = effect.get("type", "")
                    effect_value = effect.get("value", 0)
                    if effect_type == "xp_bonus":
                        state["xp_mult"] = state.get("xp_mult", 1.0) + (effect_value / 100.0)
                    elif effect_type == "gil_bonus":
                        state["gil_mult"] = state.get("gil_mult", 1.0) + (effect_value / 100.0)
                    elif effect_type == "armor_penalty":
                        state["def_mod"] = state.get("def_mod", 0) + effect_value

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
                await async_save_world_state(state)

                def _process_characters():
                    files = [f for f in os.listdir(characters_dir) if f.endswith(".json")]
                    r_count = 0
                    t_interest = 0

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
                                r_count += 1

                            # Clear Caravan Flags
                            if sheet.get("flags", {}).get("caravan_gear_bought"):
                                sheet["flags"]["caravan_gear_bought"] = False
                                modified = True

                            # Clear stale calendar buff flags
                            for stale_key in ("_winter_resolve_applied", "_new_year_applied"):
                                if stale_key in sheet:
                                    sheet.pop(stale_key)
                                    modified = True

                            # Clear temporary conditions at dawn
                            from utils.ttrpg.progression import PERMANENT_CONDITIONS
                            old_conds = sheet.get("conditions", [])
                            # Ale warmth carries a +3 max HP — strip it before clearing
                            if "ale_warmth" in old_conds:
                                sheet["hp"]["max"] = max(1, sheet["hp"]["max"] - 3)
                                sheet["hp"]["current"] = min(sheet["hp"]["current"], sheet["hp"]["max"])
                            new_conds = [c for c in old_conds if c in PERMANENT_CONDITIONS]
                            if old_conds != new_conds:
                                sheet["conditions"] = new_conds
                                modified = True
                            
                            # Bank Interest (2%, max 10g + bonus) has been removed
                            
                            if modified:
                                tmp = path + ".tmp"
                                with open(tmp, 'w', encoding='utf-8') as f:
                                    json.dump(sheet, f, indent=2)
                                os.replace(tmp, path)

                        except Exception as e:
                            log_warning(f"[dawn] Failed to process {fname}: {e}")
                    
                    return r_count, t_interest

                reset_count, total_interest = await asyncio.to_thread(_process_characters)



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
                
                from utils.ttrpg.pantheon import DEITIES
                import secrets
                deity_key = secrets.choice(list(DEITIES.keys()))
                lines.append(f"\n🕯️ *{DEITIES[deity_key]['shrine_flavor']}*")

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
            
            today_str = now.strftime("%Y-%m-%d")
            if now.hour == 0 and now.minute < 30:
                if getattr(self.ctx.bot_state, 'last_dawn_date', "") != today_str:
                    log_info("[dawn] Booted shortly after midnight. Firing immediately.")
                    return
            
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

        @tasks.loop(hours=24)
        async def noon_raid_task():
            if shutdown_manager.shutting_down: return
            if not self.ctx or not self.ctx.bot: return
            try:
                rpg_channel_name = self.ctx.config.get('discord.rpg_channel', 'aethelgard').lower()
                channel = discord.utils.get(self.ctx.bot.get_all_channels(), name=rpg_channel_name)
                if channel:
                    import secrets
                    EVENT_POOL = [
                        (run_village_raid,       35),
                        (run_oracle_speaks,      12),
                        (run_moogle_festival,    15),
                        (run_aeridorian_tremor,  12),
                        (run_tonberry_procession, 8),
                        (run_spine_storm,        10),
                        (run_caravan_arrival,     5),
                        (run_bard_performance,    3),
                    ]
                    total_w = sum(w for _, w in EVENT_POOL)
                    r_val = secrets.randbelow(total_w)
                    cum = 0
                    chosen_event = EVENT_POOL[0][0]
                    for fn, w in EVENT_POOL:
                        cum += w
                        if r_val < cum:
                            chosen_event = fn
                            break
                    await chosen_event(self.ctx, channel)
            except Exception as e:
                log_error(f"[noon-event] Task failed: {e}")

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
        
        # Presence system
        if self.presence_task:
            self.presence_task.start()
            if self.presence_task.get_task():
                task_registry.register("presence_update_task", self.presence_task.get_task())
                
        # Afterthought task
        self.afterthought_task.start()
        if self.afterthought_task.get_task():
            task_registry.register("afterthought_task", self.afterthought_task.get_task())

        # Inner Monologue task
        if self.monologue_task:
            self.monologue_task.start()
            if self.monologue_task.get_task():
                task_registry.register("monologue_task", self.monologue_task.get_task())

        # Proactive Initiation task
        if self.proactive_task:
            self.proactive_task.start()
            if self.proactive_task.get_task():
                task_registry.register("proactive_task", self.proactive_task.get_task())

        log_action("Core background tasks started via CoreTaskManager.")

    def stop(self):
        self.news_refresh_task.stop()
        self.dream_engine_task.stop()
        self.evening_reflection_task.stop()
        self.aethelgard_dawn_task.stop()
        self.noon_raid_task.stop()
        self.afterthought_task.stop()
        if self.presence_task:
            self.presence_task.stop()
        if self.monologue_task:
            self.monologue_task.stop()
        if self.proactive_task:
            self.proactive_task.stop()

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
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    RAID_POOL = [
        ("wolf",     30),
        ("skeleton", 25),
        ("goblin",   20),
        ("bandit",   15),
        ("ghoul",    10),
    ]
    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
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
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
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
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
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
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
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
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
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
            from utils.ttrpg.progression import check_level_up
            leveled, new_lvl = check_level_up(s)
            await save(s)
            result_lines.append(
                f"🕯️ **{s['character_name']}** watched in silence. A tonberry dropped a coin purse as it passed. (+{xp} XP, +{gil}g)"
            )
            if leveled:
                result_lines.append(f"🎉 **{s['character_name']}** reached **Level {new_lvl}!**")
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
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
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

async def run_caravan_arrival(bot_ctx, channel):
    """Full caravan merchant event — tier 3 gear, 1 gear per customer, buy + talk.

    Only an announcement embed is posted to the channel.  Players click
    '🐪 Visit Caravan' to open the shop privately (ephemeral).
    """
    import discord
    import secrets
    import asyncio
    from utils.infrastructure.logging.kaia_logger import log_action
    from utils.ttrpg.equipment_registry import (
        get_caravan_stock, WEAPONS, ARMOR, HEADGEAR, BOOTS, ACCESSORIES, CONSUMABLES,
    )
    from utils.ttrpg.shop import find_item, process_purchase
    from utils.ttrpg.character_manager import load, save
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    TOWN_LOCATIONS = {
        "oakhaven", "stone_hearth", "hemlocks_store",
        "shrine", "watchtower", "oakhaven_bank", "herbalists_hut",
        "housing_district", "tricklebrook_pond"
    }

    CARAVAN_TALK = [
        (
            "The Road from Grimstone",
            "*The merchant leans against a crate and rolls a coin across his knuckles.*\n\n"
            "\"Three days from Grimstone. Road's worse than last season — bandits twice, "
            "a fog that didn't move right once. The Ironclad Guild men say the Trade Road "
            "is their jurisdiction but I didn't see a single patrol past the second mile marker.\"\n\n"
            "*He spits.* \"Jurisdiction. Right.\""
        ),
        (
            "Corvus Watch Over You",
            "*He touches a small charm at his throat — three interlocking circles.*\n\n"
            "\"Corvus, god of travelers and merchants. Every caravan runner carries his mark. "
            "Not because we're devout — because the alternative is admitting we're out here alone.\"\n\n"
            "*He glances at the Whisperwood treeline.* \"Some roads, you want someone watching.\""
        ),
        (
            "News from the Coast",
            "*The merchant sorts through a ledger while he talks.*\n\n"
            "\"Riverbend's gone quiet. Used to be good business — boat builders, fishermen, "
            "people who need rope and nails. Last two runs, half the stalls were closed. "
            "A fisherman told me the Silverstream is running dark. Not muddy. Dark.\"\n\n"
            "*He doesn't look up from the ledger.* \"I don't fish. Not my problem.\""
        ),
        (
            "The Aeridor Shards",
            "*His eyes sharpen when you mention the ruins.*\n\n"
            "\"Shards? Oh, I'll move those. Cities pay well — universities, collectors, "
            "the odd Ironclad Guild 'researcher.' Your man Hemlock buys them too, but he "
            "won't say what for. Between you and me, neither will the cities.\"\n\n"
            "*He taps his nose.* \"Good margins on mystery.\""
        ),
        (
            "Whisperwood Sightings",
            "*The merchant glances over his shoulder.*\n\n"
            "\"Silvani on the road two nights ago. Didn't speak to us — never do. But one of them "
            "stopped and watched the caravan pass for a full minute. My guard said they were counting "
            "our supplies.\"\n\n"
            "*He shrugs.* \"Silvani don't steal. But they're paying attention to something.\""
        ),
        (
            "Why Limited Stock",
            "*He gestures at the single wagon.*\n\n"
            "\"You see one wagon. One mule. I'm not Hemlock with a storeroom — everything I carry "
            "is what I could fit past the bandits and the fog and whatever else the road threw at me. "
            "One piece of real gear per customer. That's the rule.\"\n\n"
            "*He holds up a finger.* \"Consumables, sure, take what you need. But the steel? "
            "One item. I need stock for the next town.\""
        ),
    ]

    # ── Pre-build stock data (shared across all player views) ────────────
    gear_keys, consumable_keys = get_caravan_stock()
    gear_buyers = set()  # UIDs who already bought gear — shared across clicks

    ALL_REGS = {
        **{k: ("weapon", WEAPONS[k]) for k in WEAPONS},
        **{k: ("armor", ARMOR[k]) for k in ARMOR},
        **{k: ("head", HEADGEAR[k]) for k in HEADGEAR},
        **{k: ("boots", BOOTS[k]) for k in BOOTS},
        **{k: ("accessory", ACCESSORIES[k]) for k in ACCESSORIES},
        **{k: ("consumable", CONSUMABLES[k]) for k in CONSUMABLES},
    }

    def _fmt(key):
        cat, item = ALL_REGS[key]
        name = item["name"]
        val = item["value"]
        if cat == "weapon":
            return f"**{name}** · +{item['attack_bonus']} ATK d{item['damage_die']} · {val}g"
        elif cat in ("armor", "head", "boots"):
            cls = f" *({'/'.join(item['classes'])})*" if item.get("classes") else ""
            return f"**{name}** · +{item['defense_bonus']} DEF{cls} · {val}g"
        elif cat == "accessory":
            parts = []
            if item.get("defense_bonus"): parts.append(f"+{item['defense_bonus']} DEF")
            if item.get("attack_bonus"):  parts.append(f"+{item['attack_bonus']} ATK")
            cls = f" *({'/'.join(item['classes'])})*" if item.get("classes") else ""
            return f"**{name}** · {', '.join(parts)}{cls} · {val}g"
        else:
            hp = item.get("hp_restore", 0)
            if hp: stat = f"+{hp} HP"
            elif item.get("description"): stat = item["description"].split(".")[0].strip()
            else: stat = "misc"
            return f"**{name}** · {stat} · {val}g"

    def _build_shop_embed(gil=None):
        """Build the shop embed (reused for each player visit)."""
        cat_items = {"🗡️ Weapons": [], "🛡️ Armor": [], "🪖 Headgear": [],
                     "👢 Boots": [], "💍 Accessories": []}
        cat_map = {"weapon": "🗡️ Weapons", "armor": "🛡️ Armor", "head": "🪖 Headgear",
                   "boots": "👢 Boots", "accessory": "💍 Accessories"}
        for k in gear_keys:
            cat, _ = ALL_REGS[k]
            cat_items[cat_map[cat]].append(_fmt(k))

        embed = discord.Embed(
            title="🐪 Corvus Road Trading Co.",
            description=(
                "*Tier III goods — forged in Grimstone, tempered on the road.*\n"
                "**⚠️ LIMIT: One gear item per customer. Consumables unlimited.**"
            ),
            color=0xc8a45c
        )
        for section, lines in cat_items.items():
            if lines:
                embed.add_field(name=section, value="\n".join(lines), inline=False)
        if consumable_keys:
            embed.add_field(
                name="🧪 Consumables",
                value="\n".join(_fmt(k) for k in consumable_keys),
                inline=False
            )
        footer = "Select an item below to buy · 💬 Talk for road news"
        if gil is not None:
            footer = f"💰 Your Gil: {gil}g  ·  " + footer
        embed.set_footer(text=footer)
        return embed

    # ── Per-player shop view (sent ephemeral on Visit click) ─────────────
    def _make_caravan_shop_view():
        """Create a fresh CaravanShopView — each player gets their own."""
        view = discord.ui.View(timeout=300)  # 5 min per player session

        # Gear selects (rows 0 & 1) — chunked at 25
        chunks = [gear_keys[i:i + 25] for i in range(0, len(gear_keys), 25)]
        for idx, chunk in enumerate(chunks):
            if idx >= 2: break
            options = []
            for k in chunk:
                item = find_item(k)
                if not item: continue
                options.append(discord.SelectOption(
                    label=f"{item['name']} ({item['value']}g)"[:100], value=k
                ))
            if options:
                placeholder = "⚔️ Buy gear (1 per customer)..." if idx == 0 else "⚔️ Buy gear (continued)..."
                gear_sel = discord.ui.Select(
                    placeholder=placeholder, options=options, row=idx
                )

                async def _buy_gear(interaction: discord.Interaction):
                    await interaction.response.defer(ephemeral=True)
                    uid = str(interaction.user.id)
                    sheet = await load(uid)
                    if not sheet:
                        await interaction.followup.send(
                            embed=discord.Embed(description="No character found. (`!rpg new`)", color=0xcc4444),
                            ephemeral=True
                        )
                        return
                    if sheet.get("location") not in TOWN_LOCATIONS:
                        await interaction.followup.send(
                            embed=discord.Embed(description="You need to be in town to buy from the caravan.", color=0xcc4444),
                            ephemeral=True
                        )
                        return
                    if uid in gear_buyers:
                        await interaction.followup.send(
                            embed=discord.Embed(
                                description=(
                                    "*The merchant shakes his head.*\n\n"
                                    "\"One piece of gear, friend. I told you — I need stock for the next town. "
                                    "Consumables are still open if you need supplies.\""
                                ),
                                color=0xcc4444
                            ), ephemeral=True
                        )
                        return

                    chosen = interaction.data["values"][0]
                    cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
                    success, purchase_msg, updated = process_purchase(
                        sheet, chosen, 1, sheet.get("reputation", 0), cha_mod=cha_mod
                    )
                    if success:
                        item = find_item(chosen)
                        if item and item["category"] in ("weapon", "armor", "head", "boots", "accessory"):
                            slot = item["category"]
                            if not updated["equipment"].get(slot):
                                updated["inventory"].remove(item["key"])
                                updated["equipment"][slot] = item
                                purchase_msg += f"\nAuto-equipped **{item['name']}**."
                        await save(updated)
                        gear_buyers.add(uid)
                        await interaction.followup.send(
                            embed=discord.Embed(description=f"🐪 {purchase_msg}", color=0x44aa44),
                            ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            embed=discord.Embed(description=purchase_msg, color=0xcc4444),
                            ephemeral=True
                        )

                gear_sel.callback = _buy_gear
                view.add_item(gear_sel)

        # Consumable select (row 2)
        cons_options = []
        for k in consumable_keys:
            item = find_item(k)
            if not item: continue
            cons_options.append(discord.SelectOption(
                label=f"{item['name']} ({item['value']}g)"[:100], value=k
            ))
        if cons_options:
            cons_sel = discord.ui.Select(
                placeholder="🧪 Buy consumables...",
                options=cons_options, row=2
            )

            async def _buy_consumable(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                uid = str(interaction.user.id)
                sheet = await load(uid)
                if not sheet:
                    await interaction.followup.send(
                        embed=discord.Embed(description="No character found.", color=0xcc4444),
                        ephemeral=True
                    )
                    return
                if sheet.get("location") not in TOWN_LOCATIONS:
                    await interaction.followup.send(
                        embed=discord.Embed(description="You need to be in town to buy from the caravan.", color=0xcc4444),
                        ephemeral=True
                    )
                    return

                chosen = interaction.data["values"][0]
                cha_mod = (sheet.get("stats", {}).get("cha", 10) - 10) // 2
                success, purchase_msg, updated = process_purchase(
                    sheet, chosen, 1, sheet.get("reputation", 0), cha_mod=cha_mod
                )
                if success:
                    await save(updated)
                    await interaction.followup.send(
                        embed=discord.Embed(description=f"🐪 {purchase_msg}", color=0x44aa44),
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        embed=discord.Embed(description=purchase_msg, color=0xcc4444),
                        ephemeral=True
                    )

            cons_sel.callback = _buy_consumable
            view.add_item(cons_sel)

        # Talk button (row 3)
        talk_btn = discord.ui.Button(
            label="Talk", emoji="💬",
            style=discord.ButtonStyle.secondary, row=3
        )

        async def _talk(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            title, body = CARAVAN_TALK[secrets.randbelow(len(CARAVAN_TALK))]
            await interaction.followup.send(
                embed=discord.Embed(title=f"🐪 {title}", description=body, color=0xc8a45c),
                ephemeral=True
            )

        talk_btn.callback = _talk
        view.add_item(talk_btn)
        return view

    # ── Arrival Announcement View (posted to channel) ────────────────────
    class CaravanArrivalView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=43200)  # 12 hours

            visit_btn = discord.ui.Button(
                label="Visit Caravan", emoji="🐪",
                style=discord.ButtonStyle.primary, row=0
            )

            async def _visit(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                uid = str(interaction.user.id)
                sheet = await load(uid)
                if not sheet:
                    await interaction.followup.send(
                        embed=discord.Embed(description="You don't have a character. (`!rpg new`)", color=0xcc4444),
                        ephemeral=True
                    )
                    return
                if sheet.get("location") not in TOWN_LOCATIONS:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            description="You need to be in town to visit the caravan. Travel to Oakhaven first.",
                            color=0xcc4444
                        ),
                        ephemeral=True
                    )
                    return

                # Send the actual shop interface as an ephemeral response
                shop_embed = _build_shop_embed(gil=sheet.get("gil", 0))
                shop_view = _make_caravan_shop_view()
                await interaction.followup.send(
                    embed=shop_embed, view=shop_view, ephemeral=True
                )

            visit_btn.callback = _visit
            self.add_item(visit_btn)

            talk_btn = discord.ui.Button(
                label="Talk", emoji="💬",
                style=discord.ButtonStyle.secondary, row=0
            )

            async def _talk_quick(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=True)
                title, body = CARAVAN_TALK[secrets.randbelow(len(CARAVAN_TALK))]
                await interaction.followup.send(
                    embed=discord.Embed(title=f"🐪 {title}", description=body, color=0xc8a45c),
                    ephemeral=True
                )

            talk_btn.callback = _talk_quick
            self.add_item(talk_btn)

        async def on_timeout(self):
            try:
                await channel.send(embed=discord.Embed(
                    description=(
                        "*The merchant folds the canvas, hitches the mule, and rolls north "
                        "without a word. By the time anyone looks, the wagon is a speck on "
                        "the Trade Road.*\n\n"
                        "*The caravan has departed.*"
                    ),
                    color=0x888888
                ))
            except Exception:
                pass

    # ── Post the Arrival Announcement ────────────────────────────────────
    arrival_embed = discord.Embed(
        title="🐪 A Caravan Arrives",
        description=(
            "*Tier III goods — forged in Grimstone, tempered on the road.*\n"
            "**⚠️ LIMIT: One gear item per customer. Consumables unlimited.**\n\n"
            "A traveling merchant sets up shop in Oakhaven.\n"
            "*\"Grimstone masterworks! Tempered on the road, forged for the brave! Come see the Corvus Road Trading Co.!\"*"
        ),
        color=0xc8a45c
    )
    arrival_embed.set_footer(text="Merchant departs at midnight · Visit to see stock")
    
    view = CaravanArrivalView()
    await channel.send(embed=arrival_embed, view=view)

    # Update and Save World State
    from utils.ttrpg.world_state import load_world_state, async_save_world_state
    state = load_world_state()
    state["caravan_active"] = True
    await async_save_world_state(state)

    await _log_world_event("🐪 **A traveling caravan** arrived in Oakhaven — tier III goods available until midnight.")
    log_action("Noon Event: Caravan Arrival (full merchant)")

async def run_bard_performance(bot_ctx, channel):
    """Noon event: Caelindra performs an LLM-generated ballad about recent world events."""
    import discord, os, json, asyncio
    import uuid as _uuid
    from utils.infrastructure.logging.kaia_logger import log_action, log_error
    from utils.infrastructure.system.yaml_config import config
    from utils.ttrpg.character_manager import load_all
    from utils.ttrpg.broadcast import log_world_event as _log_world_event

    # Load recent world events for song material
    events_path = os.path.join("memory", "ttrpg", "world_events.json")
    recent_events = []
    if os.path.exists(events_path):
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                recent_events = json.load(f)[-6:]
        except Exception:
            pass

    # Top adventurers for name-drops
    all_sheets = await load_all()
    top_adventurers = sorted(all_sheets, key=lambda s: s.get("xp", 0), reverse=True)[:4]
    names = [s["character_name"] for s in top_adventurers]

    events_str = "\n".join([f"- {e}" for e in recent_events]) if recent_events else "- A quiet season. The forest waits."
    names_str = ", ".join(names) if names else "the adventurers of Oakhaven"

    # Build prompt (mirrors _handle_bard_song pattern)
    prompt = (
        f"You are Caelindra the Bard performing at the Stone Hearth Inn in Oakhaven.\n"
        f"Recent events:\n{events_str}\n\n"
        f"Notable adventurers: {names_str}\n\n"
        f"Write a ballad (4-10 lines) about these deeds. "
        f"Voice: dry, specific, sardonic — like a journalist who found melody. "
        f"It MUST name at least one adventurer. Reference a specific event. "
        f"Output only the ballad, no preamble."
    )

    song_text = "*Caelindra strums a chord, hums something, then shrugs and orders another drink.*"
    try:
        from utils.social.kaia_social_responder import load_persona_async
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager, gpu_memory_manager, GPUTaskPriority

        persona = await load_persona_async()
        gpu_manager = OllamaGPUManager(config.chat_model)
        opts = gpu_manager.get_gpu_options(for_chat=True)
        opts["num_predict"] = 180
        opts["temperature"] = 0.95

        resp = await gpu_memory_manager.run_with_gpu_guard(
            model_name=config.chat_model,
            priority=GPUTaskPriority.CHAT,
            coro=asyncio.wait_for(
                bot_ctx.ollama_client.chat(
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
            task_id=f"bard_noon_{_uuid.uuid4().hex[:8]}"
        )
        raw = resp["message"]["content"].strip().replace("```", "")
        if raw:
            song_text = raw
    except Exception as e:
        log_error(f"[bard noon event] LLM call failed: {e}")

    embed = discord.Embed(
        title="🎵 Caelindra Performs",
        description=f"*{song_text}*",
        color=0x9b59b6
    )
    embed.set_footer(text="The Stone Hearth goes quiet for a moment. Then Mira refills something.")
    await channel.send(embed=embed)

    await _log_world_event("🎵 **Caelindra the Bard** performed a ballad at the Stone Hearth.")
    log_action("Noon Event: Bard Performance (LLM)")

