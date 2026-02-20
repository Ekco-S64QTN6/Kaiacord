import os
import sys
import asyncio
import argparse
import re
import traceback
import random
import time
import logging
import psutil
import threading
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dotenv import load_dotenv
load_dotenv()

# Initialize Unified Logging
from utils.infrastructure.logging.unified_logging import replace_all_logging, logger
replace_all_logging()

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_error, log_action
)

# Core Infrastructure Imports
import ollama
import discord
from discord.ext import commands

from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from utils.infrastructure.monitoring.async_task_registry import task_registry
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.rate_limiter import RateLimiter
from utils.infrastructure.system.messaging import send_kaia_response
from utils.infrastructure.system.dashboard_manager import DashboardManager
from utils.infrastructure.monitoring.stats_tracker import stats_tracker
from utils.infrastructure.system.app_context import AppContext

# Logic Imports
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_dream import DreamEngine
from utils.core.performance_monitor import PerformanceMonitor
from utils.core.kaia_intelligence import (
    ModelWarmPool, ContextOptimizer, RelevanceFeedback, IntentParser
)
from utils.infrastructure.system.performance_optimizer import ResponseOptimizer, timed_response
from utils.core.message_processor import MessageProcessor
from utils.social.kaia_social_responder import load_persona_async
from utils.news.kaia_news import NewsRetrievalEnhancer, NewsManager, RAGEnhancer
from utils.core.background_tasks import run_news_update

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

# Semaphore used by RAG embedding operations — CPU-only, max 2 concurrent
embedding_semaphore = asyncio.Semaphore(2)

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
    ctx.model_warm_pool = ModelWarmPool(ctx.ollama_client)

    # IntentParser object only — NOT warmed here.  Phase 3 loads it on CPU.
    ctx.intent_parser = IntentParser(
        ctx.ollama_client,
        model=config.get('models.classification_model', 'gemma2:2b'), # gemma2:2b — CPU-only
        timeout=config.classification_timeout,
    )

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


# Build the object graph NOW — synchronous, zero I/O, completes in <100ms.
# on_ready() will never need to wait for this.
_build_logic_layer_sync()




from utils.core.rag_executor import run_rag


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
        try:
            log_action(
                f"[Phase 1] Claiming GPU for {config.chat_model} "
                f"({config.max_context_tokens // 1000}k ctx) …"
            )
            await ctx.ollama_client.generate(
                model=config.chat_model,
                prompt=".",
                options={
                    "num_ctx": config.max_context_tokens,
                    "num_gpu": -1,   # force full GPU; all layers on device
                },
            )
            log_success(f"[Phase 1] {config.chat_model} loaded to GPU.")
        except Exception as e:
            log_error(f"[Phase 1] Chat model GPU warm failed: {e}")
            # Non-fatal — bot continues, first real response will trigger lazy load

    # Poll Ollama's process list to confirm the chat model is actually resident
    # in VRAM before proceeding.  Avoids the guesswork of asyncio.sleep().
    _vram_confirmed = False
    for _attempt in range(10):
        try:
            _ps = await asyncio.to_thread(ollama.ps)
            for m in (_ps.get("models") or []):
                name = m.get("name", "")
                size_vram = m.get("size_vram", 0)
                if config.chat_model in name and size_vram > 0:
                    _vram_confirmed = True
                    break
            if _vram_confirmed:
                break
        except Exception:
            pass
        await asyncio.sleep(0.5)

    if _vram_confirmed:
        log_success(f"[Phase 1] VRAM lock confirmed for {config.chat_model}.")
    else:
        # Ollama ps() unavailable or model name mismatch — fall back to fixed delay
        log_info("[Phase 1] Could not confirm VRAM lock via ollama.ps(); waiting 3s as fallback.")
        await asyncio.sleep(3.0)

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

    # 3a. VRAM stabilization window — let gemma3 fully settle into GPU before
    #     anything touches disk, RAM, or Ollama.
    await asyncio.sleep(5)

    # 3b-i. Load persistent state first — pure disk/JSON, no Ollama involvement.
    log_action("[Phase 3] Loading persistent state …")
    try:
        await ctx.persistent_state_manager.load_state_async(
            ctx.personalization_engine, ctx.performance_monitor
        )
        log_success("[Phase 3] Persistent state loaded.")
    except Exception as e:
        log_error(f"[Phase 3] Persistent state load error: {e}")

    # Small breath between disk operations to avoid read contention.
    await asyncio.sleep(2)

    # 3b-ii. Initialize RAG indices — may trigger embedding calls (CPU-only,
    #        num_gpu=0 enforced in KaiaRAG.__init__).  Awaited directly; no
    #        thread wrapper needed because initialize_async() handles its own
    #        threading internally via asyncio.to_thread().
    log_action("[Phase 3] Initializing RAG indices …")
    try:
        await ctx.rag.initialize_async()
        log_success("[Phase 3] RAG indices initialized.")
    except Exception as e:
        log_error(f"[Phase 3] RAG init error: {e}")

    # 3c. Warm intent classifier on CPU only.
    #     10s delay after RAG init gives Ollama time to finish any embedding
    #     model scheduling before loading a second model (gemma2:2b).
    #     Single warm call via pre_warm() — which MUST pass num_gpu: 0 internally.
    #     If IntentParser.pre_warm() does not enforce this, add:
    #       options={"num_gpu": 0}  to its internal generate() call.
    await asyncio.sleep(10)
    try:
        log_action(f"[Phase 3] Warming intent classifier ({config.get('models.classification_model', 'gemma2:2b')}) on CPU …")
        if ctx.intent_parser:
            await ctx.intent_parser.pre_warm()
        log_success("[Phase 3] Intent classifier ready (CPU).")
    except Exception as e:
        log_error(f"[Phase 3] Intent classifier warm failed: {e}")

    # 3d. RAG knowledge base refresh — scans for new/changed files and embeds them.
    #     Delayed until after intent warm to avoid three models loading simultaneously.
    await asyncio.sleep(5)
    try:
        log_action("[Phase 3] Running background RAG knowledge base refresh …")
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
        from utils.infrastructure.gpu.clear_gpu_memory import kill_orphaned_runners
        kill_orphaned_runners()
        dm.run_curses_mode(initialize_logic_layer_async, run_bot_wrapper)
    else:
        asyncio.run(dm.run_simple_mode(initialize_logic_layer_async, run_bot_wrapper))


if __name__ == "__main__":
    main()
