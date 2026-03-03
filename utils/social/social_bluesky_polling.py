"""
Bluesky Platform Polling — Mention Fetching, History & Replies
================================================================

Extracted from kaia_social_responder.py (Phase 28 / CQ-01).

Contains:
- _reconstruct_bluesky_history: Rebuild thread counts from bot's recent posts
- _get_bluesky_mentions: Fetch unread mentions with thread limit enforcement
- _reply_to_bluesky: Post a reply to a Bluesky mention
"""

import os
import asyncio
from typing import List, Dict, Any

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_success, log_warning, log_error, log_debug
)
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from utils.infrastructure.system.yaml_config import config
from utils.social.social_tracker import social_tracker
from utils.infrastructure.circuit_breaker import CircuitBreaker

# ── Module-owned state (moved from kaia_social_responder.py) ─────────────
_bluesky_breaker = CircuitBreaker("bluesky")
MAX_THREAD_REPLIES = 5


async def _reconstruct_bluesky_history(_silenced_replied_ids: set):
    """Fetch recent bot posts from Bluesky and rebuild thread counts efficiently."""
    try:
        from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured
        from atproto import models

        if not is_bluesky_configured() or shutdown_manager.shutting_down:
            return

        client = await get_bluesky_client()
        if not client:
            return

        # Reset counts for fresh reconstruction
        handle = os.getenv("BLUESKY_HANDLE")
        response = await client.app.bsky.feed.get_author_feed(
            params=models.AppBskyFeedGetAuthorFeed.Params(actor=handle, limit=50)
        )

        # Phase 1: Collect parent URIs
        reply_map = {}  # {bot_post_uri: (root_uri, parent_uri)}
        for i, item in enumerate(response.feed):
            post = item.post
            reply = getattr(post.record, 'reply', None)
            if reply:
                reply_map[post.uri] = (reply.root.uri, reply.parent.uri)

            # Yield occasionally
            if i % 10 == 0:
                await asyncio.sleep(0)

        if not reply_map:
            return

        # Phase 2: Batch fetch parent posts to get authors
        parent_uris = list(set(p for r, p in reply_map.values()))
        author_map = {}  # {post_uri: author_handle}

        # Batch by 25 (get_posts limit is usually 25-50)
        for i in range(0, len(parent_uris), 25):
            if shutdown_manager.shutting_down:
                break

            batch = parent_uris[i : i + 25]
            try:
                posts_response = await client.app.bsky.feed.get_posts(
                    params=models.AppBskyFeedGetPosts.Params(uris=batch)
                )
                for p in posts_response.posts:
                    author_map[p.uri] = p.author.handle

                # Yield to let other tasks (like Discord heartbeats) run
                await asyncio.sleep(0)
            except Exception as e:
                log_warning(f"Failed to fetch batch of parent posts: {e}")

        # Phase 3: Update state
        count = 0
        for i, (bot_post_uri, (root_uri, parent_uri)) in enumerate(reply_map.items()):
            # Track replies per user in this thread
            replied_to_author = author_map.get(parent_uri)
            if replied_to_author:
                await social_tracker.mark_replied(f"bsky:{parent_uri}", "bluesky", root_uri, replied_to_author)

            # Always mark the parent as replied if we found our own reply to it
            _silenced_replied_ids.add(f"bsky:{parent_uri}")
            count += 1

            # Yield occasionally
            if i % 10 == 0:
                await asyncio.sleep(0)

        if count > 0:
            log_info(f"Reconstructed thread counts and replied IDs for {count} Bluesky replies.")
    except Exception as e:
        log_warning(f"Failed to reconstruct Bluesky history: {e}")


