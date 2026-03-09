# Standard Library
import argparse
import asyncio
import concurrent.futures
import logging
import os
import random
import re
import sys
import threading
import time
import traceback
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Suppress harmless POSIX semaphore cleanup warnings from LlamaIndex tokenizer subprocesses
warnings.filterwarnings("ignore", message=".*semaphore.*", module="multiprocessing.resource_tracker")

# Third-Party Libraries
import discord
from discord.ext import commands
from dotenv import load_dotenv
import ollama
import psutil

load_dotenv()

# Internal Modules
from utils.core.background_tasks import run_news_update
from utils.core.kaia_dream import DreamEngine
from utils.core.kaia_intelligence import ContextOptimizer, IntentParser, ModelWarmPool, RelevanceFeedback
from utils.core.kaia_rag import KaiaRAG
from utils.core.message_processor import MessageProcessor
from utils.core.performance_monitor import PerformanceMonitor
from utils.infrastructure.logging.kaia_logger import log_action, log_debug, log_error, log_info, log_success, log_warning
from utils.infrastructure.logging.unified_logging import logger, replace_all_logging
from utils.infrastructure.monitoring.async_task_registry import task_registry
from utils.infrastructure.monitoring.stats_tracker import stats_tracker
from utils.infrastructure.system.app_context import AppContext
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.dashboard_manager import DashboardManager
from utils.infrastructure.system.messaging import send_kaia_response
from utils.infrastructure.system.performance_optimizer import ResponseOptimizer, timed_response
from utils.infrastructure.system.rate_limiter import RateLimiter
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from utils.infrastructure.system.yaml_config import config
from utils.news.kaia_news import NewsManager, NewsRetrievalEnhancer, RAGEnhancer

# ─────────────────────────────────────────────
# PHASE 0 — Minimal synchronous setup only.
# NO heavy I/O, NO Ollama calls, NO RAG here.
# ─────────────────────────────────────────────

# Global application context
ctx = AppContext()
ctx.config = config
ctx.bot_state = bot_state
ctx.ollama_client = ollama.AsyncClient(timeout=config.llm_request_seconds)
ctx.stats_tracker = stats_tracker
ctx.rate_limiter = RateLimiter(config.requests_per_minute)
ctx.shutdown_manager = shutdown_manager
ctx.news_manager = NewsManager()


# Late-bound helpers (no I/O at construction time)
ctx.news_enhancer = NewsRetrievalEnhancer()
ctx.rag_enhancer = RAGEnhancer()

# GPU startup serialization lock — prevents simultaneous Ollama GPU claims
_gpu_startup_lock = asyncio.Lock()

# Initialize Bot (lightweight — no I/O)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
ctx.bot = bot


# ─────────────────────────────────────────────
# Logic layer object graph — created once,
# populated lazily after Discord connects.
# ─────────────────────────────────────────────

def _build_logic_layer_sync():
    """
    Construct all stateful objects synchronously during Phase 0 — before
    bot.start() is ever called.  No disk I/O, no Ollama calls, no awaits.
    Constructor side-effects that do I/O must be audited and removed from
    the affected classes; if any constructor *must* do I/O it should be
    refactored to a lazy .initialize_async() call instead.
    """
    from utils.core.kaia_intelligence import PersonalizationEngine, PersistentStateManager

    ctx.performance_monitor = PerformanceMonitor()
    # ModelWarmPool and IntentParser moved to on_ready (Phase 1.5) 
    # to avoid early VRAM consumption during boot.
    ctx.model_warm_pool = None
    ctx.intent_parser = None

    response_optimizer = ResponseOptimizer()
    context_optimizer = ContextOptimizer(
        model_name=config.chat_model, max_tokens=config.max_context_tokens
    )

    ctx.rag = KaiaRAG()
    shutdown_manager.register_rag(ctx.rag)
    ctx.dream_engine = DreamEngine(config, ctx.rag)
    relevance_feedback = RelevanceFeedback(ctx.rag)

    ctx.personalization_engine = PersonalizationEngine()
    ctx.persistent_state_manager = PersistentStateManager()

    ctx.message_processor = MessageProcessor(
        ctx=ctx,
        response_optimizer=response_optimizer,
        context_optimizer=context_optimizer,
        relevance_feedback=relevance_feedback,
        news_enhancer=ctx.news_enhancer,
        rag_enhancer=ctx.rag_enhancer,
    )

    try:
        from utils.infrastructure.gpu.clear_gpu_memory import clear_gpu_memory
        ctx.clear_gpu_memory = lambda: asyncio.to_thread(clear_gpu_memory, silent=True)
    except ImportError:
        pass
    except Exception as e:
        log_error(f"Failed to register GPU memory clearing: {e}")


