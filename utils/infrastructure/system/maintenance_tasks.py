import asyncio
import psutil
import sys
import os
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_info, log_debug, log_warning, log_error, log_action
from utils.infrastructure.system.bot_state import bot_state

# Dependencies
_rag = None
# _semantic_cache = None
_personalization_engine = None
_performance_monitor = None
_state_manager = None
_rate_limiter = None
_clear_gpu_memory = None

# Memory audit tracking variables
_last_log_rss = 0.0
_last_log_cache_size = -1
_first_run = True

@tasks.loop(hours=1)
async def rag_maintenance_task():
    """Periodic RAG maintenance: persist index and check for updates"""
    if not _rag:
        return
        
    try:
        if _rag.persist_needed:
            log_action("Periodic RAG persistence...")
            await asyncio.to_thread(_rag.persist)
    except Exception as e:
        log_error(f"RAG maintenance failed: {e}")


@tasks.loop(minutes=15)
async def memory_audit_task():
    """Periodic memory audit and cleanup."""
    global _last_log_rss, _first_run
    if not _rate_limiter or not _state_manager:
        return
        
    try:
        process = psutil.Process()
        rss_mb = process.memory_info().rss / 1024 / 1024
        
        current_rss = rss_mb
        
        rss_delta = abs(current_rss - _last_log_rss)
        cache_changed = current_cache_size != _last_log_cache_size
        
        if _first_run or rss_delta >= 50.0 or cache_changed:
            log_info(f"Memory Audit: RSS {rss_mb:.1f} MB | Cache: {current_cache_size} entries")
            _last_log_rss = current_rss
            _last_log_cache_size = current_cache_size
            _first_run = False
        else:
            log_debug(f"Memory Audit: RSS {rss_mb:.1f} MB | Cache: {current_cache_size} entries")
        
        # Memory cleanup thresholds (in MB)
        NORMAL_THRESHOLD_MB = 8192
        IMAGE_GEN_THRESHOLD_MB = 10240
        
        if bot_state.is_generating_image:
            if rss_mb > IMAGE_GEN_THRESHOLD_MB:
                log_warning(f"Memory usage high ({rss_mb:.1f}MB > {IMAGE_GEN_THRESHOLD_MB}MB), but skipping cleanup due to active image generation.")
        else:
            if rss_mb > NORMAL_THRESHOLD_MB:
                from utils.infrastructure.logging.kaia_logger import log_critical
                log_critical(f"Memory usage critical ({rss_mb:.1f}MB > {NORMAL_THRESHOLD_MB}MB)! Clearing caches and GPU memory.")
                # Cache clearing removed
                if _clear_gpu_memory:
                    _clear_gpu_memory()
            
        # Cleanup rate limiter to prevent unbounded memory growth
        _rate_limiter.cleanup()
        
        # Save state
        _state_manager.save_state(_personalization_engine, _performance_monitor)
            
    except Exception as e:
        log_error(f"Memory audit task failed: {e}")

def start_maintenance_tasks(rag, personalization_engine, performance_monitor, state_manager, rate_limiter, clear_gpu_memory_func=None):
    global _rag, _personalization_engine, _performance_monitor, _state_manager, _rate_limiter, _clear_gpu_memory
    _rag = rag
    # _semantic_cache = semantic_cache
    _personalization_engine = personalization_engine
    _performance_monitor = performance_monitor
    _state_manager = state_manager
    _rate_limiter = rate_limiter
    _clear_gpu_memory = clear_gpu_memory_func
    
    rag_maintenance_task.start()
    memory_audit_task.start()
    # log_enrichment_task.start() # DELETED: Caused high GPU usage

    log_action("Maintenance background tasks started.")

def stop_maintenance_tasks():
    rag_maintenance_task.stop()
    memory_audit_task.stop()
