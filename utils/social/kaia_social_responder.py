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

# HEAVY IMPORTS: Moved to top-level to prevent event loop stalls during lazy initialization.
# These libraries (especially atproto) have significant import overhead (~5s).
try:
    from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured
    from atproto import models
except ImportError:
    log_warning("Social libraries (atproto) not found. Some social features may be limited.")
    get_bluesky_client = is_bluesky_configured = models = None

def warm_social_libraries():
    """No-op function to trigger top-level imports of heavy social libraries."""
    log_info("Warming social libraries (atproto, twikit)...")
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

# Replied mentions tracker (persisted to disk)
_replied_ids_path = Path("memory/social_replied_ids.json")

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
        mtime = persona_file.stat().st_mtime
        if _persona_cache and mtime <= _persona_last_load:
            return _persona_cache
            
        with open(persona_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            _persona_cache = content
            _persona_last_load = mtime
            return _persona_cache
    except Exception:
        if _persona_cache:
            return _persona_cache
        return "You are Kaia, a blunt and grounded resident of this server."


async def load_persona_async() -> str:
    """Load the bot's persona from kaia_persona.md with caching (Async)"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, load_persona)

_replied_ids: set = set()
_thread_counts: Dict[str, Dict[str, int]] = {}  # Track replies per user per thread {root_uri: {user_handle: count}}
_replied_ids_lock = asyncio.Lock()  # Protects BOTH _replied_ids AND _thread_counts
_first_poll_done = False


def _trim_replied_ids():
    """Evict old replied IDs to prevent unbounded memory growth."""
    global _replied_ids
    if len(_replied_ids) > MAX_REPLIED_IDS:
        _replied_ids = set(sorted(_replied_ids)[-MAX_REPLIED_IDS:])
        log_debug(f"Trimmed replied IDs to {MAX_REPLIED_IDS}")


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
    """Load set of already-replied mention IDs from disk."""
    global _replied_ids, _thread_counts
    try:
        if _replied_ids_path.exists():
            with open(_replied_ids_path, 'r') as f:
                data = json.load(f)
                _replied_ids = set(data.get('bluesky', []) + data.get('x', []))
                _thread_counts = data.get('thread_counts', {})
                log_debug(f"Loaded {len(_replied_ids)} replied IDs from disk")
    except json.JSONDecodeError as e:
        log_warning(f"Corrupted replied IDs file, resetting: {e}")
        _replied_ids = set()
        _thread_counts = {}
    except Exception as e:
        log_warning(f"Failed to load replied IDs: {e}")
    
    # MIGRATION: Ensure _thread_counts is Dict[str, Dict[str, int]]
    # If the root values are integers, the file was from an older version.
    if _thread_counts and not all(isinstance(v, dict) for v in _thread_counts.values()):
        log_info("Migrating social thread_counts to per-user format...")
        new_counts = {}
        for k, v in _thread_counts.items():
            if isinstance(v, dict):
                new_counts[k] = v
            else:
                # We don't know who the old count was for, but we'll assign it to 'unknown' 
                # to maintain the thread-level cap for old conversations.
                new_counts[k] = {"__legacy_total__": v}
        _thread_counts = new_counts


def _save_replied_ids():
    """Save replied IDs to disk with atomic write to prevent corruption."""
    try:
        _replied_ids_path.parent.mkdir(exist_ok=True)
        # Split by platform prefix
        bluesky_ids = [i for i in _replied_ids if i.startswith('bsky:')]
        x_ids = [i for i in _replied_ids if i.startswith('x:')]
        
        data = {
            'bluesky': bluesky_ids, 
            'x': x_ids,
            'thread_counts': _thread_counts
        }
        
        # Atomic write: write to temp file then rename
        # This prevents corruption if the process crashes mid-write
        temp_path = _replied_ids_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Atomic rename (on POSIX systems)
        temp_path.replace(_replied_ids_path)
        log_debug(f"Saved {len(_replied_ids)} replied IDs to disk")
        
    except Exception as e:
        log_warning(f"Failed to save replied IDs: {e}")


async def _save_replied_ids_async():
    """Async-safe wrapper for saving replied IDs."""
    if shutdown_manager.shutting_down:
        return
    try:
        await asyncio.to_thread(_save_replied_ids)
    except (RuntimeError, asyncio.CancelledError):
        # Silent failure on shutdown/cancellation is expected
        pass
    except Exception as e:
        log_warning(f"Async save of replied IDs failed: {e}")


async def _reconstruct_bluesky_history():
    """Fetch recent bot posts from Bluesky and rebuild thread counts efficiently."""
    global _thread_counts
    try:
        if not is_bluesky_configured() or shutdown_manager.shutting_down: return
        
        client = await get_bluesky_client()
        if not client: return
        
        # Reset counts for fresh reconstruction
        _thread_counts = {}
        handle = os.getenv("BLUESKY_HANDLE")
        response = await client.app.bsky.feed.get_author_feed(params=models.AppBskyFeedGetAuthorFeed.Params(actor=handle, limit=50))
        
        # Phase 1: Collect parent URIs
        reply_map = {} # {bot_post_uri: (root_uri, parent_uri)}
        for item in response.feed:
            post = item.post
            reply = getattr(post.record, 'reply', None)
            if reply:
                reply_map[post.uri] = (reply.root.uri, reply.parent.uri)
        
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
        async with _replied_ids_lock:
            for bot_post_uri, (root_uri, parent_uri) in reply_map.items():
                replied_to_author = author_map.get(parent_uri)
                if replied_to_author:
                    if root_uri not in _thread_counts:
                        _thread_counts[root_uri] = {}
                    _thread_counts[root_uri][replied_to_author] = _thread_counts[root_uri].get(replied_to_author, 0) + 1
                
                # Always mark the parent as replied if we found our own reply to it
                _replied_ids.add(f"bsky:{parent_uri}")
                count += 1
        
        if count > 0:
            log_info(f"Reconstructed thread counts and replied IDs for {count} Bluesky replies.")
    except Exception as e:
        log_warning(f"Failed to reconstruct Bluesky history: {e}")
async def _reconstruct_x_history():
    """Fetch recent bot posts from X and rebuild thread counts with retry."""
    global _thread_counts, _replied_ids
    
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
        async with _replied_ids_lock:
            for tweet in response:
                if shutdown_manager.shutting_down: break
                
                in_reply_to = getattr(tweet, 'in_reply_to', None)
                if in_reply_to:
                    _replied_ids.add(f"x:{in_reply_to}")
                    root_id = in_reply_to
                    try:
                        root_id = tweet._legacy.get('conversation_id_str', in_reply_to)
                    except: pass
                    
                    _thread_counts.setdefault(root_id, {})
                    _thread_counts[root_id]["__reconstructed__"] = _thread_counts[root_id].get("__reconstructed__", 0) + 1
                    current_count += 1
                
                # Yield every few tweets to prevent hogging the loop
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
                
                if mention_id in _replied_ids:
                    log_debug(f"Skipping already-replied mention: {mention_id}")
                    continue

                # Thread tracking: root_uri is the anchor for the thread
                root = getattr(getattr(notif.record, 'reply', None), 'root', None)
                root_uri = root.uri if root and hasattr(root, 'uri') else notif.uri
                
                user_handle = notif.author.handle
                thread_data = _thread_counts.get(root_uri, {})
                user_reply_count = thread_data.get(user_handle, 0)
                
                # Admin check (must be defined here, not just in check_and_reply_mentions)
                admin_handles = config.get('social.admin_handles', [])
                is_admin = user_handle in admin_handles
                
                log_debug(f"Checking mention {mention_id} from @{user_handle} in thread {root_uri[:30]}. Current count: {user_reply_count}")
                
                if not is_admin and user_reply_count >= MAX_THREAD_REPLIES:
                    log_warning(f"Thread limit reached for @{user_handle} in Bluesky thread: {root_uri[:40]}... Polling will skip until manual reset or limit increase.")
                    
                    # FIX: Add to _replied_ids so we don't spam the logs every poll cycle
                    async with _replied_ids_lock:
                        _replied_ids.add(mention_id)
                        _trim_replied_ids()
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
            
            if mention_id not in _replied_ids:
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
        
    global _replied_ids, _first_poll_done
    
    # log_debug("Social media poll started...")
    
    # Load replied IDs if not loaded (Offload to thread)
    if not _replied_ids:
        await asyncio.to_thread(_load_replied_ids)
    
    # SAFETY: High-integrity session safety.
    # 1. Reconstruct thread counts from real platform state (prevents loops even if storage wiped)
    # 2. Skip first poll replies (populates history only)
    if not _first_poll_done:
        log_debug("Social media poll started...")
        log_info("Initializing social safety scan (Session Start)...")
        
        # FIX: CONCURRENT RECONSTRUCTION
        # Reconstruct thread counts and replied IDs from bot's own recent activity
        # We run these in parallel to prevent stacking serial blocking/IO time.
        await asyncio.gather(
            _reconstruct_bluesky_history(),
            _reconstruct_x_history(),
            return_exceptions=True
        )
        
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
            thread_data = _thread_counts.get(root_uri, {})
            user_reply_count = thread_data.get(author, 0)
            
            # Use MAX_THREAD_REPLIES (5) for everyone
            if not is_admin and user_reply_count >= MAX_THREAD_REPLIES:
                log_warning(f"Thread limit ({MAX_THREAD_REPLIES}) reached for @{author} in thread {root_uri[:30]}. Skipping.")
                async with _replied_ids_lock:
                    _replied_ids.add(mention['id'])
                continue

            log_info(f"Bluesky mention from @{author}: {text[:50]}...")
            
            response = await generate_response_with_callback(text, author, "bluesky", parent_text=parent_text, root_text=root_text)
            if response:
                success = await _reply_to_bluesky(mention, response)
                if success:
                    root_uri = _get_root_uri(mention)
                    async with _replied_ids_lock:
                        _replied_ids.add(mention['id'])
                        if root_uri not in _thread_counts:
                            _thread_counts[root_uri] = {}
                        _thread_counts[root_uri][author] = _thread_counts[root_uri].get(author, 0) + 1
                        _trim_replied_ids()
                        
                    log_success(f"Replied to @{author} on Bluesky (User thread count: {_thread_counts[root_uri][author]}): {response[:50]}...")
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
            
            # ANTI-BOT LOOP PROTECTION (Standardized to 5 replies per user)
            admin_handles = config.get('social.admin_handles', [])
            is_admin = author in admin_handles
            
            thread_data = _thread_counts.get(root_id, {})
            user_reply_count = thread_data.get(author, 0)
            
            if not is_admin and user_reply_count >= MAX_THREAD_REPLIES:
                log_warning(f"Thread limit ({MAX_THREAD_REPLIES}) reached for @{author} in X thread {root_id}. Skipping.")
                async with _replied_ids_lock:
                    _replied_ids.add(mention['id'])
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
                    async with _replied_ids_lock:
                        _replied_ids.add(mention['id'])
                        if root_id not in _thread_counts:
                            _thread_counts[root_id] = {}
                        _thread_counts[root_id][author] = _thread_counts[root_id].get(author, 0) + 1
                        _trim_replied_ids()
                        
                    log_success(f"Replied to @{author} on X (User thread count: {_thread_counts[root_id][author]}): {response[:50]}...")
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


async def get_random_memories(limit=20):
    """Get random interaction snippets from any user log in the knowledge base.
    
    Offloaded to a thread to prevent blocking the event loop during directory scans.
    """
    def _fetch_memories():
        import os
        import random
        from pathlib import Path
        
        memories = []
        project_root = Path(__file__).parent.parent.parent
        base_dir = project_root / "knowledge_base" / "user_logs"
        
        if not base_dir.exists():
            return []
            
        # 1. Gather subdirectories instead of full rglob immediately
        # This prevents scanning the entire tree if there are thousands of files.
        try:
            subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
            if not subdirs:
                # Fallback to root if no subdirs
                all_files = list(base_dir.glob("interactions_*.md")) + list(base_dir.glob("interactions_*.txt"))
            else:
                # Pick 5 random subdirs to scan
                chosen_dirs = random.sample(subdirs, min(5, len(subdirs)))
                all_files = []
                for d in chosen_dirs:
                    all_files.extend(list(d.glob("interactions_*.md")))
                    all_files.extend(list(d.glob("interactions_*.txt")))
            
            if not all_files:
                return []
                
            # 2. Sample random files
            sample_size = min(15, len(all_files))
            sampled_files = random.sample(all_files, sample_size)
            
            for log_file in sampled_files:
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()
                        if len(lines) > 20:
                            start = random.randint(0, len(lines) - 20)
                            chunk = lines[start:start+20]
                        else:
                            chunk = lines
                            
                        for line in chunk:
                            if "Kaia:" in line or "User:" in line:
                                is_kaia = "Kaia:" in line
                                prefix = "Kaia:" if is_kaia else "User:"
                                parts = line.split(prefix, 1)
                                if len(parts) >= 2:
                                    msg = parts[1].strip()
                                    if 20 < len(msg) < 400:
                                        if any(skip in msg.lower() for skip in ["[vision]", "[idle", "hello", "error:"]):
                                            continue
                                        memories.append({
                                            "text": msg,
                                            "type": "said" if is_kaia else "heard"
                                        })
                except Exception:
                    continue
        except Exception as e:
            from utils.infrastructure.logging.kaia_logger import log_error
            log_error(f"Error in background memory scan: {e}")
            return []
            
        random.shuffle(memories)
        return memories[:limit]

    return await asyncio.to_thread(_fetch_memories)

async def get_random_dream_reflection(limit=5):
    """Pick a random dream file and extract Kaia's Reflection.
    
    Offloaded to a thread to prevent blocking the event loop.
    """
    def _fetch_dreams():
        import os
        import random
        from pathlib import Path
        
        reflections = []
        project_root = Path(__file__).parent.parent.parent
        base_dir = project_root / "knowledge_base" / "kaia_dreams"
        
        if not base_dir.exists():
            return []
            
        try:
            # Gather all dream files recursively (Dreams are fewer, so rglob is okay but still threaded)
            all_files = list(base_dir.rglob("dream_*.md"))
            if not all_files:
                return []
                
            sampled_files = random.sample(all_files, min(limit * 2, len(all_files)))
            
            for dream_file in sampled_files:
                try:
                    with open(dream_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Extract Source
                        source = "unknown archive"
                        if "Source: " in content:
                            source = content.split("Source: ")[1].split("\n")[0].strip()
                        
                        # Extract original fragment
                        fragment = ""
                        if "## Original Fragment" in content and "## Kaia's Reflection" in content:
                            fragment = content.split("## Original Fragment")[1].split("## Kaia's Reflection")[0].strip()
                            if fragment.startswith(">"):
                                fragment = fragment.replace(">", "").strip()
                        
                        if fragment:
                            reflections.append({
                                "text": fragment,
                                "source": source,
                                "category": dream_file.parent.name,
                                "type": "dream_fragment"
                            })
                except Exception:
                    continue
        except Exception:
            return []
            
        random.shuffle(reflections)
        return reflections[:limit]

    return await asyncio.to_thread(_fetch_dreams)

async def get_recent_events_for_reflection(run_rag_func, rag_instance):
    """Get recent events for reflection-based posts."""
    try:
        # Use existing search_recent_events with a broad query
        events = await run_rag_func(
            rag_instance.search_recent_events,
            query="error crash deploy debug kaia vision memory",
            hours=24,
            limit=5
        )
        return events
    except Exception:
        return []

def clean_quip(quip_text, max_chars=800):  # Increased default
    """Clean up generated text while preserving substance."""
    if not quip_text:
        return ""
    
    # Keep more of the original structure
    # Don't strip asterisks or parens
    clean_text = quip_text
    
    # Remove meta-commentary but keep content
    meta_phrases = [
        "here are my thoughts:", "in this thread:", 
        "my take:", "to elaborate:", "thread:", 
        "kaia says:", "response:"
    ]
    for phrase in meta_phrases:
        if clean_text.lower().startswith(phrase):
            clean_text = clean_text[len(phrase):].strip()
    
    # Strip hallucinated bracket placeholders (e.g. [LINK_TO_ARCHIVE], [IMAGE_HERE])
    # Requires underscore OR 4+ uppercase chars to avoid stripping legitimate [NOTE], [EDIT], etc.
    clean_text = re.sub(r'\[\s*[A-Z][A-Z_]*_[A-Z_]*\s*\]', '', clean_text)  # Must contain underscore
    clean_text = re.sub(r'\[\s*[A-Z]{4,}\s*\]', '', clean_text).strip()  # Or 4+ uppercase chars
    
    # Ensure it ends with proper punctuation
    if clean_text and clean_text[-1] not in '.!?…"':
        clean_text += '.'
    
    # Cap at reasonable length (soft limit, thread splitter handles hard limits)
    if len(clean_text) > max_chars:
        # Try to cut at sentence boundary
        last_period = clean_text[:max_chars-3].rfind('.')
        if last_period > max_chars * 0.5:  # At least 50% of the text
            clean_text = clean_text[:last_period+1]
        else:
            clean_text = clean_text[:max_chars-3] + '...'
    
    return clean_text.strip()


def is_interesting_post(text):
    """Check if a post says something substantive."""
    # Too short or vague
    if len(text) < 120: 
        return False
    
    # Substantive markers (Connectors + Perspective shifts)
    content_markers = [
        ' because ', ' actually ', ' specifically ', 
        ' example ', ' remember ', ' like when ', 
        ' but ', ' however ', ' though ', ' surprisingly ',
        ' unless ', ' until ', ' instead ', ' rather ',
        ' implies ', ' means ', ' reveals ', ' suggests ',
        ' always ', ' never ', ' only ', ' just ',
        ' reliant ', ' beneath ', ' behind ', ' between ',
        ' underneath ', ' despite ', ' without ', ' within ',
        ' every ', ' nothing ', ' everything ', ' most ',
        ' yet ', ' still ', ' already ', ' except '
    ]
    
    has_marker = any(marker in text.lower() for marker in content_markers)
    
    # Alternative: Presence of systemic/contemplative words
    systemic_words = [
        'system', 'network', 'pattern', 'mirror', 'architecture', 
        'design', 'logic', 'machine', 'human', 'layer', 'structure',
        'infrastructure', 'brittle', 'fracture', 'collapse', 'signal',
        'noise', 'entropy', 'recursion', 'loop', 'feedback', 'control',
        'commerce', 'government', 'surveillance', 'algorithm', 'data'
    ]
    has_systemic = any(word in text.lower() for word in systemic_words)

    # Word count check: 10+ words with em-dashes or ellipsis = contemplative = likely good
    word_count = len(text.split())
    has_depth_cues = word_count >= 10 and ('—' in text or '…' in text or '...' in text)
    
    return has_marker or has_systemic or has_depth_cues


def is_too_vague(text):
    """Filter out vague platitudes."""
    vague_phrases = [
        'things will change', 'interesting times', 
        'we live in a society', 'that\'s how it is',
        'it is what it is', 'just saying', 'time will tell',
        'remains to be seen'
    ]
    
    return any(phrase in text.lower() for phrase in vague_phrases)


def _split_into_thread_posts(text, max_chars=X_CHAR_LIMIT, max_posts=MAX_THREAD_POSTS):
    """Split generated text into logical thread posts using smart cutting.
    
    Args:
        text: The text to split.
        max_chars: Maximum characters per post (default: X_CHAR_LIMIT=280).
        max_posts: Maximum number of posts in the thread.
    """

    posts = []
    text = text.strip()
    
    # Pre-clean: Remove "Thread:" prefix if present
    if text.lower().startswith("thread:"):
        text = text[7:].strip()
        
    start = 0
    
    while start < len(text):
        # If remaining text fits, just take it
        if len(text) - start <= max_chars:
            posts.append(text[start:].strip())
            break
            
        # Define the chunk we are looking at
        end = start + max_chars
        chunk = text[start:end]
        
        # Look for a "good" split point in the last 60 characters
        # Priority: Sentence End > Clause End > Space
        
        search_zone_start = max(0, len(chunk) - 60)
        search_zone = chunk[search_zone_start:]
        
        split_index = -1
        
        # 1. Look for sentence endings
        sentence_match = list(re.finditer(r'[.!?]["\u201d]?\s+', search_zone))
        if sentence_match:
            # Pick the last one
            split_index = search_zone_start + sentence_match[-1].end()
        
        # 2. If no sentence end, look for clause delimiters
        if split_index == -1:
            clause_match = list(re.finditer(r'[;,]\s+', search_zone))
            if clause_match:
                split_index = search_zone_start + clause_match[-1].end()
                
        # 3. If still nothing, look for the last space
        if split_index == -1:
            last_space = search_zone.rfind(' ')
            if last_space != -1:
                split_index = search_zone_start + last_space
                
        # 4. Total fallback: hard cut at limit (rare)
        if split_index == -1:
            split_index = len(chunk)
            
        posts.append(text[start:start+split_index].strip())
        start += split_index
        
    # Filter out empty posts
    posts = [p for p in posts if p]
    
    return posts[:max_posts]



async def generate_social_thread(bot, ollama_client, reflection_target, context_type):
    """Generate a proper thread instead of just a quip."""
    from utils.infrastructure.system.yaml_config import config
    
    system_prompt = await load_persona_async()
    
    thread_prompt = f"""Context: "{reflection_target}"

Task: Write a deep-dive Bluesky thread about this.
Guidelines:
1. Write a continuous cohesive thought stream.
2. DO NOT number your points (no "1/", "2/", "1.").
3. Just write. I will handle the cutting and formatting.
4. Speak naturally as Kaia (lowercase, blunt, grounded).
5. Go deep but stay concise (aim for 4-5 posts maximum). Connect systems to feelings.
6. DO NOT include any introductory preamble, metadata, or acknowledgement (e.g., no "Okay, here's a thread..."). Start the first post directly.

"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": thread_prompt}
    ]
    
    try:
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        gpu_manager = OllamaGPUManager(config.chat_model)
        options = gpu_manager.get_gpu_options(for_chat=True)
        # Higher temperature for threading to encourage creativity/length
        options['temperature'] = 0.8
        options['num_predict'] = 1000 # Ensure enough tokens for a thread
        
        response = await asyncio.wait_for(
            ollama_client.chat(
                model=config.chat_model,
                messages=messages,
                options=options
            ),
            timeout=600.0  # 10 minute absolute max for full thread generation
        )
        
        full_text = response['message']['content']
        max_threads = config.get('social.max_thread_posts', MAX_THREAD_POSTS)
        raw_posts = _split_into_thread_posts(full_text, max_posts=max_threads)
        
        # Apply hardening to each post in the thread
        posts = [BotSpeakFilter.strip_bot_speak(p) for p in raw_posts if p]
        return [p for p in posts if p]

        
    except Exception as e:
        log_error(f"Thread generation failed: {e}")
        return []