async def _get_bluesky_mentions(_silenced_replied_ids: set, _save_replied_ids_async) -> List[Dict[str, Any]]:
    """Fetch unread mentions from Bluesky."""
    if shutdown_manager.shutting_down:
        return []

    mentions = []

    # Circuit breaker check
    if not _bluesky_breaker.can_proceed():
        log_debug("Bluesky circuit breaker open - skipping fetch")
        return []

    async def run_fetch(force_new=False):
        from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured

        if shutdown_manager.shutting_down:
            return []

        if not is_bluesky_configured():
            return []

        client = await get_bluesky_client(force_new=force_new)
        if not client or shutdown_manager.shutting_down:
            return []

        # Get notifications with limit
        from atproto import models
        notifs = await client.app.bsky.notification.list_notifications(
            params=models.AppBskyNotificationListNotifications.Params(limit=100)
        )

        from datetime import datetime, timezone, timedelta
        lookback_hours = config.get('social.mention_lookback_hours', 3)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        local_mentions = []
        for notif in notifs.notifications:
            if shutdown_manager.shutting_down:
                break

            # Filter for mentions/replies
            if notif.reason in ['mention', 'reply']:
                mention_id = f"bsky:{notif.uri}"

                # Timestamp check: notifications have indexedAt
                try:
                    indexed_at = datetime.fromisoformat(notif.indexed_at.replace('Z', '+00:00'))
                    if indexed_at < cutoff_time:
                        continue
                except Exception as e:
                    log_warning(f"Failed to parse Bluesky notification timestamp: {e}")

                if social_tracker.is_replied(mention_id):
                    if mention_id not in _silenced_replied_ids:
                        log_debug(f"Skipping already-replied mention: {mention_id}")
                        _silenced_replied_ids.add(mention_id)
                    continue

                # Thread tracking: root_uri is the anchor for the thread
                root = getattr(getattr(notif.record, 'reply', None), 'root', None)
                root_uri = root.uri if root and hasattr(root, 'uri') else notif.uri

                user_handle = notif.author.handle
                thread_count = social_tracker.get_thread_count(root_uri, user_handle)

                # Admin check (must be defined here, not just in check_and_reply_mentions)
                admin_handles = config.get('social.admin_handles', [])
                is_admin = user_handle in admin_handles

                log_debug(f"Checking mention {mention_id} from @{user_handle} in thread {root_uri[:30]}. Current count: {thread_count}")

                if not is_admin and thread_count >= MAX_THREAD_REPLIES:
                    log_warning(f"Thread limit reached for @{user_handle} in Bluesky thread: {root_uri[:40]}... Polling will skip until manual reset or limit increase.")

                    # FIX: Add to tracker so we don't spam the logs every poll cycle
                    await social_tracker.mark_replied(mention_id, "bluesky", root_uri, user_handle)
                    _silenced_replied_ids.add(mention_id)
                    await _save_replied_ids_async()

                    continue

                # Fetch parent/root text for context if it's a reply
                parent_text = None
                root_text = None

                reply_ref = getattr(notif.record, 'reply', None)
                parent_uri_obj = getattr(reply_ref, 'parent', None) if reply_ref else None
                root_uri_obj = getattr(reply_ref, 'root', None) if reply_ref else None

                if parent_uri_obj and hasattr(parent_uri_obj, 'uri'):
                    from utils.social.kaia_bluesky import get_post_text
                    parent_text = await get_post_text(parent_uri_obj.uri)

                    # If root is different from parent, fetch root too
                    if root_uri_obj and hasattr(root_uri_obj, 'uri') and root_uri_obj.uri != parent_uri_obj.uri:
                        root_text = await get_post_text(root_uri_obj.uri)
                    else:
                        root_text = parent_text

                local_mentions.append({
                    'id': mention_id,
                    'uri': notif.uri,
                    'cid': notif.cid,
                    'author': notif.author.handle,
                    'text': getattr(notif.record, 'text', ''),
                    'root_uri': root,
                    'parent_uri': parent_uri_obj,
                    'parent_text': parent_text,
                    'root_text': root_text
                })
        return local_mentions

    try:
        mentions = await run_fetch()
        _bluesky_breaker.record_success()
    except Exception as e:
        # Check for specific error types
        error_str = str(e).lower()
        error_type = type(e).__name__

        if "unauthorized" in error_str or "expired" in error_str or "token" in error_str:
            log_warning(f"Bluesky session potentially expired, retrying with new client: {e}")
            try:
                mentions = await run_fetch(force_new=True)
                _bluesky_breaker.record_success()
            except Exception as e2:
                log_error(f"Failed to fetch Bluesky mentions after retry ({type(e2).__name__}): {e2}")
                _bluesky_breaker.record_failure()
        elif "timeout" in error_str or "invoketimeouterror" in error_type.lower():
            # Retry once for timeouts without forcing new client
            log_warning(f"Bluesky fetch timed out, retrying once...")
            try:
                mentions = await run_fetch(force_new=False)
                _bluesky_breaker.record_success()
                log_success("Bluesky fetch succeeded on retry.")
            except Exception as e2:
                log_warning(f"Bluesky fetch timed out again (transient network issue).")
                _bluesky_breaker.record_failure()
        else:
            log_error(f"Failed to fetch Bluesky mentions ({error_type}): {e}")
            import traceback
            log_debug(f"Fetch failure traceback:\n{traceback.format_exc()}")
            _bluesky_breaker.record_failure()

    return mentions


async def _reply_to_bluesky(mention: Dict[str, Any], response_text: str) -> bool:
    """Reply to a Bluesky mention."""
    try:
        from utils.social.kaia_bluesky import get_bluesky_client
        from atproto import models

        client = await get_bluesky_client()
        if not client:
            return False

        # Build reply reference using StrongRef directly
        # The parent is what we're replying to, root is the thread root
        parent_ref = models.ComAtprotoRepoStrongRef.Main(
            uri=mention['uri'],
            cid=mention.get('cid', '')
        )

        # For root, use the thread root if available, otherwise the parent
        root_uri = mention.get('root_uri')
        if root_uri and hasattr(root_uri, 'uri'):
            root_ref = models.ComAtprotoRepoStrongRef.Main(
                uri=root_uri.uri,
                cid=getattr(root_uri, 'cid', '')
            )
        else:
            root_ref = parent_ref

        reply_ref = models.AppBskyFeedPost.ReplyRef(
            root=root_ref,
            parent=parent_ref
        )

        await client.send_post(response_text, reply_to=reply_ref)
        return True

    except RuntimeError as e:
        if "shutdown" in str(e).lower():
            return False
        log_error(f"Social responder runtime error: {e}")
        return False
    except Exception as e:
        log_error(f"Failed to reply on Bluesky: {e}")
        return False