# on_ready() will never need to wait for this.
# _build_logic_layer_sync() is now called in main() before bot start.




from utils.core.rag_executor import run_rag, run_rag_retrieval


# ─────────────────────────────────────────────
# PHASE 1 — on_ready: claim GPU for chat model
# PHASE 2 — mark bot ready immediately after
# PHASE 3 — background: CPU models + RAG + tasks
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    log_info(f"Discord gateway connected as {bot.user}.")
    # Object graph is already built (synchronous Phase 0). No waiting needed.

    if ctx.rag:
        ctx.rag._bot_user_id = bot.user.id

    # Register guild member names for Knowledge Boundary
    if ctx.message_processor and hasattr(ctx.message_processor, "knowledge_boundary"):
        all_names = set()
        for guild in bot.guilds:
            for member in guild.members:
                all_names.add(member.name)
                if member.display_name != member.name:
                    all_names.add(member.display_name)
        ctx.message_processor.knowledge_boundary.register_usernames(all_names)
        log_info(f"Registered {len(all_names)} guild member names in Knowledge Boundary.")

    # ── PHASE 1: Exclusive GPU warm for chat model ──────────────────────────
    # Runs alone — no other Ollama calls permitted concurrently.
    async with _gpu_startup_lock:
        async def _do_phase1():
            log_action(f"[Phase 1] Claiming GPU for {config.chat_model}...")
            # We fire the predictably check into the background so slow VRAM loads don't hit socket timeouts
            nonlocal _load_task
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_mgr = OllamaGPUManager(config.chat_model)
            # Use EXACT SAME options as chat to prevent VRAM re-allocation later
            options = gpu_mgr.get_gpu_options(for_chat=True)
            # Force 1 token predict for speed, but preserve other chat flags
            options['num_predict'] = 1
            
            _load_task = asyncio.create_task(
                ctx.ollama_client.generate(
                    model=config.chat_model,
                    prompt=".",
                    options=options,
                    keep_alive=-1,
                ),
                name=f"prewarm_{config.chat_model}"
            )
            task_registry.register(f"prewarm_{config.chat_model}", _load_task)
            _load_task.add_done_callback(
                lambda t: log_warning(f"Pre-warm of {config.chat_model} failed: {t.exception()}")
                if not t.cancelled() and t.exception() else None
            )
            
            # Poll Ollama's process list to confirm the chat model is actually resident in VRAM
            _vram_confirmed = False
            _resident_confirmed = False
            start_time = asyncio.get_running_loop().time()
            last_log_time = start_time
            max_wait = config.model_load_timeout + 120.0
            
            while asyncio.get_running_loop().time() - start_time < max_wait:
                await asyncio.sleep(2.0)
                current_time = asyncio.get_running_loop().time()
                if current_time - last_log_time > 20.0:
                    log_info(f"[Phase 1] Still waiting for {config.chat_model} residency... ({int(current_time - start_time)}s elapsed)")
                    last_log_time = current_time

                try:
                    _ps = await asyncio.to_thread(ollama.ps)
                    _models = _ps.get("models") or [] if isinstance(_ps, dict) else getattr(_ps, 'models', [])
                    
                    if not _models:
                        log_debug(f"[Phase 1] ps() returned no models (still loading or idle)...")
                        
                    for m in _models:
                        name = getattr(m, 'name', m.get('name', '') if isinstance(m, dict) else '')
                        size_vram = getattr(m, 'size_vram', m.get('size_vram', 0) if isinstance(m, dict) else 0)
                        base_model = config.chat_model.split(":")[0]
                        if (base_model in name or name in config.chat_model or config.chat_model in name):
                            _resident_confirmed = True
                            if size_vram > 0:
                                _vram_confirmed = True
                            break
                    
                    if _vram_confirmed:
                        # Wait for prewarm generate() to complete so Ollama is free
                        if _load_task and not _load_task.done():
                            log_info("[Phase 1] VRAM confirmed. Waiting for prewarm generate() to finish...")
                            try:
                                await asyncio.wait_for(_load_task, timeout=60.0)
                            except Exception:
                                pass
                        break   # ✅ genuinely in VRAM — done
                    if _resident_confirmed and current_time - start_time > 60.0:
                        # ⚠️  Model is resident in ps() but size_vram == 0.
                        # Ollama fell back to system RAM (likely CUDA wasn't ready at load time).
                        log_warning(f"[Phase 1] {config.chat_model} loaded into SYSTEM RAM (size_vram=0). "
                                    f"Triggering unload → GPU reload cycle...")
                        break
                except Exception as e:
                    log_debug(f"[Phase 1] ps() poll failed: {type(e).__name__}: {e}")
                
                # [BUG 2 FIX]: If ps() didn't confirm, check if generate() task completed.
                # A completed generate task with keep_alive=-1 guarantees residency.
                if not _resident_confirmed and _load_task and _load_task.done() and not _load_task.cancelled():
                    try:
                        _load_task.result() # Raises if prewarm failed
                        _resident_confirmed = True
                        log_info(f"[Phase 1] generate() completed — model is resident (VRAM unconfirmed by ps).")
                        break
                    except Exception as task_err:
                        log_error(f"[Phase 1] prewarm task failed: {task_err}")
                        break

            # ─── GPU Reload Retry ─────────────────────────────────────────────────
            if _resident_confirmed and not _vram_confirmed:
                try:
                    if _load_task and not _load_task.done():
                        _load_task.cancel()
                        try:
                            await _load_task
                        except (asyncio.CancelledError, Exception):
                            pass
                    # Force full unload
                    log_action(f"[Phase 1] Unloading CPU-resident {config.chat_model}...")
                    await asyncio.wait_for(
                        ctx.ollama_client.generate(model=config.chat_model, keep_alive=0),
                        timeout=15.0
                    )
                except Exception:
                    pass

                log_info("[Phase 1] Waiting 8s for CUDA context to stabilize before GPU retry...")
                await asyncio.sleep(8.0)

                log_action(f"[Phase 1] Retry: re-claiming GPU for {config.chat_model}...")
                _load_task = asyncio.create_task(
                    ctx.ollama_client.generate(
                        model=config.chat_model,
                        prompt=".",
                        options=options,
                        keep_alive=-1,
                    ),
                    name=f"prewarm_retry_{config.chat_model}"
                )
                task_registry.register(f"prewarm_retry_{config.chat_model}", _load_task)

                retry_start = asyncio.get_running_loop().time()
                _vram_confirmed = False
                while asyncio.get_running_loop().time() - retry_start < 120.0:
                    await asyncio.sleep(2.0)
                    try:
                        _ps = await asyncio.to_thread(ollama.ps)
                        _models = _ps.get("models") or [] if isinstance(_ps, dict) else getattr(_ps, 'models', [])
                        for m in _models:
                            name = getattr(m, 'name', m.get('name', '') if isinstance(m, dict) else '')
                            size_vram = getattr(m, 'size_vram', m.get('size_vram', 0) if isinstance(m, dict) else 0)
                            base_model = config.chat_model.split(":")[0]
                            if (base_model in name or name in config.chat_model or config.chat_model in name):
                                if size_vram > 0:
                                    _vram_confirmed = True
                                break
                        if _vram_confirmed:
                            break
                    except Exception as e:
                        log_debug(f"[Phase 1 retry] ps() poll error: {e}")

                if _vram_confirmed:
                    log_success(f"[Phase 1] GPU retry succeeded — {config.chat_model} now in VRAM.")
                else:
                    log_error(f"[Phase 1] GPU retry FAILED. Model may still be in system RAM.")

            return _vram_confirmed

        _load_task = None
        try:
            _phase1_success = await _do_phase1()
        except Exception as e:
            log_error(f"[Phase 1] Pre-warm error: {e}")
            _phase1_success = False
            if _load_task:
                try:
                    _load_task.cancel()
                except Exception:
                    pass

    if _phase1_success:
        log_success(f"[Phase 1] VRAM lock confirmed for {config.chat_model}.")
    else:
        log_error(f"[Phase 1] ⚠️  {config.chat_model} failed to load into VRAM. "
                  f"Running on CPU — responses will be very slow. "
                  f"Run `ollama ps` and `nvidia-smi` to investigate.")

    # ── PHASE 1.5: Late-initialize CPU models ───────────────────────────────
    # We build these AFTER the chat model has claimed the GPU to prevent
    # VRAM contention during the initial load window.
    log_action("[Phase 1.5] Initializing secondary models...")
    ctx.model_warm_pool = ModelWarmPool(ctx.ollama_client)
    ctx.intent_parser = IntentParser(
        ctx.ollama_client,
        model=config.get('models.classification_model', 'gemma2:2b'),
        timeout=config.classification_timeout,
    )
    if ctx.message_processor:
        ctx.message_processor.intent_parser = ctx.intent_parser

    # ── PHASE 2: Bot is now ready to serve messages ─────────────────────────
    ctx.set_ready()
    bot_state.boot_complete = True
    log_success("[Phase 2] Kaia is ready to respond.")

    # Start maintenance loops (uptime, dashboard refresh, etc.)
    from utils.infrastructure.system.maintenance_tasks import start_maintenance_tasks
    start_maintenance_tasks(ctx)

    # Start loop watchdog
    try:
        from utils.infrastructure.monitoring.watchdog import watchdog
        watchdog.start(asyncio.get_running_loop())
    except Exception as e:
        log_error(f"Failed to start LoopWatchdog: {e}")

    # ── PHASE 3: Heavy background init (non-blocking) ───────────────────────
    asyncio.create_task(_phase3_background_init())


