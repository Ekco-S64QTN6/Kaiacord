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
from utils.news.kaia_news import NewsRetrievalEnhancer, NewsManager, RAGEnhancer, ResponseEnhancer
from utils.core.background_tasks import run_news_update

# Global components
rag = None
dream_engine = None
performance_monitor = None
model_warm_pool = None
intent_parser = None
response_optimizer = None
context_optimizer = None
relevance_feedback = None
personalization_engine = None
message_processor = None
news_manager = NewsManager()
news_enhancer = NewsRetrievalEnhancer()
rag_enhancer = RAGEnhancer()
ollama_client = ollama.AsyncClient()
rate_limiter = RateLimiter(config.requests_per_minute)

# Initialize Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def initialize_logic_layer():
    """Initializes RAG and intelligence components."""
    global rag, dream_engine, performance_monitor, model_warm_pool
    global intent_parser, response_optimizer, context_optimizer, relevance_feedback
    global personalization_engine, message_processor
    
    if rag is not None:
        return
        
    performance_monitor = PerformanceMonitor()
    model_warm_pool = ModelWarmPool(ollama_client)
    
    intent_parser = IntentParser(ollama_client, model=config.chat_model, timeout=config.classification_timeout)
    # ... (rest of the initializations) ...
    response_optimizer = ResponseOptimizer()
    context_optimizer = ContextOptimizer(model_name=config.chat_model, max_tokens=config.max_context_tokens or 24000)
    
    rag = KaiaRAG()
    dream_engine = DreamEngine(config, rag)
    relevance_feedback = RelevanceFeedback(rag)
    
    from utils.core.kaia_intelligence import PersonalizationEngine
    personalization_engine = PersonalizationEngine()
    
    message_processor = MessageProcessor(
        bot=bot, ollama_client=ollama_client, run_rag=run_rag, rag=rag, 
        config=config, bot_state=bot_state, performance_monitor=performance_monitor, 
        intent_parser=intent_parser, 
        response_optimizer=response_optimizer, context_optimizer=context_optimizer, 
        relevance_feedback=relevance_feedback, personalization_engine=personalization_engine, 
        stats_tracker=stats_tracker, rate_limiter=rate_limiter, shutdown_manager=shutdown_manager, 
        news_enhancer=news_enhancer, rag_enhancer=rag_enhancer,
        news_manager=news_manager, dream_engine=dream_engine
    )

# RAG Executor Helper
rag_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix='rag_worker')

async def run_rag(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(rag_executor, lambda: fn(*args, **kwargs))

async def prewarm_main_model():
    from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
    try:
        gpu_manager = OllamaGPUManager(config.chat_model)
        log_action(f"Pre-warming {config.chat_model} with {config.max_context_tokens // 1000}k context...")
        await gpu_manager.load_only(ollama_client)
    except Exception as e:
        print(f"⚠️ Pre-warm failed: {e}")

@bot.event
async def on_ready():
    from utils.infrastructure.system.file_watcher import start_watcher
    from utils.infrastructure.system.maintenance_tasks import start_maintenance_tasks
    
    global rag, personalization_engine, performance_monitor
    
    # Wait up to 30s for logic layer to initialize if needed
    for _ in range(30):
        if rag is not None:
            break
        await asyncio.sleep(1)
        
    if rag is None:
        log_error("CRITICAL: Bot ready but RAG layer not initialized!")
        return

    start_watcher(rag, asyncio.get_running_loop(), task_registry=task_registry)
    start_maintenance_tasks(rag, personalization_engine, performance_monitor, None, rate_limiter, None)

@bot.event
@timed_response(threshold=30.0)
async def on_message(msg: discord.Message):
    global message_processor
    if message_processor:
        await message_processor.process(msg)
    else:
        log_warning("Message received but processor not yet initialized. Skipping.")

async def process_external_mention(content: str, author_name: str, author_id: Any, platform: str):
    from utils.social.kaia_social_responder import mock_external_mention
    return await mock_external_mention(on_message, content, author_name, author_id, platform)

def main():
    # Initialize DashboardManager
    from utils.infrastructure.monitoring.stats_tracker import stats_tracker
    from utils.infrastructure.monitoring.stats_poller import stats_poller
    
    dm = DashboardManager(
        bot=bot, config=config, bot_state=bot_state, stats_tracker=stats_tracker, 
        stats_poller=stats_poller, logger=logger, model_warm_pool=None, intent_parser=None
    )
    
    # Pass necessary functions to the manager
    async def run_bot_wrapper(sp, stop_event=None):
        dm.intent_parser = intent_parser
        await dm.run_bot_async(sp, initialize_logic_layer, dm_sequenced_boot, stop_event)

    async def dm_sequenced_boot():
        await dm.sequenced_boot_tasks(
            run_rag, rag, run_news_update, prewarm_main_model, load_persona_async, 
            on_message, news_manager, dream_engine, ollama_client
        )

    mode = os.environ.get('KAIA_DASHBOARD', 'curses').lower()
    if mode == 'curses':
        dm.run_curses_mode(initialize_logic_layer, run_bot_wrapper)
    else:
        asyncio.run(dm.run_simple_mode(run_bot_wrapper))

if __name__ == "__main__":
    main()