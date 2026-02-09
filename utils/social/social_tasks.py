import asyncio
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_error, log_action
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config

# Dependencies will be injected via start_social_tasks
_bot = None
_ollama_client = None
_run_rag = None
_rag = None
_on_message = None

@tasks.loop(minutes=5)
async def idle_quip_task():
    """Generate a random quip if idle for too long"""
    if not _bot or not _ollama_client or not _run_rag or not _rag or not _on_message:
        return
        
    try:
        from utils.social.kaia_social_responder import generate_quip
        await generate_quip(_bot, _ollama_client, _run_rag, _rag, on_message_func=_on_message)
    except Exception as e:
        log_error(f"Idle quip task failed: {e}")

@tasks.loop(minutes=config.get('social.poll_interval_minutes', 3))
async def social_mention_task():
    """Check and reply to social media mentions on Bluesky and X."""
    if not bot_state.boot_complete:
        return
    
    if not _on_message:
        return

    try:
        from utils.social.kaia_social_responder import check_and_reply_mentions
        await check_and_reply_mentions(_on_message)
    except Exception as e:
        log_error(f"Social mention task failed: {e}")

def start_social_tasks(bot, ollama_client, run_rag, rag, on_message):
    global _bot, _ollama_client, _run_rag, _rag, _on_message
    _bot = bot
    _ollama_client = ollama_client
    _run_rag = run_rag
    _rag = rag
    _on_message = on_message
    
    import time
    # Prevent bootup "catch-up" spam by resetting the timer to now.
    bot_state.last_quip_time = time.time()
    bot_state.save()
    
    idle_quip_task.start()
    social_mention_task.start()
    log_action("Social background tasks started.")

def stop_social_tasks():
    idle_quip_task.stop()
    social_mention_task.stop()