async def generate_quip(ctx, is_manual=False, target_channel=None, on_message_func=None):
    """Generate social posts by piping through the FULL Kaia engine.
    
    This ensures quips use the complete persona, RAG, and personalization pipeline
    rather than a truncated custom prompt.
    """
    import time
    import random
    # Dependencies from ctx
    bot = ctx.bot
    ollama_client = ctx.ollama_client
    rag_instance = ctx.rag
    bot_state = ctx.bot_state
    config = ctx.config

    if not is_manual:
        # Guard: skip if a user chat is actively generating
        if getattr(bot_state, 'is_generating', False):
            log_info("Quip deferred: user chat generation in progress.")
            return

        # Check if we need to FORCE a post due to time elapsed
        last_quip = bot_state.last_quip_time
        # Handle 0.0 case where it was never set (backward compatibility)
        if last_quip == 0.0:
            last_quip = bot_state.last_manual_quip_time
            
        time_since_last = time.time() - last_quip
        max_interval_seconds = config.social_max_interval_hours * 3600
        
        force_post = time_since_last > max_interval_seconds
        
        if not force_post:
            # Normal idle check
            idle_duration = time.time() - bot_state.last_interaction_time
            timeout = config.idle_quip_timeout_minutes
            
            if idle_duration < timeout * 60:
                return
            if bot_state.consecutive_quips >= config.max_consecutive_quips:
                return
        else:
            log_action(f"Forcing social post due to max interval ({time_since_last/3600:.1f}h > {config.social_max_interval_hours}h)")

    # Find target channel
    channel = target_channel
    if not channel:
        if bot_state.last_active_channel_id:
            channel = bot.get_channel(bot_state.last_active_channel_id)
            
        if not channel:
            # Fallback: Find any valid channel
            for guild in bot.guilds:
                for chan in sorted(guild.text_channels, key=lambda c: c.position):
                    if chan.permissions_for(guild.me).send_messages and chan.name.lower() not in config.blacklisted_channels:
                        channel = chan
                        bot_state.last_active_channel_id = channel.id
                        bot_state.save()
                        break
                if channel: break
    
    if not channel:
        log_error("Could not find a valid channel for quip.")
        return

    try:
        from utils.infrastructure.gpu.gpu_manager import ModelContextMonitor
        current_model = ModelContextMonitor.get_current_model()
        if current_model != config.chat_model:
            log_action(f"ACTION: Model {config.chat_model} is cold. Waking up for quip (this may take a moment)...")
            await channel.send("```\njust a second, waking up my brain...\n```")

        log_action(f"Generating quip via main engine in #{channel.name}...")
        
        # 1. MINE DREAMS AND MEMORIES for reflection context
        dreams = await get_random_dream_reflection(limit=5)
        memories = await get_random_memories(limit=10)
        
        reflection_target = None
        context_type = None
        
        # 2. DECIDE REFLECTION TARGET (70% dream/news, 30% memory/chat)
        if dreams and random.random() < 0.70:
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = _get_context_type_for_dream(dream)

        elif memories:
            memory = random.choice(memories)
            reflection_target = memory["text"]
            context_type = "something someone said" if memory.get("type") == "heard" else "something I said before"
        elif dreams:
            # Fallback for when memories are empty but dreams exist
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = _get_context_type_for_dream(dream)
        
        # concrete fallbacks if target is too thin
        if not reflection_target or len(reflection_target) < 30:
            concrete_fallbacks = [
                ("the way AI labs keep promising AGI next year like it's going five more minutes in the oven", "tech predictions"),
                ("how every social platform eventually becomes a shopping mall with worse vibes", "platform decay"),
                ("the eternal cycle of 'this new framework will fix everything' followed by six months of regret", "developer culture"),
                ("people who reply 'skill issue' to genuine bug reports", "internet culture"),
                ("the specific exhaustion of explaining the same thing for the fifth time", "digital labor"),
                ("how every app update removes a feature someone actually used", "software entropy"),
            ]
            reflection_target, context_type = random.choice(concrete_fallbacks)

        # 3. DECIDE: SINGLE OR THREAD?
        # User Feedback: Less threads overall (25%), less about news (10%), more about dreams (40%)
        thread_chance = 0.25
        if context_type:
            ctx_lower = context_type.lower()
            if "dream" in ctx_lower:
                thread_chance = 0.40
            elif "news" in ctx_lower or "politics" in ctx_lower or "technology" in ctx_lower or "business" in ctx_lower:
                thread_chance = 0.10
                
        should_make_thread = random.random() < thread_chance
        
        if should_make_thread:
            log_action(f"Attempting to generate a thread about: {context_type}...")
            posts = await generate_social_thread(bot, ollama_client, reflection_target, context_type)
            
            if posts and len(posts) > 1:
                # Post thread to Discord
                for i, post in enumerate(posts):
                    await channel.send(f"**[Thread {i+1}/{len(posts)}]**\n```\n{post}\n```")
                    await asyncio.sleep(1) # Slight visual delay
                
                # Cross-post thread
                if config.bluesky_cross_post_quips:
                    try:
                        from utils.social.kaia_bluesky import post_thread_to_bluesky
                        bsky_ok, _ = await post_thread_to_bluesky(posts)
                        if bsky_ok and target_channel:
                            await target_channel.send("```\nskeet thread sent ✓\n```")
                        elif not bsky_ok and target_channel:
                            await target_channel.send("```\nskeet thread failed ✗\n```")
                         # Also post the hook to X if enabled
                        if config.x_cross_post_quips:
                            from utils.social.kaia_twitter import post_quip_to_x
                            # Append link to thread if possible? For now just the first tweet
                            await post_quip_to_x(posts[0] + " (thread on bsky)")
                    except Exception as e:
                        log_error(f"Thread cross-post failed: {e}")
                        if target_channel:
                            await target_channel.send(f"```\nskeet thread failed: {e}\n```")
                
                # Update channel memory & RAG for each post in the thread
                if channel.id not in bot_state.channel_memory:
                    from collections import deque
                    bot_state.channel_memory[channel.id] = deque(maxlen=config.max_memory_messages)
                
                for post in posts:
                    bot_state.channel_memory[channel.id].append({"role": "assistant", "content": post})
                    if rag_instance:
                        await asyncio.to_thread(rag_instance.log_user_interaction, 
                                                user_id=f"channel_{channel.id}", 
                                                user_name="Kaia-Autonomous", 
                                                message_content="[AUTO_THREAD_PART]", 
                                                bot_response=post)
                
                # Update state
                bot_state.add_quip(posts[0]) # Track identifying post
                if not is_manual:
                    bot_state.consecutive_quips += 1
                    bot_state.last_quip_time = time.time()
                    bot_state.last_interaction_time = time.time()
                bot_state.save()
                log_success(f"Thread posted ({len(posts)} parts).")
                return True

        # 4. SINGLE POST FALLBACK (or design choice)
        log_action(f"Generating single broadcast quip...")
        
        system_prompt = await load_persona_async()
        
        # --- RAG INTEGRATION START ---
        try:
            search_query = ""
            if "news about" in context_type:
                search_query = context_type.replace("recent news about ", "")
            else:
                search_query = " ".join(reflection_target.split()[:10])
                
            if rag_instance and search_query:
                rag_results = await rag_instance.retrieve(search_query, top_k=3, category="general")
                if rag_results:
                    rag_block = "\n\n### RELEVANT KNOWLEDGE & MEMORIES\n"
                    from utils.core.rag_utils import get_node_text
                    for node in rag_results:
                        content = get_node_text(node)
                        if content: rag_block += f"- {content[:400].replace(chr(10), ' ')}...\n"
                    system_prompt += rag_block
        except Exception as rag_err:
            log_warning(f"Failed to inject RAG context: {rag_err}")
        # --- RAG INTEGRATION END ---

        # Length Decision: Always aim for substantive length
        length_instruction = "Aim for 200-280 characters. Use the space to say something substantive."

        # Standalone Broadcast Prompt
        final_prompt = (
            f"Context: \"{reflection_target}\"\n\n"
            "Task: Post a standalone broadcast thought inspired by this context.\n"
            "Guidelines:\n"
            "1. Speak from your persona (Kaia). Use your natural voice.\n"
            "2. NO FILLERS. DO NOT say 'it's funny how', 'interesting that', 'i wonder', or 'maybe'.\n"
            "3. Make a definitive, declarative statement. No 'huh?' or generic questions.\n"
            "4. Be contemplative and systemic. Connect the detail to a broader pattern of logic or architecture.\n"
            f"5. {length_instruction} Lowercase only."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": final_prompt}
        ]
        
        # 5. RETRY LOOP FOR QUALITY
        max_retries = 3
        actual_quip = None
        
        for attempt in range(max_retries):
            try:
                from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
                gpu_manager = OllamaGPUManager(config.chat_model)
                options = gpu_manager.get_gpu_options(for_chat=True)
                
                # Increase temperature on retries to encourage creativity
                options['temperature'] = 0.75 + (attempt * 0.1)
                
                # Vary prompt slightly on retries
                current_messages = messages.copy()
                if attempt > 0:
                    current_messages.append({"role": "user", "content": "That was a bit too short or generic. Give me something with more teeth—connect it to a specific systemic pattern or observation. Be definitive."})

                response = await asyncio.wait_for(
                    ollama_client.chat(
                        model=config.chat_model,
                        messages=current_messages,
                        options=options
                    ),
                    timeout=120.0
                )
                raw_quip = response['message']['content']
                processed_quip = clean_quip(raw_quip, max_chars=800)
                
                # Quality check
                if is_too_vague(processed_quip):
                    log_warning(f"Quip attempt {attempt+1} too vague: '{processed_quip}'. Skipping.")
                    continue
                    
                if not is_interesting_post(processed_quip):
                    log_warning(f"Quip attempt {attempt+1} too boring/short: '{processed_quip}'. Retrying...")
                    continue
                
                # If we get here, it's good enough
                actual_quip = processed_quip
                break
                
            except Exception as e:
                log_error(f"Generation attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1: return # Last attempt failed

        if not actual_quip:
            log_warning("All quip generation attempts failed quality check. Giving up.")
            return

        quip = actual_quip

        # 6. Apply strict hardening filter (strip_bot_speak is a classmethod)
        quip = BotSpeakFilter.strip_bot_speak(quip)
        
        if not quip or "too much entropy" in quip:
            log_warning("Quip failed hardening.")
            return

        # Ensure lowercase (persona style)
        if quip and quip[0].isupper():
            quip = quip[0].lower() + quip[1:]

        # 6. POST to Discord
        await channel.send(f"```\n{quip}\n```")

        # Update channel memory
        if channel.id not in bot_state.channel_memory:
            from collections import deque
            bot_state.channel_memory[channel.id] = deque(maxlen=config.max_memory_messages)
        bot_state.channel_memory[channel.id].append({"role": "assistant", "content": quip})
        
        # Log to RAG (Non-critical error handling)
        try:
            if rag_instance:
                if shutdown_manager.shutting_down:
                    log_warning("Shutdown in progress, skipping RAG logging for quip.")
                else:
                    await asyncio.to_thread(rag_instance.log_user_interaction, 
                                            user_id=f"channel_{channel.id}", 
                                            user_name="Kaia-Autonomous", 
                                            message_content="[AUTO_QUIP]", 
                                            bot_response=quip)
        except Exception as rag_err:
            log_error(f"Failed to log quip to RAG: {rag_err}")

        # 7. Cross-post
        if config.bluesky_cross_post_quips:
            try:
                from utils.social.kaia_bluesky import post_quip_to_bluesky
                await post_quip_to_bluesky(quip)
            except Exception as e:
                log_error(f"Bluesky post failed: {e}")
        
        if config.x_cross_post_quips:
            try:
                from utils.social.kaia_twitter import post_quip_to_x
                # Truncate for X if needed (soft truncate)
                x_quip = quip
                if len(x_quip) > 280:
                     x_quip = x_quip[:277] + "..."
                await post_quip_to_x(x_quip)
            except Exception as e:
                log_error(f"X post failed: {e}")

        # 8. UPDATE state
        bot_state.add_quip(quip)
        if not is_manual:
            bot_state.consecutive_quips += 1
            bot_state.last_quip_time = time.time()
            bot_state.last_interaction_time = time.time()
        bot_state.save()
        log_success(f"Quip sent: {quip[:80]}...")
        return True

    except Exception as e:
        log_error(f"Quip generation failed: {e}")
        log_debug(traceback.format_exc())
        return False

