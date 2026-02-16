import os
import sys
import argparse
import asyncio
import uuid
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

# Global application context
ctx = AppContext()
ctx.config = config
ctx.bot_state = bot_state
ctx.ollama_client = ollama.AsyncClient(timeout=config.llm_request_seconds)
ctx.stats_tracker = stats_tracker
ctx.rate_limiter = RateLimiter(config.requests_per_minute)
ctx.shutdown_manager = shutdown_manager
ctx.news_manager = NewsManager()

# Concurrency limit for embedding-heavy RAG operations
embedding_semaphore = asyncio.Semaphore(2)

# Populating late-bound functions
ctx.news_enhancer = NewsRetrievalEnhancer()
ctx.rag_enhancer = RAGEnhancer()

# Initialize Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
ctx.bot = bot

async def initialize_logic_layer_async():
    """Asynchronously initializes RAG and intelligence components."""
    if ctx.rag is not None:
        return
        
    ctx.performance_monitor = PerformanceMonitor()
    ctx.model_warm_pool = ModelWarmPool(ctx.ollama_client)
    
    ctx.intent_parser = IntentParser(ctx.ollama_client, model=config.chat_model, timeout=config.classification_timeout)
    response_optimizer = ResponseOptimizer()
    context_optimizer = ContextOptimizer(model_name=config.chat_model, max_tokens=config.max_context_tokens)
    
    ctx.rag = KaiaRAG()
    shutdown_manager.register_rag(ctx.rag)
    ctx.dream_engine = DreamEngine(config, ctx.rag)
    relevance_feedback = RelevanceFeedback(ctx.rag)
    
    from utils.core.kaia_intelligence import PersonalizationEngine, PersistentStateManager
    ctx.personalization_engine = PersonalizationEngine()
    ctx.persistent_state_manager = PersistentStateManager()
    
    # Load state from last run (Offload to thread)
    await ctx.persistent_state_manager.load_state_async(ctx.personalization_engine, ctx.performance_monitor)
    
    # Initialize RAG indices (Offload to thread internally)
    await ctx.rag.initialize_async()
    
    ctx.message_processor = MessageProcessor(
        ctx=ctx,
        response_optimizer=response_optimizer,
        context_optimizer=context_optimizer,
        relevance_feedback=relevance_feedback,
        news_enhancer=ctx.news_enhancer,
        rag_enhancer=ctx.rag_enhancer
    )
    
    # Register GPU memory clearing (Offloaded to thread)
    try:
        from utils.infrastructure.gpu.clear_gpu_memory import clear_gpu_memory
        ctx.clear_gpu_memory = lambda: asyncio.to_thread(clear_gpu_memory, silent=True)
    except:
        pass
    
    ctx.set_ready()

# RAG Executor Helper
rag_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='rag_worker')

async def run_rag(fn, *args, **kwargs):
    import inspect
    async with embedding_semaphore:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

async def prewarm_main_model():
    try:
        if ctx.model_warm_pool:
            await ctx.model_warm_pool.pre_warm(config.chat_model)
        else:
            log_action(f"Pre-warming {config.chat_model} with {config.max_context_tokens // 1000}k context...")
            await ctx.ollama_client.generate(model=config.chat_model, prompt=".", options={"num_ctx": config.max_context_tokens})
    except Exception as e:
        print(f"⚠️ Pre-warm failed: {e}")

@bot.event
async def on_ready():
    # start_watcher removed
    from utils.infrastructure.system.maintenance_tasks import start_maintenance_tasks
    
    # Wait for logic layer to initialize if needed (event-based, no more polling)
    try:
        await ctx.wait_until_ready(timeout=30.0)
    except asyncio.TimeoutError:
        log_error("CRITICAL: Bot ready but RAG layer initialization timed out (30s)!")
        return

    if ctx.rag:
        ctx.rag._bot_user_id = bot.user.id
        
    start_maintenance_tasks(ctx)
    
    # Start loop watchdog to detect stalls
    try:
        from utils.infrastructure.monitoring.watchdog import watchdog
        watchdog.start(asyncio.get_running_loop())
    except Exception as e:
        log_error(f"Failed to start LoopWatchdog: {e}")

