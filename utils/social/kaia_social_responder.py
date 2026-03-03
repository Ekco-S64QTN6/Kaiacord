"""
Kaia Social Media Responder
============================

Unified module for monitoring and responding to mentions on Bluesky and X.

Polls both platforms for mentions and generates AI responses using Kaia's persona.
"""

import os
import asyncio
import json
import re
import random
import time
import traceback
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error, log_action, log_debug
from utils.core.response_filter import BotSpeakFilter
from contextlib import asynccontextmanager
from utils.infrastructure.system.shutdown_fixed import shutdown_manager
from utils.infrastructure.system.yaml_config import config
from utils.social.social_tracker import social_tracker

# Lazy load these to prevent event loop stalls during module initialization
get_bluesky_client = None
is_bluesky_configured = None
models = None

def _ensure_social_imports():
    """Lazy import social libraries to avoid blocking startup."""
    global get_bluesky_client, is_bluesky_configured, models
    if get_bluesky_client is None:
        try:
            from utils.social.kaia_bluesky import get_bluesky_client as _gbc, is_bluesky_configured as _ibc
            from atproto import models as _m
            get_bluesky_client, is_bluesky_configured, models = _gbc, _ibc, _m
        except ImportError:
            log_warning("Social libraries (atproto) not found. Some social features may be limited.")

def warm_social_libraries():
    """Trigger lazy imports of heavy social libraries."""
    log_info("Warming social libraries (atproto, twikit)...")
    _ensure_social_imports()
    try:
        import utils.social.kaia_twitter as kt
        # Trigger lazy imports in kaia_twitter
        kt.is_x_configured()
    except Exception as e:
        log_warning(f"Failed to warm X library: {e}")
    return bool(models)

# =============================================================================
# CONSTANTS
# =============================================================================
BLUESKY_CHAR_LIMIT = 300
X_CHAR_LIMIT = 280
MAX_THREAD_REPLIES = 5
MAX_NOTIFICATIONS_FETCH = 50
MAX_THREAD_POSTS = 5
MAX_REPLIED_IDS = 5000

# Persona cache
_persona_cache = None
_persona_last_load = 0


# CircuitBreaker lives in the shared infrastructure layer to avoid
# the dependency inversion of core modules importing from social.
from utils.infrastructure.circuit_breaker import CircuitBreaker

# Module-level circuit breaker instances
_bluesky_breaker = CircuitBreaker("bluesky")
_x_breaker = CircuitBreaker("x")


