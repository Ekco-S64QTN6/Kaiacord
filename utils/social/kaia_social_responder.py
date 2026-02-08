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
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error, log_action, log_debug
from utils.core.response_filter import BotSpeakFilter
from contextlib import asynccontextmanager

# Persona cache
_persona_cache = None
_persona_last_load = 0

# Replied mentions tracker (persisted to disk)
_replied_ids_path = Path("memory/social_replied_ids.json")

# =============================================================================
# CIRCUIT BREAKER: API Resilience Pattern
# Added: Feb 2026 for social media API stability
# Opens after repeated failures to prevent cascade effects
# =============================================================================
class CircuitBreaker:
    """Simple circuit breaker for API calls with exponential backoff."""
    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout: int = 300):
        self.name = name
        self.failures = 0
        self.threshold = failure_threshold
        self.reset_timeout = reset_timeout  # 5 minutes default
        self.last_failure_time = 0
        self.is_open = False
    
    def can_proceed(self) -> bool:
        """Check if calls should be allowed through."""
        if not self.is_open:
            return True
        # Check if reset timeout has passed
        import time
        if time.time() - self.last_failure_time >= self.reset_timeout:
            self.is_open = False
            self.failures = 0
            log_info(f"Circuit breaker '{self.name}' reset after timeout")
            return True
        return False
    
    def record_success(self):
        """Record successful API call."""
        self.failures = 0
        self.is_open = False
    
    def record_failure(self):
        """Record failed API call."""
        import time
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.threshold:
            self.is_open = True
            log_warning(f"Circuit breaker '{self.name}' OPEN after {self.failures} failures")

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
_thread_counts: Dict[str, int] = {}  # Track replies per thread root
_replied_ids_lock = asyncio.Lock()
_first_poll_done = False


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
    """Async-safe wrapper for saving replied IDs.
    Uses asyncio.to_thread to avoid blocking the event loop."""
    try:
        await asyncio.to_thread(_save_replied_ids)
    except Exception as e:
        log_warning(f"Async save of replied IDs failed: {e}")


async def _reconstruct_bluesky_history():
    """Fetch recent bot posts from Bluesky and rebuild thread counts."""
    global _thread_counts
    try:
        from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured
        if not is_bluesky_configured(): return
        
        client = await get_bluesky_client()
        if not client: return
        
        # Reset counts for fresh reconstruction
        _thread_counts = {}
        
        from atproto import models
        handle = os.getenv("BLUESKY_HANDLE")
        response = await client.app.bsky.feed.get_author_feed(params=models.AppBskyFeedGetAuthorFeed.Params(actor=handle, limit=50))
        
        count = 0
        for item in response.feed:
            post = item.post
            reply = getattr(post.record, 'reply', None)
            if reply:
                # 1. Track the thread root (for 3-reply cap)
                root_uri = reply.root.uri
                _thread_counts[root_uri] = _thread_counts.get(root_uri, 0) + 1
                
                # 2. Track that we already replied to the parent post
                # This prevents us from replying to it again during the first poll
                parent_uri = reply.parent.uri
                async with _replied_ids_lock:
                    _replied_ids.add(f"bsky:{parent_uri}")
                
                count += 1
        
        if count > 0:
            log_info(f"Reconstructed thread counts and replied IDs for {count} Bluesky replies.")
    except Exception as e:
        log_warning(f"Failed to reconstruct Bluesky history: {e}")


async def _generate_response(mention_text: str, author_name: str, platform: str, on_message_func) -> Optional[str]:
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
            platform=platform
        )
        
        if not response:
            log_warning(f"Main engine returned empty response for social mention from @{author_name}.")
            return None
            
        # LOG SUCCESSFUL RETRIEVAL
        log_info(f"Main engine response: {response[:100]}...")
        
        # Enforce char limit strictly for social (Try cutting at sentence end first)
        if len(response) > char_limit:
            # Try to cut at the last sentence end (., !, ?) within the limit
            import re
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
        import traceback
        traceback.print_exc()
        return None