@bot.event
@timed_response(threshold=30.0)
async def on_message(msg: discord.Message):
    if ctx.message_processor:
        await ctx.message_processor.process(msg)
    else:
        log_warning("Message received but processor not yet initialized. Skipping.")

async def process_external_mention(content: str, author_name: str, author_id: Any, platform: str):
    from utils.social.kaia_social_responder import mock_external_mention
    return await mock_external_mention(on_message, content, author_name, author_id, platform)

def main():
    # Initialize DashboardManager
    from utils.infrastructure.monitoring.stats_tracker import stats_tracker
    from utils.infrastructure.monitoring.stats_poller import stats_poller
    
    # Parse Arguments
    parser = argparse.ArgumentParser(description="Kaiacord - The AI Discord Bot")
    parser.add_argument('--no-gui', action='store_true', help="Run without curses dashboard")
    parser.add_argument('--eager-rag-warm', action='store_true', help="Eagerly pre-warm BM25 indices at boot (default: lazy, built on first query)")
    parser.add_argument('--status', action='store_true', help="Check system status and exit")
    args = parser.parse_args()

    if args.status:
        # Simple status check
        print("\n--- Kaia System Status ---")
        import ollama
        try:
            ollama.list()
            print("Ollama: ✅ ONLINE")
        except:
            print("Ollama: 🔴 OFFLINE")
        return

    # Ensure shutdown manager is registered for global access if needed
    ctx.shutdown_manager = shutdown_manager

    dm = DashboardManager(
        ctx=ctx, bot=bot, config=config, bot_state=bot_state, stats_tracker=stats_tracker, 
        stats_poller=stats_poller, logger=logger, model_warm_pool=None, intent_parser=None
    )
    
    # Pass necessary functions to the manager
    async def run_bot_wrapper(sp, stop_event=None):
        dm.intent_parser = ctx.intent_parser
        await dm.run_bot_async(sp, initialize_logic_layer_async, dm_sequenced_boot, stop_event)

    async def dm_sequenced_boot():
        import utils.core.background_tasks as bg_tasks
        bg_tasks.ctx = ctx # Initialize context for background tasks early
        
        from utils.social.social_tasks import start_social_tasks
        
        # Sequenced boot with respect to skip-rag-warm
        log_info("Starting sequenced boot...")
        
        # 1. Primary RAG Refresh (Mandatory for identity)
        await run_rag(ctx.rag.refresh_knowledge_base)
        await asyncio.sleep(2.0) # Settle I/O after refresh
        
        # 2. News Update
        if config.startup_news_update:
            await run_news_update()
            await asyncio.sleep(2.0) # Settle I/O after news pull
            
        # 3. Model Pre-warming (Serialized for I/O safety)
        try:
            if ctx.intent_parser:
                await ctx.intent_parser.pre_warm()
                await asyncio.sleep(1.0)
            await prewarm_main_model()
        except: pass

        # Signal boot complete for message processor IMMEDIATELY after models are warm
        bot_state.boot_complete = True
        log_success("Kaia models are warm and ready.")

        # 4. Heavy RAG Warm (Optional/Bypassable)
        if args.eager_rag_warm:
            log_info("Eager RAG pre-warm requested. Building BM25 indices...")
            await run_rag(ctx.rag.pre_warm)
        else:
            log_info("BM25 indices will be built lazily on first query (use --eager-rag-warm to pre-warm).")
        
        # Start loops with shared context
        bg_tasks.start_background_core_tasks(ctx)
        start_social_tasks(ctx, on_message)
        
        log_success("Kaia is fully online and heartbeating.")

    # Determine Display Mode
    env_mode = os.environ.get('KAIA_DASHBOARD', 'curses').lower()
    if args.no_gui:
        mode = 'simple'
    else:
        mode = env_mode

    if mode == 'curses':
        dm.run_curses_mode(initialize_logic_layer_async, run_bot_wrapper)
    else:
        asyncio.run(dm.run_simple_mode(initialize_logic_layer_async, run_bot_wrapper))

if __name__ == "__main__":
    main()