def load_persona() -> str:
    """Load the bot's persona from kaia_persona.md with caching"""
    global _persona_cache, _persona_last_load
    # FIX: Correct path traversal - from utils/social/ up to project root
    # Path: utils/social/kaia_social_responder.py -> utils/social -> utils -> project_root
    project_root = Path(__file__).parent.parent.parent
    persona_file = project_root / 'knowledge_base' / 'kaia_persona.md'
    
    try:
        if not persona_file.exists():
            log_error(f"Persona file NOT FOUND at: {persona_file}")
            
        mtime = persona_file.stat().st_mtime
        if _persona_cache and mtime <= _persona_last_load:
            return _persona_cache
            
        with open(persona_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            _persona_cache = content
            _persona_last_load = mtime
            log_debug(f"Persona loaded successfully from {persona_file} ({len(content)} chars)")
            return _persona_cache
    except Exception as e:
        log_error(f"load_persona() FAILED to read file: {persona_file} — Error: {e}")
        if _persona_cache:
            log_info("Returning persona from memory cache as fallback.")
            return _persona_cache
        return "You are Kaia, a blunt and grounded resident of this server."


async def load_persona_async() -> str:
    """Load the bot's persona from kaia_persona.md with caching (Async)"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_persona)

_silenced_replied_ids: set = set()  # Track which IDs have already been logged as skipped this session
_first_poll_done = False




def _get_root_uri(mention: Dict[str, Any]) -> str:
    """Extract root thread URI from a mention dict."""
    root = mention.get('root_uri')
    return root.uri if root and hasattr(root, 'uri') else mention['uri']


def _get_context_type_for_dream(dream: Dict[str, Any]) -> str:
    """Derive a context framing string from a dream's metadata."""
    source = dream.get('metadata', {}).get('source', '').lower()
    if any(k in source for k in ('book', 'epub', 'pdf')):
        title = source.replace('_', ' ').replace('.md', '').title()
        return f"reading a book called {title}"
    elif 'dream' in source:
        return "recalling a weird fever dream"
    return f"thinking about {dream.get('category', 'something')}"


def _load_replied_ids():
    """Legacy wrapper (No-op as tracker loads on init)."""
    # Pre-silence all loaded IDs so they don't spam logs on first poll
    _silenced_replied_ids.update(social_tracker.get_all_replied_ids())


def _save_replied_ids():
    """Trigger a state snapshot in the social_tracker."""
    # social_tracker.save_snapshot is async, but this is a sync wrapper
    # We use create_task if called from async, or run_until_complete if from sync (not ideal)
    # However, responder calls this via _save_replied_ids_async usually.
    pass

async def _save_replied_ids_async():
    """Trigger a state snapshot in the social_tracker (Async)."""
    if shutdown_manager.shutting_down:
        return
    try:
        await social_tracker.save_snapshot()
    except (RuntimeError, asyncio.CancelledError):
        # Silent failure on shutdown/cancellation is expected
        pass
    except Exception as e:
        log_warning(f"Async save of replied IDs failed: {e}")


async def _reconstruct_bluesky_history():
    """Fetch recent bot posts from Bluesky and rebuild thread counts efficiently."""
    global _silenced_replied_ids
    try:
        await asyncio.to_thread(_ensure_social_imports)
        if not is_bluesky_configured or not is_bluesky_configured() or shutdown_manager.shutting_down: return
        
        client = await get_bluesky_client()
        if not client: return
        
        # Reset counts for fresh reconstruction
        handle = os.getenv("BLUESKY_HANDLE")
        response = await client.app.bsky.feed.get_author_feed(params=models.AppBskyFeedGetAuthorFeed.Params(actor=handle, limit=50))
        
        # Phase 1: Collect parent URIs
        reply_map = {} # {bot_post_uri: (root_uri, parent_uri)}
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
        author_map = {} # {post_uri: author_handle}
        
        # Batch by 25 (get_posts limit is usually 25-50)
        for i in range(0, len(parent_uris), 25):
            if shutdown_manager.shutting_down:
                break
                
            batch = parent_uris[i : i + 25]
            try:
                posts_response = await client.app.bsky.feed.get_posts(params=models.AppBskyFeedGetPosts.Params(uris=batch))
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
async def _reconstruct_x_history():
    """Fetch recent bot posts from X and rebuild thread counts with retry."""
    global _silenced_replied_ids
    
    async def run_reconstruct(force_new=False):
        if not config.x_enabled or shutdown_manager.shutting_down: return 0
        
        from utils.social.kaia_twitter import get_x_client
        client = await get_x_client(force_new=force_new)
        if not client: return 0
        
        username = os.getenv("X_USERNAME")
        if not username: return 0
        
        # Get user ID first
        user_id = await client.user_id()
        # Fetch last 40 tweets (Tweets + Replies)
        response = await client.get_user_tweets(user_id, 'Replies', count=40)
        
        if not response:
            return 0

        current_count = 0
        for tweet in response:
            if shutdown_manager.shutting_down: break
            
            in_reply_to = getattr(tweet, 'in_reply_to', None)
            if in_reply_to:
                mention_id = f"x:{in_reply_to}"
                _silenced_replied_ids.add(mention_id)
                root_id = in_reply_to
                try:
                    root_id = tweet._legacy.get('conversation_id_str', in_reply_to)
                except Exception: pass
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
        error_str = str(e).lower()
        if "unauthorized" in error_str or "auth" in error_str or "401" in error_str:
            log_warning(f"X history reconstruction failed (401), retrying: {e}")
            try:
                count = await run_reconstruct(force_new=True)
                if count > 0:
                    log_info(f"Reconstructed thread state for {count} X replies after re-auth.")
            except Exception as e2:
                log_error(f"Failed X history reconstruction after re-auth: {e2}")
        else:
            log_warning(f"Failed to reconstruct X history: {e}")


async def _generate_response(mention_text: str, author_name: str, platform: str, on_message_func, parent_text: Optional[str] = None, root_text: Optional[str] = None) -> Optional[str]:
    """Generate a response using the main Kaiacord engine.
    
    This pipes the mention through the full RAG, memory, and persona pipeline 
    by leveraging the shared inference engine in Kaiacord.py.
    """
    try:
        # Define social-specific variables
        char_limit = 300 if platform == "bluesky" else 280
        author_id = f"social_{platform}_{author_name}"
        
        # ADD DEBUG LOGGING
        log_info(f"Social mention from @{author_name} ({platform}): {mention_text[:50]}...")
        
        response = await mock_external_mention(
            on_message_func=on_message_func,
            content=mention_text,
            author_name=author_name,
            author_id=author_id,
            platform=platform,
            parent_text=parent_text,
            root_text=root_text
        )
        
        if not response:
            log_warning(f"Main engine returned empty response for social mention from @{author_name}.")
            return None
            
        # LOG SUCCESSFUL RETRIEVAL
        log_info(f"Main engine response: {response[:100]}...")
        
        if response:
            response = BotSpeakFilter.strip_bot_speak(response)
            
        # Enforce char limit strictly for social (Try cutting at sentence end first)
        if response and len(response) > char_limit:
            # Try to cut at the last sentence end (., !, ?) within the limit
            sentences = re.split(r'(?<=[.!?])\s+', response)
            short_resp = ""
            for s in sentences:
                candidate = (short_resp + " " + s).strip()
                if len(candidate) <= char_limit:
                    short_resp = candidate
                else: break
            
            if short_resp:
                response = short_resp
            else:
                # Absolute fallback: hard truncation
                response = response[:char_limit-3].strip() + "..."
            
        return response
        
    except Exception as e:
        log_error(f"Failed to generate social response via main engine: {e}")
        traceback.print_exc()
        return None


async def _get_bluesky_mentions() -> List[Dict[str, Any]]:
    """Fetch unread mentions from Bluesky."""
    if shutdown_manager.shutting_down:
        return []
        
    mentions = []
    
    # Circuit breaker check
    if not _bluesky_breaker.can_proceed():
        log_debug("Bluesky circuit breaker open - skipping fetch")
        return []
    
    async def run_fetch(force_new=False):
        global _silenced_replied_ids
        from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured
        from utils.infrastructure.system.yaml_config import config
        
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


async def _get_x_mentions() -> List[Dict[str, Any]]:
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
            return []
        
        client = await get_x_client(force_new=force_new)
        if not client:
            return []
            
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
        error_str = str(e).lower()
        error_type = type(e).__name__
        
        # Recover from auth/unauthorized errors by clearing session
        if "unauthorized" in error_str or "auth" in error_str or "login" in error_str or "401" in error_str:
            log_warning(f"X session potentially expired (401), retrying with new client: {e}")
            try:
                mentions = await run_fetch(force_new=True)
                _x_breaker.record_success()
                log_success("X fetch succeeded after re-authentication.")
            except Exception as e2:
                log_error(f"Failed to fetch X mentions after re-auth retry ({type(e2).__name__}): {e2}")
                _x_breaker.record_failure()
        else:
            log_error(f"Failed to fetch X mentions ({error_type}): {e}")
            _x_breaker.record_failure()
    
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
        error_str = str(e).lower()
        if "unauthorized" in error_str or "auth" in error_str or "401" in error_str:
            log_warning(f"X reply failed (401), retrying with fresh session: {e}")
            try:
                return await run_reply(force_new=True)
            except Exception as e2:
                log_error(f"Failed to reply on X after re-auth: {e2}")
        else:
            log_error(f"Failed to reply on X: {e}")
        return False


async def check_and_reply_mentions(on_message_func):
    """
    Main polling function - check both platforms and reply to mentions.
    
    Call this from a periodic task loop.
    """
    if shutdown_manager.shutting_down:
        return 0
        
    global _first_poll_done, _silenced_replied_ids
    
    # log_debug("Social media poll started...")
    
    # Load replied IDs if not loaded (Offload to thread)
    # social_tracker loads automatically on init, but we keep this for consistency if needed
    pass
    
    # SAFETY: High-integrity session safety.
    # 1. Reconstruct thread counts from real platform state (prevents loops even if storage wiped)
    # 2. Skip first poll replies (populates history only)
    if not _first_poll_done:
        log_debug("Social media poll started...")
        log_info("Initializing social safety scan (Session Start)...")
        
        # FIX: CONCURRENT RECONSTRUCTION (Strictly honoring enabled flags)
        # Reconstruct thread counts and replied IDs from bot's own recent activity
        # We run these in parallel to prevent stacking serial blocking/IO time.
        tasks = []
        
        if config.bluesky_enabled:
            tasks.append(_reconstruct_bluesky_history())
        else:
            log_debug("Bluesky disabled - skipping history reconstruction.")
            
        if config.x_enabled:
            tasks.append(_reconstruct_x_history())
        else:
            log_debug("X/Twitter disabled - skipping history reconstruction.")
            
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        await _save_replied_ids_async()
        _first_poll_done = True
        log_success("Social safety initialization complete. Thread caps and history restored.")
        # Proceed immediately to process any missed mentions
    
    # FIX: Removed duplicate _first_poll_done = True and total_replies = 0 assignments
    total_replies = 0
    
    # helper for generating response that uses the passed on_message_func
    async def generate_response_with_callback(text, author, platform, parent_text=None, root_text=None):
        return await _generate_response(text, author, platform, on_message_func, parent_text=parent_text, root_text=root_text)
    
    # Check Bluesky
    if config.bluesky_enabled and config.get('bluesky.reply_to_mentions', True):
        mentions = await _get_bluesky_mentions()
        if mentions:
            log_info(f"Bluesky poll: Found {len(mentions)} unhandled mentions. Processing up to 10.")
        
        for mention in mentions[:10]:  # Limit to 10 per poll to clear backlog faster
            if shutdown_manager.shutting_down:
                break
                
            author = mention['author']
            text = mention['text']
            parent_text = mention.get('parent_text')
            root_text = mention.get('root_text')
            
            # ANTI-BOT LOOP PROTECTION (Standardized to 5 replies per user)
            admin_handles = config.get('social.admin_handles', [])
            is_admin = author in admin_handles
            
            # Standardized thread limit check (applies to everyone)
            root_uri = _get_root_uri(mention)
            user_reply_count = social_tracker.get_thread_count(root_uri, author)
            
            # Use MAX_THREAD_REPLIES (5) for everyone
            if not is_admin and user_reply_count >= MAX_THREAD_REPLIES:
                log_warning(f"Thread limit ({MAX_THREAD_REPLIES}) reached for @{author} in thread {root_uri[:30]}. Skipping.")
                _silenced_replied_ids.add(mention['id'])
                continue

            log_info(f"Bluesky mention from @{author}: {text[:50]}...")
            
            response = await generate_response_with_callback(text, author, "bluesky", parent_text=parent_text, root_text=root_text)
            if response:
                success = await _reply_to_bluesky(mention, response)
                if success:
                    root_uri = _get_root_uri(mention)
                    await social_tracker.mark_replied(mention['id'], "bluesky", root_uri, author)
                    _silenced_replied_ids.add(mention['id'])
                        
                    log_success(f"Replied to @{author} on Bluesky (User thread count: {social_tracker.get_thread_count(root_uri, author)}): {response[:50]}...")
                    await _save_replied_ids_async()  # Async persistence
                    total_replies += 1
    
    # Check X
    if config.x_enabled and config.get('x_twitter.reply_to_mentions', True):
        mentions = await _get_x_mentions()
        if mentions:
            log_info(f"X poll: Found {len(mentions)} unhandled mentions. Processing up to 3.")
        
        for mention in mentions[:3]:  # Limit to 3 per poll
            if shutdown_manager.shutting_down:
                break
                
            author = mention['author']
            text = mention['text']
            root_id = mention['root_id']
            mention_id = mention['id'] # Ensure mention_id is available here
            
            # ANTI-BOT LOOP PROTECTION (Standardized to 5 replies per user)
            admin_handles = config.get('social.admin_handles', [])
            is_admin = author in admin_handles
            
            user_reply_count = social_tracker.get_thread_count(root_id, author)
            
            if not is_admin and user_reply_count >= MAX_THREAD_REPLIES:
                log_warning(f"Thread limit ({MAX_THREAD_REPLIES}) reached for @{author} in X thread {root_id}. Skipping.")
                _silenced_replied_ids.add(mention['id'])
                continue

            log_info(f"X mention from @{author}: {text[:50]}...")
            
            # Fetch context for X (Parent/Root)
            parent_text = None
            root_text = None
            try:
                client = await get_x_client()
                if client:
                    if mention['parent_id']:
                        parent_tweet = await client.get_tweet_by_id(mention['parent_id'])
                        if parent_tweet: parent_text = parent_tweet.text
                    
                    if root_id and root_id != mention['parent_id'] and root_id != mention['tweet_id']:
                        root_tweet = await client.get_tweet_by_id(root_id)
                        if root_tweet: root_text = root_tweet.text
            except Exception as e:
                log_warning(f"Failed to fetch X thread context: {e}")
            
            response = await generate_response_with_callback(text, author, "x", parent_text=parent_text, root_text=root_text)
            if response:
                success = await _reply_to_x(mention, response)
                if success:
                    await social_tracker.mark_replied(mention_id, "x", root_id, author)
                    _silenced_replied_ids.add(mention_id)
                        
                    log_success(f"Replied to @{author} on X (User thread count: {social_tracker.get_thread_count(root_id, author)}): {response[:50]}...")
                    await _save_replied_ids_async()  # Async persistence
                    total_replies += 1
    
    if total_replies > 0:
        log_info(f"Social media polling complete: {total_replies} replies sent")
    
    return total_replies


async def mock_external_mention(on_message_func, content: str, author_name: str, author_id: Any, platform: str, parent_text: Optional[str] = None, root_text: Optional[str] = None):
    import uuid
    from contextlib import asynccontextmanager
    from typing import Optional
    from utils.infrastructure.system.messaging import MockMessage, MockUser, MockChannel

    log_info(f"Mocking {platform} message from {author_name}...")

    # If root/parent text is provided, wrap content with context tags
    # This ensures the engine sees the thread context immediately
    context_prefix = ""
    if root_text and root_text != parent_text:
        context_prefix += f"[ORIGINAL_POST]\n{root_text}\n\n"
    
    if parent_text:
        context_prefix += f"[REPLYING_TO]\n{parent_text}\n\n"
        
    if context_prefix:
        content = f"{context_prefix}[USER_MESSAGE]\n{content}"

    # Use unified Mock infrastructure
    mock_author = MockUser(id=author_id, name=author_name, display_name=author_name)
    # Stable int hash for channel ID ensures memory persistence across runs
    channel_id = abs(hash(f"{platform}_{author_id}")) % 10**12
    mock_channel = MockChannel(id=channel_id, name=f"{platform}_mentions")
    
    msg = MockMessage(content=content, author=mock_author, channel=mock_channel, platform=platform)
    
    # Process the message
    await on_message_func(msg)
    
    if msg.channel.sent_messages:
        full_response = "\n".join(msg.channel.sent_messages)
        return full_response.replace("```\n", "").replace("```", "").strip()
    return None



# ── Extracted Response Generation (Phase 28 / CQ-01) ─────────────────────
from utils.social.social_response_generator import (           # noqa: F401
    get_random_memories,
    get_random_dream_reflection,
    get_recent_events_for_reflection,
    clean_quip,
    is_interesting_post,
    is_too_vague,
    _split_into_thread_posts,
    generate_social_thread,
    generate_quip,
)