async def _get_bluesky_mentions() -> List[Dict[str, Any]]:
    """Fetch unread mentions from Bluesky."""
    mentions = []
    
    # Circuit breaker check
    if not _bluesky_breaker.can_proceed():
        log_debug("Bluesky circuit breaker open - skipping fetch")
        return []
    
    async def run_fetch(force_new=False):
        from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured
        from utils.infrastructure.system.yaml_config import config
        
        if not is_bluesky_configured():
            return []
            
        client = await get_bluesky_client(force_new=force_new)
        if not client:
            return []
        
        # Get notifications
        notifs = await client.app.bsky.notification.list_notifications()

        from datetime import datetime, timezone, timedelta
        lookback_hours = config.get('social.mention_lookback_hours', 3)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        
        local_mentions = []
        for notif in notifs.notifications:
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
                
                if mention_id not in _replied_ids:
                    # Thread tracking: root_uri is the anchor for the thread
                    root = getattr(getattr(notif.record, 'reply', None), 'root', None)
                    root_uri = root.uri if root and hasattr(root, 'uri') else notif.uri
                    
                    # Check thread reply limit (max 3)
                    admin_handles = config.get('social.admin_handles', [])
                    is_admin = notif.author.handle in admin_handles
                    
                    if not is_admin and _thread_counts.get(root_uri, 0) >= 3:
                        log_warning(f"Thread limit reached for Bluesky thread: {root_uri[:40]}... Skipping.")
                        # Mark as replied so we don't keep logging it
                        async with _replied_ids_lock:
                            _replied_ids.add(mention_id)
                        continue

                    local_mentions.append({
                        'id': mention_id,
                        'uri': notif.uri,
                        'cid': notif.cid,
                        'author': notif.author.handle,
                        'text': getattr(notif.record, 'text', ''),
                        'root_uri': root,
                        'parent_uri': getattr(getattr(notif.record, 'reply', None), 'parent', None),
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
            log_warning(f"Bluesky fetch timed out (transient network issue).")
            _bluesky_breaker.record_failure()
        else:
            log_error(f"Failed to fetch Bluesky mentions ({error_type}): {e}")
            import traceback
            log_debug(f"Fetch failure traceback:\n{traceback.format_exc()}")
            _bluesky_breaker.record_failure()
    
    return mentions


async def _get_x_mentions() -> List[Dict[str, Any]]:
    """Fetch unread mentions from X."""
    mentions = []
    
    # Circuit breaker check
    if not _x_breaker.can_proceed():
        log_debug("X circuit breaker open - skipping fetch")
        return []
    
    try:
        from utils.social.kaia_twitter import get_x_client, is_x_configured
        from utils.infrastructure.system.yaml_config import config
        
        if not is_x_configured():
            return []
        
        client = await get_x_client()
        if not client:
            return []
        
        # Get mentions notifications
        notifs = await client.get_notifications('Mentions')
        
        from datetime import datetime, timezone, timedelta
        lookback_hours = config.get('social.mention_lookback_hours', 3)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        
        for notif in notifs:
            tweet = notif.tweet if hasattr(notif, 'tweet') else notif
            if not tweet:
                continue
                
            # Timestamp check for X (tweepy usually returns datetime objects)
            try:
                created_at = tweet.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if created_at < cutoff_time:
                    continue
            except Exception as e:
                log_warning(f"Failed to check X mention timestamp: {e}")

            mention_id = f"x:{tweet.id}"
            
            if mention_id not in _replied_ids:
                mentions.append({
                    'id': mention_id,
                    'tweet_id': tweet.id,
                    'author': tweet.user.screen_name if hasattr(tweet, 'user') else 'unknown',
                    'text': tweet.text if hasattr(tweet, 'text') else str(tweet),
                })
        
        # Record success - API is healthy
        _x_breaker.record_success()
                
    except Exception as e:
        log_error(f"Failed to fetch X mentions: {e}")
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
        
    except Exception as e:
        log_error(f"Failed to reply on Bluesky: {e}")
        return False


async def _reply_to_x(mention: Dict[str, Any], response_text: str) -> bool:
    """Reply to an X mention."""
    try:
        from utils.social.kaia_twitter import get_x_client
        
        client = await get_x_client()
        if not client:
            return False
        
        await client.create_tweet(
            response_text,
            reply_to=mention['tweet_id']
        )
        return True
        
    except Exception as e:
        log_error(f"Failed to reply on X: {e}")
        return False


async def check_and_reply_mentions(on_message_func):
    """
    Main polling function - check both platforms and reply to mentions.
    
    Call this from a periodic task loop.
    """
    global _replied_ids, _first_poll_done
    
    # log_debug("Social media poll started...")
    
    # Load replied IDs if not loaded
    if not _replied_ids:
        _load_replied_ids()
    
    from utils.infrastructure.system.yaml_config import config
    
    # SAFETY: High-integrity session safety.
    # 1. Reconstruct thread counts from real platform state (prevents loops even if storage wiped)
    # 2. Skip first poll replies (populates history only)
    if not _first_poll_done:
        log_debug("Social media poll started...")
        log_info("Initializing social safety scan (Session Start)...")
        
        # Reconstruct thread counts and replied IDs from bot's own recent activity
        await _reconstruct_bluesky_history()
        # (X reconstruction can be added when X client supports author feed fetching)
        
        await _save_replied_ids_async()
        _first_poll_done = True
        log_success("Social safety initialization complete. Thread caps and history restored.")
        # Proceed immediately to process any missed mentions
    
    # FIX: Removed duplicate _first_poll_done = True and total_replies = 0 assignments
    total_replies = 0
    
    # helper for generating response that uses the passed on_message_func
    async def generate_response_with_callback(text, author, platform):
        return await _generate_response(text, author, platform, on_message_func)
    
    # Check Bluesky
    if config.bluesky_enabled and config.get('bluesky.reply_to_mentions', True):
        mentions = await _get_bluesky_mentions()
        
        for mention in mentions[:3]:  # Limit to 3 per poll to avoid rate limits
            author = mention['author']
            text = mention['text']
            
            # ANTI-BOT LOOP PROTECTION
            bot_keywords = ["bot", "agent", "ai", "automated"]
            admin_handles = config.get('social.admin_handles', [])
            is_admin = author in admin_handles
            
            if not is_admin and any(k in author.lower() for k in bot_keywords):
                # Thread tracking: root_uri is the anchor
                root = mention.get('root_uri')
                root_uri = root.uri if root and hasattr(root, 'uri') else mention['uri']
                
                # Check how many times we've replied to THIS thread
                if _thread_counts.get(root_uri, 0) >= 1: 
                     log_warning(f"Suspected bot author @{author} in thread {root_uri[:30]}. Skipping subsequent reply.")
                     continue

            log_info(f"Bluesky mention from @{author}: {text[:50]}...")
            
            response = await generate_response_with_callback(text, author, "bluesky")
            if response:
                success = await _reply_to_bluesky(mention, response)
                if success:
                    async with _replied_ids_lock:
                        _replied_ids.add(mention['id'])
                        
                        # Increment thread count for Bluesky
                        root = mention.get('root_uri')
                        root_uri = root.uri if root and hasattr(root, 'uri') else mention['uri']
                        _thread_counts[root_uri] = _thread_counts.get(root_uri, 0) + 1
                        
                    log_success(f"Replied to @{author} on Bluesky (Thread count: {_thread_counts[root_uri]}): {response[:50]}...")
                    await _save_replied_ids_async()  # Async persistence
                    total_replies += 1
    
    # Check X
    if config.x_enabled and config.get('x_twitter.reply_to_mentions', True):
        mentions = await _get_x_mentions()
        
        for mention in mentions[:3]:  # Limit to 3 per poll
            author = mention['author']
            text = mention['text']
            
            log_info(f"X mention from @{author}: {text[:50]}...")
            
            response = await generate_response_with_callback(text, author, "x")
            if response:
                success = await _reply_to_x(mention, response)
                if success:
                    async with _replied_ids_lock:
                        _replied_ids.add(mention['id'])
                    log_success(f"Replied to @{author} on X: {response[:50]}...")
                    await _save_replied_ids_async()  # Async persistence
                    total_replies += 1
    
    if total_replies > 0:
        log_info(f"Social media polling complete: {total_replies} replies sent")
    
    return total_replies


async def mock_external_mention(on_message_func, content: str, author_name: str, author_id: Any, platform: str):
    """Mock a Discord message for social platform mentions to pipe through the main engine."""
    import uuid
    from contextlib import asynccontextmanager

    log_info(f"Mocking {platform} message from {author_name}...")

    class MockChannel:
        def __init__(self):
            # Stable int hash for channel ID ensures memory persistence across runs
            self.id = abs(hash(f"{platform}_{author_id}")) % 10**12
            self.name = f"{platform}_mentions"
            self.sent_messages = []
        async def send(self, content=None, **kwargs):
            if content: self.sent_messages.append(content)
            return type('obj', (object,), {'id': 123})() 
        
        @asynccontextmanager
        async def typing(self):
            yield

    class MockAuthor:
        def __init__(self):
            self.id = author_id
            self.name = author_name
            self.display_name = author_name
            self.bot = False

    class MockMessage:
        def __init__(self):
            self.content = content
            self.author = MockAuthor()
            self.channel = MockChannel()
            self.attachments = []
            self.embeds = []
            self.platform = platform
            self.id = uuid.uuid4().int >> 64
            self.guild = None
            self.reference = None
            self.mentions = []
        async def reply(self, content=None, **kwargs):
            return await self.channel.send(content, **kwargs)

    msg = MockMessage()
    await on_message_func(msg)
    
    if msg.channel.sent_messages:
        full_response = "\n".join(msg.channel.sent_messages)
        return full_response.replace("```\n", "").replace("```", "").strip()
    return None


async def get_random_memories(limit=20):
    """Get random interaction snippets from any user log in the knowledge base."""
    import os
    import random
    from pathlib import Path
    
    memories = []
    # Use absolute path resolution relative to project root
    project_root = Path(__file__).parent.parent.parent
    base_dir = project_root / "knowledge_base" / "user_logs"
    
    if not base_dir.exists():
        return []
        
    # 1. Gather all interaction files
    all_files = list(base_dir.rglob("interactions_*.txt"))
    if not all_files:
        return []
        
    # 2. Sample random files to avoid reading the whole disk
    sample_size = min(15, len(all_files))
    sampled_files = random.sample(all_files, sample_size)
    
    for log_file in sampled_files:
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # Pick a random chunk of lines from the file
                if len(lines) > 20:
                    start = random.randint(0, len(lines) - 20)
                    chunk = lines[start:start+20]
                else:
                    chunk = lines
                    
                for line in chunk:
                    # Capture both Kaia and User messages
                    if "Kaia:" in line or "User:" in line:
                        is_kaia = "Kaia:" in line
                        prefix = "Kaia:" if is_kaia else "User:"
                        parts = line.split(prefix, 1)
                        if len(parts) >= 2:
                            msg = parts[1].strip()
                            if 20 < len(msg) < 400:
                                # Skip technical/boring noise
                                if any(skip in msg.lower() for skip in ["[vision]", "[idle", "hello", "error:"]):
                                    continue
                                memories.append({
                                    "text": msg,
                                    "type": "said" if is_kaia else "heard"
                                })
        except Exception:
            continue
            
    random.shuffle(memories)
    return memories[:limit]

async def get_random_dream_reflection(limit=5):
    """Pick a random dream file and extract Kaia's Reflection."""
    import os
    import random
    from pathlib import Path
    
    reflections = []
    # Use absolute path resolution relative to project root
    project_root = Path(__file__).parent.parent.parent
    base_dir = project_root / "knowledge_base" / "kaia_dreams"
    
    if not base_dir.exists():
        return []
        
    # Gather all dream files recursively
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
                    # Clean up markdown blockquotes if present
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
            
    random.shuffle(reflections)
    return reflections[:limit]

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

def clean_quip(quip_text: str, max_chars: int = 270) -> str:
    """Clean up generated quips with minimal intervention - persona handles the rest.
    
    Centralized hardening in BotSpeakFilter handles the meta-talk and hallucinations.
    """
    # Remove roleplay markers
    clean_text = re.sub(r'\*.*?\*', '', quip_text)
    clean_text = re.sub(r'\(.*?\)', '', clean_text)
    
    # Standardize spaces and remove newlines
    clean_text = clean_text.replace('\n', ' ')
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # Apply persona's lowercase rule
    clean_text = clean_text.lower()
    
    # Remove quotes
    clean_text = clean_text.replace('"', '').replace("'", "")
    
    return clean_text

async def generate_quip(bot, ollama_client, run_rag_func, rag_instance, is_manual=False, target_channel=None, on_message_func=None):
    """Generate social posts by piping through the FULL Kaia engine.
    
    This ensures quips use the complete persona, RAG, and personalization pipeline
    rather than a truncated custom prompt.
    """
    import time
    import random
    from utils.infrastructure.system.bot_state import bot_state
    from utils.infrastructure.system.yaml_config import config

    if not is_manual:
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
        log_action(f"Generating quip via main engine in #{channel.name}...")
        
        # 1. MINE DREAMS AND MEMORIES for reflection context
        dreams = await get_random_dream_reflection(limit=5)
        memories = await get_random_memories(limit=10)
        
        reflection_target = None
        context_type = None
        
        # 2. DECIDE REFLECTION TARGET (70% dream/news, 30% memory/chat)
        reflection_target = None
        context_type = None
        
        if dreams and random.random() < 0.70:
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = f"recent news about {dream.get('category', 'something')}"
        elif memories:
            memory = random.choice(memories)
            reflection_target = memory["text"]
            context_type = "something someone said" if memory["type"] == "heard" else "something I said before"
        elif dreams:
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = f"recent news about {dream.get('category', 'something')}"
        
        # QUALITY CHECK: Use concrete fallbacks if target is too thin
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

        # 2. DEFINE LENGTH GUIDANCE (Moved up for prompt construction)
        # Add LENGTH VARIANCE - sometimes short, sometimes thread-worthy
        # 40% short (single skeet), 40% medium (may be 2 posts), 20% long (thread)
        length_roll = random.random()
        
        # STANDALONE REQUIREMENT: Output must be complete thought
        standalone_req = "Your output must be a COMPLETE, STANDALONE thought that makes sense on its own. Don't reference 'this' or reply to the spark text. Write something that would make sense to someone who has no idea what prompted it."
        
        if length_roll < 0.40:
            # Short - punchy single post, but still grounded
            length_mode = "short"
            length_guidance = f" Keep it brief - one or two punchy sentences, under 280 characters. {standalone_req}"
            max_quip_chars = 300
        elif length_roll < 0.80:
            # Medium - might thread
            length_mode = "medium"
            length_guidance = f" Give me a few sentences, like a social media post. {standalone_req}"
            max_quip_chars = 600
        else:
            # Long - go off, make a thread
            length_mode = "long"
            length_guidance = f" Really dig into this one. Give me your full take - multiple paragraphs if you want. This could be a whole thread. {standalone_req}"
            max_quip_chars = 900  # ~3 posts worth

        # 3. BUILD DIRECT STANDALONE PROMPTS
        # These strictly forbid "replying" to the context
        system_prompt = load_persona()
        
        # --- RAG INTEGRATION START ---
        # Search for related context to inform the opinion (e.g. knowing about Deus Ex endings)
        try:
            search_query = ""
            if "news about" in context_type:
                search_query = context_type.replace("recent news about ", "")
            else:
                # Use the first 10 words of the reflection as the search query
                search_query = " ".join(reflection_target.split()[:10])
                
            if rag_instance and search_query:
                log_action(f"Contextualizing quip with RAG search for: '{search_query}'")
                # Use a broader search to get general knowledge + logs
                rag_results = rag_instance.retrieve(search_query, top_k=3, category="general")
                
                if rag_results:
                    rag_block = "\n\n### RELEVANT KNOWLEDGE & MEMORIES\n"
                    for node in rag_results:
                        # Handle NodeWithScore object vs direct node
                        content = node.node.get_content() if hasattr(node, 'node') else node.get_content()
                        rag_block += f"- {content[:400].replace(chr(10), ' ')}...\n"
                    
                    system_prompt += rag_block
                    log_success(f"Injected {len(rag_results)} RAG snippets into quip prompt.")
        except Exception as rag_err:
            log_warning(f"Failed to inject RAG context for quip: {rag_err}")
        # --- RAG INTEGRATION END ---

        standalone_prompts = [
            f"Context (for inspiration only, do not reply to this): {reflection_target}\n"
            f"Task: Write a standalone social media post. DO NOT reference this context directly.\n"
            f"Length: {length_guidance}\n"
            f"Important: No questions, no 'this made me think', no 'what prompted this'. Start with your thought, not a reaction.",
            
            f"You're writing a social media post. Something about '{context_type}' made you think.\n"
            f"Inspiration: \"{reflection_target}\"\n"
            f"Write a complete thought that stands on its own. No lead-ins, no questions, no references to context.\n"
            f"Just your take. {length_guidance}",
            
            f"Social media post. Be blunt. Complete thought.\n"
            f"Inspiration: {reflection_target[:200]}...\n"
            f"Rules: No 'this reminded me', no 'someone said', no questions, no meta-talk.\n"
            f"{length_guidance}"
        ]
        
        final_prompt = random.choice(standalone_prompts)
        log_debug(f"Quip length mode: {length_mode} (max {max_quip_chars} chars)")
        
        # 4. GENERATE A STANDALONE STATEMENT (not a reply)
        # We bypass the conversation engine to ensure it's a statement, not a reply
        log_action(f"Generating persona-driven {length_mode} quip...")
        response = await ollama_client.chat(
            model=config.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_prompt}
            ],
            options={
                'temperature': 0.85,
                'top_p': 0.95,
                'num_predict': 500,
                'presence_penalty': 0.6,
                'frequency_penalty': 0.5
            }
        )
        quip = response['message']['content'].strip()
        
        if not quip:
            log_warning("Main engine returned empty quip.")
            return
            
        # 5. CLEAN UP and HARDEN
        quip = clean_quip(quip, max_chars=max_quip_chars)
        
        # Apply strict hardening filter
        harden = BotSpeakFilter()
        quip = harden.strip_bot_speak(quip)
        
        # Ensure it's not a hallucination or refusal
        if not quip or "too much entropy" in quip:
            log_warning("Quip failed hardening or hallucination check.")
            return
            
        # Remove any leading artifacts
        quip = quip.strip()
        for prefix in ["kaia:", "kaia says:", "response:"]:
            if quip.lower().startswith(prefix):
                quip = quip[len(prefix):].strip()
        
        # Ensure lowercase (persona style)
        if quip and quip[0].isupper():
            quip = quip[0].lower() + quip[1:]
        
        # Cap sanity check (uses dynamic limit from length mode)
        if len(quip) > max_quip_chars:
            log_warning(f"Quip too long ({len(quip)} chars), truncating to {max_quip_chars}...")
            sentences = quip.split('. ')
            truncated = ""
            for s in sentences:
                candidate = (truncated + ". " + s).strip() if truncated else s.strip()
                if len(candidate) <= max_quip_chars - 20:
                    truncated = candidate
                else:
                    break
            quip = truncated
            if quip and not quip.endswith('.'): quip += '.'
            if len(quip) > max_quip_chars:
                quip = quip[:max_quip_chars-3] + "..."

        # 5. POST to Discord and cross-post
        await channel.send(f"```\n{quip}\n```")

        # Cross-post if enabled
        if config.bluesky_cross_post_quips:
            try:
                from utils.social.kaia_bluesky import (
                    post_quip_to_bluesky, 
                    needs_thread_expansion, 
                    post_thread_to_bluesky,
                    _split_into_thread
                )
                
                # Check if this would create an awkwardly short second post
                needs_expansion, short_remainder = needs_thread_expansion(quip, min_second_chunk=100)
                
                if needs_expansion and on_message_func:
                    log_info(f"Thread final post too short ({len(short_remainder)} chars), expanding...")
                    
                    # Prepare the chunks for the thread
                    chunks = _split_into_thread(quip, max_chars=300)
                    if not chunks:
                        await post_quip_to_bluesky(quip)
                        return

                    # Context for expansion: everything before the last chunk
                    # If it's a 2-chunk thread, this is just chunks[0]
                    # If it's a 3+ chunk thread, join the leading chunks for context
                    context_parts = chunks[:-1]
                    first_part = " ".join(context_parts)
                    if len(first_part) > 1000: # Context safety cap
                        first_part = "..." + first_part[-1000:]
                    
                    # Ask Kaia to expand on the short remainder
                    expansion_prompt = (
                        f"kaia, you just said this: \"{first_part}\" "
                        f"and you were about to add \"{short_remainder}\" but that's too short. "
                        f"expand on that last thought - explain what you mean or add another observation. "
                        f"give me just the continuation, about 2-3 sentences, under 280 characters."
                    )
                    
                    expanded = await mock_external_mention(
                        on_message_func=on_message_func,
                        content=expansion_prompt,
                        author_name="Kaia",
                        author_id=bot.user.id if bot.user else "kaia_self",
                        platform="thread_expansion"
                    )
                    
                    if expanded and len(expanded) > len(short_remainder):
                        # Clean up the expansion
                        expanded = expanded.strip()
                        for prefix in ["kaia:", "kaia says:", "response:", "continuation:"]:
                            if expanded.lower().startswith(prefix):
                                expanded = expanded[len(prefix):].strip()
                        
                        # Ensure lowercase persona style
                        if expanded and expanded[0].isupper():
                            expanded = expanded[0].lower() + expanded[1:]
                        
                        # Cap at 300 for the final post
                        if len(expanded) > 300:
                            expanded = expanded[:297] + "..."
                        
                        # Final thread: chunks minus the short remainder, plus the expanded version
                        final_thread_chunks = context_parts + [expanded]
                        log_success(f"Expanded thread into {len(final_thread_chunks)} posts. Continuation: {expanded[:50]}...")
                        await post_thread_to_bluesky(final_thread_chunks)
                    else:
                        # Expansion failed, just post normally
                        log_warning("Thread expansion failed, posting original chunks")
                        await post_quip_to_bluesky(quip)
                else:
                    # Normal case - no expansion needed
                    await post_quip_to_bluesky(quip)
                    
            except Exception as e:
                log_error(f"Bluesky post failed: {e}")
        
        if config.x_cross_post_quips:
            try:
                from utils.social.kaia_twitter import post_quip_to_x
                await post_quip_to_x(quip)
            except Exception as e:
                log_error(f"X post failed: {e}")
        
        # 6. LOG the quip to Kaia's user log
        if bot and hasattr(bot, 'user') and bot.user:
            try:
                # Use real name or fallback
                user_id = getattr(bot.user, 'id', 0)
                user_name = getattr(bot.user, 'name', 'kaia')
                
                trigger = "[MANUAL_QUIP]" if is_manual else "[IDLE_REFLECTION]"
                rag_instance.log_user_interaction(
                    user_id=user_id,
                    user_name=user_name,
                    message_content=trigger,
                    bot_response=quip
                )
            except Exception as log_err:
                log_warning(f"Failed to log quip interaction: {log_err}")

        # 7. UPDATE state
        bot_state.add_quip(quip)
        if not is_manual:
            bot_state.consecutive_quips += 1
            bot_state.last_quip_time = time.time()
            # Don't update last_interaction_time for forced posts to allow normal idle logic to resume?
            # actually we should, so we don't double post.
            bot_state.last_interaction_time = time.time()
        bot_state.save()
        log_success(f"Quip sent: {quip[:80]}...")

    except Exception as e:
        log_error(f"Quip generation failed: {e}")
        import traceback
        log_debug(traceback.format_exc())

