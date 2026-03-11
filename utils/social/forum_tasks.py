"""
Forum background tasks — periodic scraping of the Off Topic forum.
"""

import asyncio
from pathlib import Path
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import log_error, log_action, log_info
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.shutdown_fixed import shutdown_manager


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
            if shutdown_manager.shutting_down:
                break
                
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
                
                # Check if we should reply
                last_post = posts[-1]
                poster = last_post.get('author', '')
                post_text = last_post.get('content', '')
                
                # Skip if Kaia posted last, or if auto_reply is disabled
                if not config.get('forum.auto_reply', False):
                    continue
                if poster.lower() in ('kaia', bot_state.get('forum_username', 'kaia').lower()):
                    continue
                
                # Check if post mentions Kaia or is a question
                is_question = '?' in post_text
                mentions_kaia = 'kaia' in post_text.lower()
                if not (is_question or mentions_kaia):
                    continue
                
                # Rate limit: check min_hours_between_posts
                min_hours = config.get('forum.min_hours_between_posts', 4)
                last_reply_time = bot_state.forum_reply_times.get(str(thread_id), 0)
                import time
                if time.time() - last_reply_time < min_hours * 3600:
                    continue
                
                # Generate and post reply
                from utils.infrastructure.system.external_mention import process_external_mention
                log_action(f"Triggering forum auto-reply for thread {thread_id} to user {poster}")
                response = await process_external_mention(
                    ctx=bot_state.ctx, # Assuming bot_state has ctx or we need another way to get it
                    content=post_text, author_name=poster,
                    author_id=poster, platform="forum"
                )
                if response:
                    success = await client.post_reply(thread_id, response)
                    if success:
                        bot_state.forum_reply_times[str(thread_id)] = time.time()
                        bot_state.save()

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

    if not config.get('forum.auto_scrape', False):
        log_info("Auto forum scraping is disabled in config — skipping periodic task")
        return

    task = forum_scrape_task.start()
    task_registry.register("forum_scrape_task", task)
    log_action("Forum background scrape task started.")


def stop_forum_tasks():
    """Stop the forum background tasks."""
    if forum_scrape_task.is_running():
        forum_scrape_task.stop()
