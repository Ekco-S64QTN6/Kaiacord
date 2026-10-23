"""
X/Twitter Platform Polling — Mention Fetching, History & Replies
==================================================================

Extracted from kaia_social_responder.py (Phase 28 / CQ-01).

Contains:
- _reconstruct_x_history: Rebuild thread counts from bot's recent tweets
- _get_x_mentions: Fetch unread mentions with auth retry
- _reply_to_x: Post a reply to an X mention with auth retry
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
_x_breaker = CircuitBreaker("x")
X_AUTH_ESCALATION_FAILURES = 2


async def _record_x_failure(error: BaseException) -> None:
    """Record a failed poll and tear down persistent half-open auth failures."""
    _x_breaker.record_failure()
    from utils.social.kaia_twitter import (
        invalidate_x_session, is_x_auth_or_challenge_error,
    )
    if (_x_breaker.half_open_failures >= X_AUTH_ESCALATION_FAILURES
            and is_x_auth_or_challenge_error(error)):
        log_error(
            "[X AUTH ESCALATION] Repeated authentication/challenge failures "
            f"across {_x_breaker.half_open_failures} half-open probes; clearing "
            "the cached session and saved cookies before the next recovery probe."
        )
        await invalidate_x_session("repeated half-open authentication/challenge failures")


async def _reconstruct_x_history(_silenced_replied_ids: set):
    """Fetch recent bot posts from X and rebuild thread counts with retry."""

    async def run_reconstruct(force_new=False):
        if not config.x_enabled or shutdown_manager.shutting_down:
            return 0

        from utils.social.kaia_twitter import get_x_client
        client = await get_x_client(force_new=force_new)
        if not client:
            return 0

        username = os.getenv("X_USERNAME")
        if not username:
            return 0

        # Get user ID first
        user_id = await client.user_id()
        # Fetch last 40 tweets (Tweets + Replies)
        response = await client.get_user_tweets(user_id, 'Replies', count=40)

        if not response:
            return 0

        current_count = 0
        for tweet in response:
            if shutdown_manager.shutting_down:
                break

            in_reply_to = getattr(tweet, 'in_reply_to', None)
            if in_reply_to:
                mention_id = f"x:{in_reply_to}"
                _silenced_replied_ids.add(mention_id)
                root_id = in_reply_to
                try:
                    root_id = tweet._legacy.get('conversation_id_str', in_reply_to)
                except Exception:
                    pass
                await social_tracker.mark_replied(mention_id, "x", root_id, "__reconstructed__")

            # Yield every few tweets to prevent hogging the loop
            current_count += 1
            if current_count % 10 == 0:
                await asyncio.sleep(0)
        return current_count

    try:
        count = await run_reconstruct()
        if count > 0:
            log_info(f"Reconstructed thread state for {count} X replies.")
    except Exception as e:
        from utils.social.kaia_twitter import is_x_auth_or_challenge_error
        if is_x_auth_or_challenge_error(e):
            log_warning(f"X history reconstruction hit an auth/challenge error, retrying: {e}")
            try:
                count = await run_reconstruct(force_new=True)
                if count > 0:
                    log_info(f"Reconstructed thread state for {count} X replies after re-auth.")
            except Exception as e2:
                log_error(f"Failed X history reconstruction after re-auth: {e2}")
        else:
            log_warning(f"Failed to reconstruct X history: {e}")


async def _get_x_mentions(_silenced_replied_ids: set) -> List[Dict[str, Any]]:
    """Fetch unread mentions from X."""
    if shutdown_manager.shutting_down:
        return []

    mentions = []

    # Circuit breaker check
    if not _x_breaker.can_proceed():
        log_debug("X circuit breaker open - skipping fetch")
        return []

    async def run_fetch(force_new=False):
        from utils.social.kaia_twitter import get_x_client, is_x_configured
        if not is_x_configured():
            raise RuntimeError("X mention polling is enabled but X credentials are not configured")

        client = await get_x_client(force_new=force_new)
        if not client:
            # Treat failed login/session construction as unavailable, not an
            # empty successful poll; otherwise the breaker is reset forever.
            raise RuntimeError("X client unavailable after login/cookie recovery")

        # Get mentions notifications
        notifs = await client.get_notifications('Mentions')

        from datetime import datetime, timezone, timedelta
        lookback_hours = config.get('social.mention_lookback_hours', 3)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        local_mentions = []
        for notif in notifs:
            tweet = notif.tweet if hasattr(notif, 'tweet') else notif
            if not tweet:
                continue

            # Timestamp check
            try:
                created_at = tweet.created_at_datetime
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff_time:
                    continue
            except Exception as e:
                log_warning(f"Failed to check X mention timestamp: {e}")

            mention_id = f"x:{tweet.id}"
            user_handle = tweet.user.screen_name if hasattr(tweet, 'user') else 'unknown'

            # Thread tracking: root_id (conversation_id) is the anchor
            root_id = tweet._legacy.get('conversation_id_str', tweet.id)
            parent_id = tweet.in_reply_to

            if social_tracker.is_replied(mention_id):
                if mention_id not in _silenced_replied_ids:
                    log_debug(f"Skipping already-replied mention: {mention_id}")
                    _silenced_replied_ids.add(mention_id)
                continue

            local_mentions.append({
                'id': mention_id,
                'tweet_id': tweet.id,
                'author': user_handle,
                'text': tweet.text,
                'root_id': root_id,
                'parent_id': parent_id
            })
        return local_mentions

    try:
        mentions = await run_fetch()
        _x_breaker.record_success()
    except Exception as e:
        error_type = type(e).__name__

        # Twikit may surface the Cloudflare/403 challenge as text rather than
        # a structured 401. Reuse the same classifier as direct posting/login.
        from utils.social.kaia_twitter import is_x_auth_or_challenge_error
        if is_x_auth_or_challenge_error(e):
            log_warning(f"X session/challenge error, retrying with new client: {e}")
            try:
                mentions = await run_fetch(force_new=True)
                _x_breaker.record_success()
                log_success("X fetch succeeded after re-authentication.")
            except Exception as e2:
                log_error(f"Failed to fetch X mentions after re-auth retry ({type(e2).__name__}): {e2}")
                await _record_x_failure(e2)
        else:
            log_error(f"Failed to fetch X mentions ({error_type}): {e}")
            await _record_x_failure(e)

    return mentions


async def _reply_to_x(mention: Dict[str, Any], response_text: str) -> bool:
    """Reply to an X mention with automatic retry on auth failure."""
    async def run_reply(force_new=False):
        from utils.social.kaia_twitter import get_x_client
        client = await get_x_client(force_new=force_new)
        if not client:
            return False

        await client.create_tweet(
            response_text,
            reply_to=mention['tweet_id']
        )
        return True

    try:
        return await run_reply()
    except Exception as e:
        from utils.social.kaia_twitter import is_x_auth_or_challenge_error
        if is_x_auth_or_challenge_error(e):
            log_warning(f"X reply auth/challenge failed, retrying with fresh session: {e}")
            try:
                return await run_reply(force_new=True)
            except Exception as e2:
                log_error(f"Failed to reply on X after re-auth: {e2}")
        else:
            log_error(f"Failed to reply on X: {e}")
        return False
