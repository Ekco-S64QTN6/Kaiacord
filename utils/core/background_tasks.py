import asyncio
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
        
    def _make_news_refresh_task(self):
        @tasks.loop(hours=12)
        async def news_refresh_task():
            if shutdown_manager.shutting_down: return
            try:
                log_action("Running periodic news refresh...")
                from tools.maintenance.refresh_news import refresh_news
                await refresh_news()
                log_success("Periodic news refresh completed.")
            except Exception as e:
                log_error(f"News refresh task failed: {e}")

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
                last_dream = getattr(self.ctx.bot_state, 'last_dream_date', "")
                today = now.strftime('%Y-%m-%d')
                
                if last_dream != today:
                    log_action("Nightly dream processing starting...")
                    try:
                        from utils.social.kaia_social_responder import load_persona_async
                        persona_content = await load_persona_async()
                        await self.ctx.dream_engine.nightly_dream_processing(persona_content)
                        
                        from utils.core.rag_executor import run_rag as run_rag_func
                        await run_rag_func(self.ctx.rag.refresh_knowledge_base)
                        
                        self.ctx.bot_state.last_dream_date = today
                        self.ctx.bot_state.save()
                    except Exception as e:
                        log_error(f"Nightly dream task failed: {e}")

        @dream_engine_task.error
        async def dream_engine_error(error):
            log_error(f"CRITICAL: Dream engine task died: {error}")
            
        return dream_engine_task

    async def run_news_update(self):
        """Run integrated news refresh."""
        if not self.ctx: return
        try:
            log_action("Starting integrated news refresh...")
            from tools.maintenance.refresh_news import refresh_news
            await refresh_news()
            
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
        self.news_refresh_task.start()
        # tasks.loop objects are not asyncio.Task, use get_task()
        if self.news_refresh_task.get_task():
            task_registry.register("news_refresh_task", self.news_refresh_task.get_task())
        self.dream_engine_task.start()
        if self.dream_engine_task.get_task():
            task_registry.register("dream_engine_task", self.dream_engine_task.get_task())
        log_action("Core background tasks started via CoreTaskManager.")

    def stop(self):
        self.news_refresh_task.stop()
        self.dream_engine_task.stop()

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