async def _phase3_background_init():
    """
    All heavy initialization that must not block Discord or GPU loading.
    Runs as a background task after the bot is already serving messages.

    Operations are deliberately STAGGERED, not gathered, to avoid
    simultaneous disk I/O + embedding load spikes that can destabilize
    Ollama's VRAM scheduler in the first 30s after boot.
    """
    import utils.core.background_tasks as bg_tasks
    bg_tasks.ctx = ctx

    # 3a. Brief yield to let the event loop breathe after Discord connects.
    await asyncio.sleep(2)

    # 3b-i. Load persistent state
    log_action("[Phase 3] Loading persistent state …")
    try:
        await ctx.persistent_state_manager.load_state_async(
            ctx.personalization_engine, ctx.performance_monitor
        )
        log_success("[Phase 3] Persistent state loaded.")
    except Exception as e:
        log_error(f"[Phase 3] Persistent state load error: {e}")

    # 3b-ii. Initialize RAG indices — may trigger embedding calls (CPU-only).
    log_action("[Phase 3] Initializing RAG indices …")
    try:
        from utils.infrastructure.monitoring.watchdog import watchdog
        with watchdog.suppress():
            await ctx.rag.initialize_async()
        log_success("[Phase 3] RAG indices initialized.")
    except Exception as e:
        log_error(f"[Phase 3] RAG init error: {e}")

    # 3c. Warm intent classifier on CPU only.
    try:
        classifier_device = "GPU" if config.get('models.classification_on_gpu', False) else "CPU"
        log_action(f"[Phase 3] Waiting for first chat completion before warming intent classifier...")
        
        # Sequence Fix: Wait for first chat or 10 min fallback to avoid connection serialization stalls
        _wait_start = time.time()
        while not ctx.bot_state.first_chat_done and (time.time() - _wait_start < 600):
            await asyncio.sleep(5.0)
            
        log_action(f"[Phase 3] Warming intent classifier ({config.get('models.classification_model', 'gemma2:2b')}) on {classifier_device} …")
        if ctx.intent_parser:
            await ctx.intent_parser.pre_warm()
        log_success(f"[Phase 3] Intent classifier ready ({classifier_device}).")
    except Exception as e:
        log_error(f"[Phase 3] Intent classifier warm failed: {e}")

    # 3d. RAG knowledge base refresh — scans for new/changed files and embeds them.
    try:
        log_action("[Phase 3] Running background RAG knowledge base refresh …")
        # Bug 2 Fix: Allow Ollama to stabilize after pre-warm before embedding pass
        log_info("Allowing Ollama to stabilize before embedding pass...")
        await asyncio.sleep(3.0)
        await run_rag(ctx.rag.refresh_knowledge_base)
        log_success("[Phase 3] RAG knowledge base refreshed.")
    except Exception as e:
        log_error(f"[Phase 3] RAG refresh error: {e}")

    # 3e. Start all background task loops — news, dreams, social.
    #     These run last so they don't compete for I/O during the critical
    #     first 30 seconds of boot.
    from utils.social.social_tasks import start_social_tasks
    bg_tasks.start_background_core_tasks(ctx)
    start_social_tasks(ctx, on_message)

    if config.startup_news_update:
        log_action("[Phase 3] Launching background news update …")
        asyncio.create_task(run_news_update())

    log_success("[Phase 3] All background systems online. Kaia fully operational.")


