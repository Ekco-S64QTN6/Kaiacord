import asyncio
import psutil
import os
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import (
    log_info, log_debug, log_warning, log_error, log_action, log_success,
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
            
        # A request is atomically claimed so a concurrent request can create a
        # fresh trigger while this sweep is running. A stale claim is recovered
        # on the next tick if the process died before it could settle the file.
        from utils.core.rag_utils import reindex_trigger_path
        trigger_path = str(reindex_trigger_path())
        claimed_path = trigger_path + ".processing"
        if os.path.exists(claimed_path):
            if os.path.exists(trigger_path):
                # The new trigger subsumes the interrupted request.
                os.remove(claimed_path)
            else:
                os.replace(claimed_path, trigger_path)

        force_sweep = os.path.exists(trigger_path)
        is_hourly = (_rag_tick_count % 12 == 0)  # Full scan every ~60 minutes

        # Indexing and persisting hold the GIL long enough to make the voice
        # thread late. Deferred work remains signalled for the next tick.
        if force_sweep or is_hourly:
            from utils.audio import voice_busy
            busy = voice_busy.playing()
            if busy:
                log_debug(f"RAG maintenance deferred: {busy} is playing")
                return

        claimed = False
        refresh_completed = False
        if force_sweep:
            log_info("🔗 Detected .trigger_reindex. Performing maintenance sweep...")
            try:
                os.replace(trigger_path, claimed_path)
                claimed = True
            except FileNotFoundError:
                # Another writer already removed the request. An hourly sweep
                # may still be due, but there is no manual signal to settle.
                force_sweep = False
        elif is_hourly:
            log_action("Periodic RAG self-heal starting (hourly)...")
        else:
            # No trigger and not the hourly tick — skip
            return

        try:
            # 1. Scan for new/changed/deleted files (Self-Heal)
            refresh_succeeded = await run_rag(ctx.rag.refresh_knowledge_base) is True
            if not refresh_succeeded:
                log_warning("RAG refresh did not complete; preserving its reindex request.")
                return

            # 2. Persist if needed (only if persist_async wasn't already triggered)
            if getattr(ctx.rag, 'persist_needed', False):
                persist_result = await ctx.rag.persist_async()
                if persist_result is False:
                    log_warning("RAG persistence did not complete; preserving its reindex request.")
                    return

            # Mark the claim consumed only after the full operation (including
            # any final persist) has completed without an error.
            refresh_completed = True
            log_success("RAG maintenance complete.")
        finally:
            if claimed and os.path.exists(claimed_path):
                try:
                    if refresh_completed or os.path.exists(trigger_path):
                        # On success the claim is consumed. If a new trigger
                        # arrived during the sweep, it remains at trigger_path.
                        # On failure the new trigger supersedes the old one.
                        os.remove(claimed_path)
                    else:
                        # No newer request exists; put the failed request back.
                        os.replace(claimed_path, trigger_path)
                except OSError as settle_error:
                    log_error(f"Could not settle reindex request: {settle_error}")
                    if os.path.exists(claimed_path) and not os.path.exists(trigger_path):
                        try:
                            os.replace(claimed_path, trigger_path)
                        except OSError as restore_error:
                            log_error(f"Could not restore reindex request: {restore_error}")
    except Exception as e:
        log_error(f"RAG maintenance failed: {e}")


@tasks.loop(minutes=15)
async def memory_audit_task():
    """Periodic memory audit and cleanup."""
    global _last_log_rss, _first_run
    if not ctx or not ctx.rate_limiter or not ctx.persistent_state_manager:
        return
        
    try:
        # RSS, a heap trim (fragmentation measured and given back) and, with
        # diagnostics.memory_trace, what Python itself holds and where it grew.
        from utils.infrastructure.monitoring import mem_probe
        bot = getattr(ctx, "bot", None)
        busy = lambda: any(vc.is_playing() for vc in getattr(bot, "voice_clients", []) or [])
        row = await asyncio.to_thread(mem_probe.sample, busy)
        rss_mb = row["rss_mb"]
        current_rss = row["rss_after_trim_mb"]
        rss_delta = abs(current_rss - _last_log_rss)

        if _first_run or rss_delta >= 50.0 or row.get("trimmed_mb", 0) >= 50.0:
            log_info(mem_probe.describe(row))
            _last_log_rss = current_rss
            _first_run = False
        else:
            log_debug(mem_probe.describe(row))
        
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
            
        # Keep conversation histories and their RAG metadata bounded together.
        try:
            state = getattr(ctx, "bot_state", None)
            if state:
                evicted = state.prune_channel_memory()
                if evicted:
                    state.save()
                stats = state.channel_state_stats()
                rag = getattr(ctx, "rag", None)
                retrievals = rag.retrieval_channel_count() if rag and hasattr(rag, "retrieval_channel_count") else 0
                log_info(f"[channel_state] {stats['channels']} channels, {stats['turns']} turns, "
                         f"{retrievals} with retrievals held; {stats['evicted']} evicted total, "
                         f"{stats['state_bytes']:,} serialized bytes (this pass evicted {len(evicted)})")
        except Exception as channel_state_error:
            log_warning(f"[channel_state] lifecycle audit unavailable: {channel_state_error}")

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
    
    from utils.infrastructure.monitoring import mem_probe
    mem_probe.start_trace()

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
