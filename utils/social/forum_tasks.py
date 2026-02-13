"""
Forum background tasks — periodic scraping of the Off Topic forum.
"""

import asyncio
from pathlib import Path
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_error, log_action, log_info
from utils.infrastructure.system.yaml_config import config


@tasks.loop(minutes=config.get('forum.scrape_interval_minutes', 30))
async def forum_scrape_task():
    """Periodically scrape the Off Topic forum for new posts."""
    from utils.infrastructure.system.bot_state import bot_state
    if not bot_state.boot_complete:
        return

    from utils.social.kaia_forum import is_forum_configured, get_forum_client

    if not is_forum_configured():
        return

    try:
        client = await get_forum_client()
        if not client:
            return

        # Scrape the listing
        threads = await client.scrape_forum_listing()
        if not threads:
            return

        client.save_forum_listing(threads)

        # Scrape recent posts from top active non-sticky threads
        max_posts = config.get('forum.max_posts_per_thread_scrape', 20)
        all_posts = []
        any_updated = False

        for t in threads[:5]:
            if t.is_sticky:
                continue
            
            # Optimization: Skip network request if reply count hasn't changed
            if not client.is_thread_update_needed(t.thread_id, t.reply_count):
                continue

            thread_data = await client.scrape_thread(t.thread_id, last_n_posts=max_posts)
            if thread_data.get('posts'):
                if client.save_thread_scrape(thread_data):
                    any_updated = True
                all_posts.extend(thread_data['posts'])

        # Update forum user profiles
        if all_posts:
            client.update_forum_user_profiles(all_posts)

        # Deep-scrape unique users found in threads (24h dedup built in)
        await client.scrape_active_users(threads, all_posts)

        # RESPONSE LOGIC: Check unread posts in allowed threads
        allowed_threads = config.get('forum.allowed_threads', [])
        if allowed_threads:
            log_action(f"Checking for new replies in {len(allowed_threads)} allowed threads...")
            for thread_id in allowed_threads:
                # We already have posts from scrape_thread above if it was in the top 5
                # But let's be explicit and fetch the very latest for allowed threads
                thread_data = await client.scrape_thread(thread_id, last_n_posts=10)
                posts = thread_data.get('posts', [])
                if not posts:
                    continue
                
                # Logic to determine if Kaia should reply will go here
                # (e.g., mention detection or just general engagement)
                # For now, we just log that we would check them
                pass

        # Trigger RAG reindex ONLY if content changed
        if any_updated:
            Path("./knowledge_base/.trigger_reindex").touch()
            log_action(f"Forum scrape: {len(threads)} threads, {len(all_posts)} posts ingested (Updates found)")
        else:
            log_info(f"Forum scrape: {len(threads)} threads checked. No new content.")

    except Exception as e:
        log_error(f"Forum scrape task failed: {e}")


def start_forum_tasks():
    """Start the forum background tasks."""
    from utils.infrastructure.monitoring.async_task_registry import task_registry

    if not config.get('forum.enabled', False):
        log_info("Forum integration disabled in config — skipping background tasks")
        return

    task = forum_scrape_task.start()
    task_registry.register("forum_scrape_task", task)
    log_action("Forum background scrape task started.")


def stop_forum_tasks():
    """Stop the forum background tasks."""
    if forum_scrape_task.is_running():
        forum_scrape_task.stop()
