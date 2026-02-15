import asyncio
import time
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_error, log_action
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config

# Dependencies managed via AppContext
ctx = None
_on_message = None

@tasks.loop(minutes=5)
async def idle_quip_task():
    """Generate a random quip if idle for too long"""
    if not ctx or not _on_message:
        return
        
    try:
        from utils.social.kaia_social_responder import generate_quip
        await generate_quip(ctx, on_message_func=_on_message)
    except Exception as e:
        log_error(f"Idle quip task failed: {e}")

@tasks.loop(minutes=config.get('social.poll_interval_minutes', 3))
async def social_mention_task():
    """Check and reply to social media mentions on Bluesky and X."""
    if not bot_state.boot_complete:
        return
        
    # User Request: Reduce grace period to allow faster catch-up
    grace_period = 60 # 1 minute (was 3 minutes)
    time_since_boot = time.time() - getattr(bot_state, 'boot_complete_time', 0)
    if time_since_boot < grace_period:
        remaining = int(grace_period - time_since_boot)
        log_action(f"Social tasks: In startup grace period. {remaining}s remaining.")
        return
    
    if not _on_message:
        return

    try:
        from utils.social.kaia_social_responder import check_and_reply_mentions
        await check_and_reply_mentions(_on_message)
    except Exception as e:
        log_error(f"Social mention task failed: {e}")

def start_social_tasks(app_ctx, on_message):
    global ctx, _on_message
    ctx = app_ctx
    _on_message = on_message
    
    # Prevent bootup "catch-up" spam by resetting the timer to now.
    bot_state.last_quip_time = time.time()
    bot_state.save()
    
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    
    quip_task = idle_quip_task.start()
    task_registry.register("idle_quip_task", quip_task)
    
    mention_task = social_mention_task.start()
    task_registry.register("social_mention_task", mention_task)
    
    # Start forum background tasks
    from utils.social.forum_tasks import start_forum_tasks
    start_forum_tasks()
    
    log_action("Social background tasks started.")

def stop_social_tasks():
    idle_quip_task.stop()
    social_mention_task.stop()
    
    from utils.social.forum_tasks import stop_forum_tasks
    stop_forum_tasks()

