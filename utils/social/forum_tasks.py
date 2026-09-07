"""
Forum background tasks — periodic scraping of the Off Topic forum.
"""

import asyncio
import os
import time
from pathlib import Path
from discord.ext import tasks
from utils.infrastructure.logging.kaia_logger import (
    log_error, log_action, log_info, log_debug, log_success, log_warning,
)
from utils.social.forum_participation import PostLedger, PostingWindow
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.shutdown_fixed import shutdown_manager

# Set by start_forum_tasks. The reply watcher needs the message pipeline, and
# an earlier version read it off `bot_state.ctx` — an attribute BotState has
# never defined, so the watcher took its "no bot context available yet" early
# return on every single pass and could not have replied to anyone.
ctx = None


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

        # ── Answering people who answered her ────────────────────────
        # Not gated on `forum.allowed_threads`, a list a human had to maintain
        # by hand — which meant someone could reply to her and get nothing
        # back. The ledger already knows every thread she has spoken in, and
        # that is the natural watch list.
        await _reply_to_replies(client, forum_username=os.getenv("VBULLETIN_USERNAME", ""))

        # Trigger RAG reindex ONLY if content changed
        if any_updated:
            Path("./knowledge_base/.trigger_reindex").touch()
            log_action(f"Forum scrape: {len(threads)} threads, {len(all_posts)} posts ingested (Updates found)")
        else:
            log_info(f"Forum scrape: {len(threads)} threads checked. No new content.")

    except Exception as e:
        log_error(f"Forum scrape task failed: {e}")


async def _queue_for_review(ctx, client, thread_id: int, title: str, text: str,
                            *, kind: str, last_seen_post_id=None,
                            replying_to: str = "") -> bool:
    """Send a draft to #kaia-opolis with accept/reject buttons."""
    try:
        import discord
        from utils.social.kaia_forum import ForumDraftReviewView

        channel = discord.utils.get(ctx.bot.get_all_channels(), name="kaia-opolis")
        if not channel:
            log_warning("Discord channel 'kaia-opolis' not found; dropping forum draft.")
            return False

        link = f"https://www.project1999.com/forums/showthread.php?t={thread_id}"
        header = (f"💬 **[P99 Forum Reply Draft]** — {replying_to} replied to her"
                  if replying_to else "📰 **[P99 Forum Draft]**")
        view = ForumDraftReviewView(client, thread_id, title, text,
                                    forum_type="off_topic", kind=kind,
                                    last_seen_post_id=last_seen_post_id)
        await channel.send(
            f"{header}\n**Thread:** [{title}]({link})\n\n"
            f"**Kaia's Draft:**\n```\n{text}\n```", view=view)
        try:
            from utils.infrastructure.monitoring.stats_tracker import stats_tracker
            stats_tracker.increment_forum_drafts()
        except Exception:
            pass
        return True
    except Exception as e:
        log_error(f"Failed to queue forum draft for review: {e}")
        return False


async def _reply_to_replies(client, forum_username: str) -> None:
    """Check the threads Kaia has posted in and answer anyone who replied.

    Replying to someone who spoke to you is conversation, not interjection, so
    it is deliberately *not* subject to the daily cap, the spacing rule, the
    72-hour thread cooldown, or the after-midnight window. She is not capped in
    Discord either, and going quiet for three days after someone answers you is
    not restraint — it is rude.

    The one guard that stays is the narrow one: a short interval, and something
    new must actually have been said. Unbounded reply-on-reply is the single
    remaining path to the behaviour the caps exist to prevent, and it matters
    most in the case that would be hardest to notice — two bots talking.
    """
    from utils.infrastructure.system.bot_state import bot_state
    from utils.social.forum_participation import PostLedger, REPLY
    from utils.social.forum_drafting import draft_forum_reply

    ledger = PostLedger()
    watch = ledger.threads_posted_in(
        within_hours=float(config.get('forum.reply_watch_days', 14)) * 24)
    if not watch:
        return

    min_minutes = float(config.get('forum.min_minutes_between_replies', 20))
    if ctx is None or getattr(ctx, "message_processor", None) is None:
        log_info("Forum reply watch: pipeline not ready yet.")
        return

    for thread_id in watch:
        if shutdown_manager.shutting_down:
            break
        try:
            thread_data = await client.scrape_thread(thread_id, last_n_posts=10)
            posts = thread_data.get('posts', [])
            if not posts:
                continue

            last = posts[-1] if isinstance(posts[-1], dict) else posts[-1].to_dict()
            poster = (last.get('author') or '')
            if poster.lower() == (forum_username or '').lower():
                continue          # she spoke last; nothing to answer

            newest_id = last.get('post_id')
            may, why = ledger.may_reply(thread_id, newest_id,
                                        min_minutes_between=min_minutes)
            if not may:
                log_debug(f"Forum reply watch: skipping thread {thread_id} — {why}.")
                continue

            log_action(f"Forum: {poster} replied in thread {thread_id}; drafting an answer.")
            draft = await draft_forum_reply(
                ctx, thread_id=thread_id,
                title=thread_data.get('title', f'Thread {thread_id}'),
                posts=posts, reply_to=last)
            if not draft:
                continue

            text = draft['text']
            if draft['quote']:
                from utils.social.forum_drafting import own_words
                q = draft['quote']
                text = client.format_quote(q.get('author', 'Unknown'),
                                           q.get('post_id'),
                                           own_words(q.get('content', ''))) + text

            title = thread_data.get('title', f'Thread {thread_id}')

            # Everything Kaia writes to this forum goes past a human first,
            # replies included. Lifting the *caps* on conversation is what was
            # asked for; posting unreviewed to a public forum is a separate
            # decision, and `forum.auto_reply` is the switch for it.
            if not config.get('forum.auto_reply', False):
                if await _queue_for_review(ctx, client, thread_id, title, text,
                                           kind=REPLY, last_seen_post_id=newest_id,
                                           replying_to=poster):
                    log_action(f"Forum: reply to {poster} queued for review.")
                continue

            if await client.post_reply(thread_id, text, title=title,
                                       kind=REPLY, last_seen_post_id=newest_id):
                # No bot_state write here: post_reply records to the ledger,
                # which is what may_reply reads. `forum_reply_times` had no
                # readers left and each write serialised the whole BotState.
                log_success(f"Forum: replied to {poster} in thread {thread_id}.")
        except Exception as e:
            log_error(f"Forum reply watch failed on thread {thread_id}: {e}")


def start_forum_tasks(app_ctx=None):
    """Start the forum background tasks."""
    from utils.infrastructure.monitoring.async_task_registry import task_registry
    global ctx
    if app_ctx is not None:
        ctx = app_ctx

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
