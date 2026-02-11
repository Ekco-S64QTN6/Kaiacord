import asyncio
import sys
import os
from dataclasses import dataclass, field
from datetime import datetime
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_action, log_success, log_error, log_info, log_warning
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config

# Dependencies — now managed via AppContext
ctx = None

@tasks.loop(hours=12)
async def news_refresh_task():
    """Periodic news refresh to keep the database current."""
    try:
        log_action("Running periodic news refresh...")
        process = await asyncio.create_subprocess_exec(
            sys.executable, "tools/maintenance/refresh_news.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        if process.returncode == 0:
            log_success("Periodic news refresh completed.")
        else:
            log_error(f"Periodic news refresh failed: {stderr.decode()}")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log_error(f"News refresh task failed: {e}")

@tasks.loop(hours=1)
async def dream_engine_task():
    """Nightly dream processing task (runs between 3-5 AM)"""
    if not ctx or not ctx.bot_state or not ctx.config:
        return
        
    if getattr(ctx.bot_state, 'is_generating_image', False):
        return
        
    if not ctx.config.get('features.dream_mode_enabled', True):
        return
        
    if not ctx.dream_engine or not ctx.rag:
        return

    now = datetime.now()
    start_hour = ctx.config.get('dream_mode.schedule_start_hour', 3)
    end_hour = ctx.config.get('dream_mode.schedule_end_hour', 5)
    
    if start_hour <= now.hour < end_hour:
        last_dream = getattr(ctx.bot_state, 'last_dream_date', "")
        today = now.strftime('%Y-%m-%d')
        
        if last_dream != today:
            log_action("Nightly dream processing starting...")
            try:
                # Late import to avoid circular dependency
                from utils.social.kaia_social_responder import load_persona_async
                persona_content = await load_persona_async()
                await ctx.dream_engine.nightly_dream_processing(persona_content)
                await asyncio.to_thread(ctx.rag.refresh_knowledge_base)
                ctx.bot_state.last_dream_date = today
                ctx.bot_state.save()
            except Exception as e:
                log_error(f"Nightly dream task failed: {e}")

async def run_news_update():
    """Run the daily news update script and manual ingestion."""
    if not ctx: return
    
    try:
        # 1. Run manual ingestion first (handles local daily and weekly files)
        log_action("Checking for manual news briefs to ingest...")
        ingest_process = await asyncio.create_subprocess_exec(
            sys.executable, "tools/maintenance/ingest_manual_news.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        try:
            async for line in ingest_process.stdout:
                decoded = line.decode().strip()
                if decoded and not decoded.startswith("[DEBUG]"):
                    print(f"  {decoded}")
            
            await ingest_process.wait()
        except asyncio.CancelledError:
            ingest_process.kill()
            await ingest_process.wait()
            raise

        # 2. Proceed with automated news update script
        log_action("Running daily news update script...")
        # Check for Gemini API key
        if not os.getenv("GEMINI_API_KEY"):
            log_warning("GEMINI_API_KEY not set, skipping automated news update.")
            return

        # Run with live output streaming
        process = await asyncio.create_subprocess_exec(
            sys.executable, "tools/maintenance/update_kaia_news.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT  # Merge stderr to stdout
        )
        
        try:
            # Stream output line by line for live progress
            async for line in process.stdout:
                decoded = line.decode().strip()
                if decoded and not decoded.startswith("[DEBUG]"):
                    print(f"  {decoded}")  # Show in dashboard
            
            await process.wait()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        
        if process.returncode == 0:
            log_success("Daily news update completed.")
            # Trigger RAG refresh after news update
            # Use module-level run_rag link from Kaiacord.py if available, or ctx
            from Kaiacord import run_rag as run_rag_func
            if ctx.rag:
                await run_rag_func(ctx.rag.refresh_knowledge_base)
            # Refresh news_manager cache to pick up new files immediately
            if ctx.news_manager:
                ctx.news_manager.refresh()
        else:
            log_error("Daily news update failed. Check output above.")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log_error(f"Failed to run news update: {e}")

def start_background_core_tasks(app_ctx):
    global ctx
    ctx = app_ctx
    
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    
    news_task = news_refresh_task.start()
    task_registry.register("news_refresh_task", news_task)
    
    dream_task = dream_engine_task.start()
    task_registry.register("dream_engine_task", dream_task)
    
    log_action("Core background tasks started.")

def stop_background_core_tasks():
    news_refresh_task.stop()
    dream_engine_task.stop()
