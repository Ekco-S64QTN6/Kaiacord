import asyncio
import psutil
import os
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import (
    log_info, log_debug, log_error, log_action, log_success,
)

# Dependencies managed via AppContext
ctx = None

# Memory audit tracking variables
_last_log_rss = 0.0
_first_run = True

# The bot's own RSS above which it collects garbage and says so. A constant:
# it was read through getattr on the config object, which has no such
# attribute, so no setting ever reached it.
MEMORY_CRITICAL_MB = 12000

# Counter for full hourly scans (every 12th tick of a 5-minute loop = 60 min)
_rag_tick_count = 0

@tasks.loop(minutes=5)
async def rag_maintenance_task():
    """Periodic RAG maintenance: check for .trigger_reindex every 5 min, full scan hourly."""
    global _rag_tick_count
    if not ctx or not ctx.rag:
        return
        
    try:
        from utils.core.rag_executor import run_rag
        
        # 0. Ensure initialization is complete
        if not getattr(ctx.rag, '_initialized', False):
            log_debug("RAG initialization not complete. Skipping periodic self-heal.")
            return

        _rag_tick_count += 1
            
        # Check if a manual trigger exists
        from utils.core.rag_utils import reindex_trigger_path
        trigger_path = str(reindex_trigger_path())
        force_sweep = os.path.exists(trigger_path)
        is_hourly = (_rag_tick_count % 12 == 0)  # Full scan every ~60 minutes
        
        if force_sweep:
            log_info("🔗 Detected .trigger_reindex. Performing maintenance sweep...")
            try: os.remove(trigger_path)
            except Exception: pass
        elif is_hourly:
            log_action("Periodic RAG self-heal starting (hourly)...")
        else:
            # No trigger and not the hourly tick — skip
            return
        
        # 1. Scan for new/changed/deleted files (Self-Heal)
        await run_rag(ctx.rag.refresh_knowledge_base)
        
        # 2. Persist if needed (only if persist_async wasn't already triggered)
        if getattr(ctx.rag, 'persist_needed', False):
            await ctx.rag.persist_async()
            
        log_success("RAG maintenance complete.")
    except Exception as e:
        log_error(f"RAG maintenance failed: {e}")


@tasks.loop(minutes=15)
async def memory_audit_task():
    """Periodic memory audit and cleanup."""
    global _last_log_rss, _first_run
    if not ctx or not ctx.rate_limiter or not ctx.persistent_state_manager:
        return
        
    try:
        process = psutil.Process()
        rss_mb = process.memory_info().rss / 1024 / 1024
        
        current_rss = rss_mb
        
        rss_delta = abs(current_rss - _last_log_rss)
        
        if _first_run or rss_delta >= 50.0:
            log_info(f"Memory Audit: RSS {rss_mb:.1f} MB")
            _last_log_rss = current_rss
            _first_run = False
        else:
            log_debug(f"Memory Audit: RSS {rss_mb:.1f} MB")
        
        NORMAL_THRESHOLD_MB = MEMORY_CRITICAL_MB
        
        if rss_mb > NORMAL_THRESHOLD_MB:
            # This is the bot's own RAM. The GPU is Ollama's, and the bot holds
            # none of it, so "clearing GPU memory" here did nothing while the
            # log line said it had. Collect garbage and report what it freed.
            import gc
            from utils.infrastructure.logging.kaia_logger import log_critical
            freed = await asyncio.to_thread(gc.collect)
            after = psutil.Process().memory_info().rss / 1024 / 1024
            log_critical(f"Memory usage critical ({rss_mb:.1f}MB > {NORMAL_THRESHOLD_MB}MB). "
                         f"Garbage collection freed {freed} objects; RSS now {after:.1f}MB.")
            
        # Cleanup rate limiter to prevent unbounded memory growth
        ctx.rate_limiter.cleanup()
        
        # Save state (Offload to thread to prevent blocking the loop)
        await ctx.persistent_state_manager.save_state_async(ctx.personalization_engine)
            
    except Exception as e:
        log_error(f"Memory audit task failed: {e}")

def start_maintenance_tasks(app_ctx):
    global ctx
    ctx = app_ctx
    
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    
    rag_maintenance_task.start()
    if rag_maintenance_task.get_task():
        task_registry.register("rag_maintenance_task", rag_maintenance_task.get_task())
    
    memory_audit_task.start()
    if memory_audit_task.get_task():
        task_registry.register("memory_audit_task", memory_audit_task.get_task())
    
    log_action("Maintenance background tasks started.")

def stop_maintenance_tasks():
    rag_maintenance_task.stop()
    memory_audit_task.stop()
