import os
import sys
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
ctx.ollama_client = ollama.AsyncClient()
ctx.stats_tracker = stats_tracker
ctx.rate_limiter = RateLimiter(config.requests_per_minute)
ctx.shutdown_manager = shutdown_manager
ctx.news_manager = NewsManager()

# Populating late-bound functions
ctx.news_enhancer = NewsRetrievalEnhancer()
ctx.rag_enhancer = RAGEnhancer()

# Initialize Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
ctx.bot = bot

def initialize_logic_layer():
    """Initializes RAG and intelligence components."""
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
    
    # Load state from last run
    ctx.persistent_state_manager.load_state(ctx.personalization_engine, ctx.performance_monitor)
    
    ctx.message_processor = MessageProcessor(
        ctx=ctx,
        response_optimizer=response_optimizer,
        context_optimizer=context_optimizer,
        relevance_feedback=relevance_feedback,
        news_enhancer=ctx.news_enhancer,
        rag_enhancer=ctx.rag_enhancer
    )
    
    # Register GPU memory clearing if available
    try:
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        ctx.clear_gpu_memory = lambda: OllamaGPUManager(config.chat_model).clear_vram()
    except:
        pass
    
    ctx.set_ready()

# RAG Executor Helper
rag_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='rag_worker')

async def run_rag(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

async def prewarm_main_model():
    try:
        if ctx.model_warm_pool:
            await ctx.model_warm_pool.pre_warm(config.chat_model)
        else:
            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_manager = OllamaGPUManager(config.chat_model)
            log_action(f"Pre-warming {config.chat_model} with {config.max_context_tokens // 1000}k context...")
            await gpu_manager.load_only(ctx.ollama_client)
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
    
    # Ensure shutdown manager is registered for global access if needed
    ctx.shutdown_manager = shutdown_manager

    dm = DashboardManager(
        ctx=ctx, bot=bot, config=config, bot_state=bot_state, stats_tracker=stats_tracker, 
        stats_poller=stats_poller, logger=logger, model_warm_pool=None, intent_parser=None
    )
    
    # Pass necessary functions to the manager
    async def run_bot_wrapper(sp, stop_event=None):
        dm.intent_parser = ctx.intent_parser
        await dm.run_bot_async(sp, initialize_logic_layer, dm_sequenced_boot, stop_event)

    async def dm_sequenced_boot():
        import utils.core.background_tasks as bg_tasks
        bg_tasks.ctx = ctx # Initialize context for background tasks early
        
        from utils.social.social_tasks import start_social_tasks
        
        await dm.sequenced_boot_tasks(
            run_rag, ctx.rag, run_news_update, prewarm_main_model
        )
        
        # Start loops with shared context
        bg_tasks.start_background_core_tasks(ctx)
        start_social_tasks(ctx, on_message)

    mode = os.environ.get('KAIA_DASHBOARD', 'curses').lower()
    if mode == 'curses':
        dm.run_curses_mode(initialize_logic_layer, run_bot_wrapper)
    else:
        asyncio.run(dm.run_simple_mode(run_bot_wrapper))

if __name__ == "__main__":
    main()