# _run_rag_initialize_cpu_only() has been removed.
# Previous versions nested: thread → new event loop → async → thread again.
# This was unnecessary CPU/memory overhead. initialize_async() is awaited
# directly inside _phase3_background_init() which already runs on the main
# event loop as a background task — no thread wrapper needed.


# ─────────────────────────────────────────────
# Message handler
# ─────────────────────────────────────────────

@bot.event
@timed_response(threshold=30.0)
async def on_message(msg: discord.Message):
    if ctx.message_processor:
        await ctx.message_processor.process(msg)
    else:
        log_warning("Message received but processor not yet initialized. Skipping.")


async def process_external_mention(
    content: str, author_name: str, author_id: Any, platform: str
):
    """
    Process mentions from external platforms (Bluesky, X, etc.)
    Constructs a MockMessage that replicates the discord.Message interface 
    enough to satisfy the intelligence pipeline.
    """
    from utils.infrastructure.system.messaging import MockMessage, MockUser, MockChannel
    
    # Create a compatible mock author
    mock_author = MockUser(
        id=author_id if isinstance(author_id, int) else (int(author_id) if str(author_id).isdigit() else 0),
        name=author_name,
        display_name=author_name
    )
    
    # Create a compatible mock channel/context
    mock_channel = MockChannel(id=hash(platform) % 10**10)
    
    # Construct the mock message
    mock_msg = MockMessage(
        content=content,
        author=mock_author,
        channel=mock_channel,
        platform=platform
    )
    
    if ctx.message_processor:
        # Directly process via the modular processor
        # This bypasses the Discord-specific on_ready decorators and 
        # avoids the 'mock_external_mention' proxy which was fragile.
        return await ctx.message_processor.process(mock_msg)
    else:
        log_warning(f"External mention from {platform} received but processor not ready.")
        return None


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    # 1. Initialize Logging FIRST
    replace_all_logging()
    
    from utils.infrastructure.monitoring.stats_tracker import stats_tracker
    from utils.infrastructure.monitoring.stats_poller import stats_poller

    parser = argparse.ArgumentParser(description="Kaiacord - The AI Discord Bot")
    parser.add_argument("--no-gui", action="store_true", help="Run without curses dashboard")
    parser.add_argument(
        "--eager-rag-warm",
        action="store_true",
        help="Eagerly pre-warm BM25 indices after RAG loads (default: lazy)",
    )
    parser.add_argument("--status", action="store_true", help="Check system status and exit")
    args = parser.parse_args()

    if args.status:
        print("\n--- Kaia System Status ---")
        try:
            ollama.list()
            print("Ollama: ✅ ONLINE")
        except Exception:
            print("Ollama: 🔴 OFFLINE")
        return

    ctx.shutdown_manager = shutdown_manager

    dm = DashboardManager(
        ctx=ctx,
        bot=bot,
        config=config,
        bot_state=bot_state,
        stats_tracker=stats_tracker,
        stats_poller=stats_poller,
        logger=logger,
        model_warm_pool=None,
        intent_parser=None,
    )

    async def run_bot_wrapper(sp, stop_event=None):
        dm.intent_parser = ctx.intent_parser
        await dm.run_bot_async(sp, None, dm_sequenced_boot, stop_event)

    async def dm_sequenced_boot():
        """
        Minimal hook for DashboardManager.  Phase 3 heavy work is driven by
        on_ready(), so there is almost nothing to do here — just wire context
        references the dashboard needs.
        """
        import utils.core.background_tasks as bg_tasks
        bg_tasks.ctx = ctx

        # Eager BM25 warm (optional, post-RAG-init)
        if args.eager_rag_warm:
            log_info("Eager RAG pre-warm requested. Will build BM25 after RAG init.")
            # Schedule — RAG must be initialized first (Phase 3 already handles this)
            async def _eager_bm25():
                # Wait until RAG init completes (ctx.rag.initialized or similar flag)
                for _ in range(60):
                    if getattr(ctx.rag, "_initialized", False):
                        break
                    await asyncio.sleep(1)
                await run_rag(ctx.rag.pre_warm)
            asyncio.create_task(_eager_bm25())

    env_mode = os.environ.get("KAIA_DASHBOARD", "curses").lower()
    mode = "simple" if args.no_gui else env_mode

    if mode == "curses":
        if config.get('startup.gpu_cleanup', True):
            from utils.infrastructure.gpu.clear_gpu_memory import kill_orphaned_runners, clear_gpu_memory
            # Optimize: Preserve current chat model to avoid 2-minute reload lag on restart
            kill_orphaned_runners(
                preserve_model=config.chat_model,
                preserve_ctx=config.max_context_tokens,
                force_all=False
            )
            clear_gpu_memory(silent=True)
            import time
            time.sleep(5)  # RESTORED — CUDA needs ~3-5s to reinitialize after runner process kill
        dm.run_curses_mode(_build_logic_layer_sync, run_bot_wrapper)
    else:
        asyncio.run(dm.run_simple_mode(_build_logic_layer_sync, run_bot_wrapper))


if __name__ == "__main__":
    main()
