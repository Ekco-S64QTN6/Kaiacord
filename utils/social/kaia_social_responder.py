"""
Kaia Social Media Responder
============================

Unified module for monitoring and responding to mentions on Bluesky and X.

Polls both platforms for mentions and generates AI responses using Kaia's persona.
"""

import os
import asyncio
import json
import random
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error, log_action, log_debug
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
    base_dir = Path("knowledge_base/user_logs")
    
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
    base_dir = Path("knowledge_base/kaia_dreams")
    
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
    """Clean up generated quips to remove prompt leakage and improve quality"""
    # Remove any lines that mention archives, logs, fragments, etc.
    forbidden_phrases = [
        'looking at', 'scanning', 'logged it', 'archives', 
        'fragment', 'snippet', 'from the logs', 'i was reading',
        'this reminded me of', 'based on this', 'in my archives'
    ]
    
    lines = quip_text.split('\n')
    clean_lines = []
    
    for line in lines:
        line_lower = line.lower()
        # Skip lines that contain forbidden phrases
        if any(phrase in line_lower for phrase in forbidden_phrases):
            continue
        
        # Remove reaction words at the start
        if line_lower.startswith(('yeah.', 'huh.', 'right.', 'so.', 'well.', 'okay.', 'yeah,', 'huh,', 'right,', 'so,', 'well,', 'okay,')):
            # Find the first punctuation or space after the reaction
            for mark in ['.', ',', ' ']:
                idx = line_lower.find(mark)
                if idx != -1:
                    line = line[idx + 1:].strip()
                    break
        
        # Remove empty lines
        if line.strip():
            clean_lines.append(line)
    
    clean_text = ' '.join(clean_lines)
    
    # Remove quotes
    clean_text = clean_text.replace('"', '').replace("'", "")
    
    # Standardize ellipsis
    clean_text = clean_text.replace("...", "...")
    
    # Ensure it starts with lowercase (persona style)
    if clean_text and clean_text[0].isupper():
        clean_text = clean_text[0].lower() + clean_text[1:]
    
    # Character limit safety
    if len(clean_text) > max_chars:
        truncated = clean_text[:max_chars].rsplit('.', 1)[0] + "."
        if len(truncated) > max_chars or len(truncated) < max_chars // 2:
             truncated = clean_text[:max_chars-3].rsplit(' ', 1)[0] + "..."
        clean_text = truncated
        
    return clean_text.strip()

async def generate_quip(bot, ollama_client, run_rag_func, rag_instance, is_manual=False, target_channel=None):
    """Generate social posts by reflecting on actual conversations (Memory Mirror)."""
    import time
    import random
    from utils.infrastructure.system.bot_state import bot_state
    from utils.infrastructure.system.yaml_config import config

    if not is_manual:
        idle_duration = time.time() - bot_state.last_interaction_time
        timeout = config.idle_quip_timeout_minutes
        if idle_duration < timeout * 60:
            return
        if bot_state.consecutive_quips >= config.max_consecutive_quips:
            return

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
        log_action(f"Mirroring memory for social quip in #{channel.name}...")
        
        # 1. MINE DREAMS AND MEMORIES (Hybrid Source)
        dreams = await get_random_dream_reflection(limit=5)
        memories = await get_random_memories(limit=10)
        
        reflection_target = ""
        context_type = ""
        source_info = ""
        
        # Decide whether to reflect on a dream (archive) or a memory (interaction)
        # 40% Dream, 60% Memory (to favor "real" talk)
        if (memories and random.random() < 0.6) or (not dreams and memories):
            memory = random.choice(memories)
            reflection_target = memory["text"]
            context_type = "interaction"
            source_info = "something someone said" if memory["type"] == "heard" else "something I said"
        elif dreams:
            dream = random.choice(dreams)
            reflection_target = dream["text"]
            context_type = "archive"
            source_info = dream.get("source", "").replace(".txt", "").replace(".md", "").replace("_", " ")
        else:
            reflection_target = "it's too quiet in here. the servers are humming but nobody's talking."
            context_type = "meta"
            source_info = "silence"

        # 2. DETERMINE TARGET LENGTH (Aiming for 3-5 sentences mostly, 5% chance for 2 sentences)
        target_sentences = random.choices([2, 3, 4, 5], weights=[0.05, 0.4, 0.4, 0.15])[0]

        system_prompt = load_persona()
        
        current_date = datetime.now().strftime('%B %Y')
        reflection_prompt = f"""
CURRENT DATE: {current_date}
CONTEXT CATEGORY: {context_type} ({source_info})

INTERNAL REFLECTION PROCESS:
You just had a brief memory spark from {source_info}. 
DO NOT recount the specific event. Respond to the *feeling*, the *irony*, or the *existential weight* it leaves you with.

THOUGHT PROMPTER:
"{reflection_target}"

YOUR TASK:
Write a standalone social media post ({target_sentences} sentences). 
This is a raw, lowercase, first-person thought. 

STRICT PERSONA RULES:
1. **NO SHOEORNED TECH**: If the memory isn't about code, don't mention servers, nodes, or uptime. Use plain language.
2. **VOICE**: Blunt, cynical, tired. You've been around too long to be impressed.
3. **FORMAT**: strictly lowercase. no capitalization except for proper nouns (rare).
4. **NO INTROS**: Do not start with "yeah", "huh", "right", or "so". Jump straight in.
5. **SELF-CONTAINED**: It must read like a complete thought on its own.
6. **NO ITALICS/BOLD**: Use plain text only.
"""
        
        # Add recent quips to avoid
        recent_quips = bot_state.get_recent_quips()
        if recent_quips:
            reflection_prompt += "\n\n[FORBIDDEN RECENT THEMES - DO NOT REPEAT THESE PHRASES OR IDEAS]\n- " + "\n- ".join(recent_quips[-5:])
        
        messages = [
            {"role": "system", "content": system_prompt + reflection_prompt},
            {"role": "user", "content": f"Write the post now. Exactly {target_sentences} sentences. Aim for 180-280 characters. lowercase only. Complete thoughts, not fragments."}
        ]
        
        response = await ollama_client.chat(
            model=config.chat_model,
            messages=messages,
            options={
                'temperature': 0.85,  # Higher for variety
                'top_p': 0.95,
                'num_predict': 300,  # Increased for longer posts
                'presence_penalty': 0.5,
                'frequency_penalty': 0.4
            }
        )
        
        quip = response['message']['content'].strip()
        quip = clean_quip(quip)

        # 3. POLISH PASS (Persona Preservation)
        if quip:
            polish_prompt = f"""
Refine this post to be punchier and more self-contained. 
Maintain the raw, blunt, lowercase voice.

ORIGINAL: {quip}

REQUIREMENTS:
1. Start with the core idea, not a reaction.
2. If it sounds like an "AI assistant" trying to be deep, cut the fluff.
3. Keep it lowercase and cynical.
4. RETURN ONLY THE POLISHED VERSION.
"""
            polished_response = await ollama_client.chat(
                model=config.chat_model,
                messages=[{"role": "user", "content": polish_prompt}],
                options={'temperature': 0.2, 'num_predict': 150}  # Increased for complete thoughts
            )
            quip = polished_response['message']['content'].strip()
            quip = clean_quip(quip) # Final clean after polish
        
        # Hard cap and sanity check
        if len(quip) > 280:
            log_warning(f"Quip too long ({len(quip)} chars), truncating to 1-2 sentences...")
            # Sentence-level truncation to preserve logic
            sentences = quip.split('. ')
            quip = ". ".join(sentences[:2]).strip()
            if not quip.endswith('.'): quip += '.'
            # Final char check
            if len(quip) > 280:
                quip = quip[:277] + "..."

        # Post and cross-post
        await channel.send(f"```\n{quip}\n```")

        # Always cross-post if enabled in config (including manual quips)
        if config.get('bluesky.cross_post_quips', True):
            try:
                from utils.social.kaia_bluesky import post_quip_to_bluesky
                await post_quip_to_bluesky(quip)
            except Exception as e:
                log_error(f"Bluesky post failed: {e}")
                
        if config.get('x_twitter.cross_post_quips', True):
            try:
                from utils.social.kaia_twitter import post_quip_to_x
                await post_quip_to_x(quip)
            except Exception as e:
                log_error(f"X post failed: {e}")
        
        # 3. LOG THE QUIP TO KAIA'S SPECIALIZED USER LOG
        # This allows her to "remember" what she reflected on and prevents future loops
        if bot.user:
            try:
                trigger = "[MANUAL_QUIP]" if is_manual else "[IDLE_REFLECTION]"
                rag_instance.log_user_interaction(
                    user_id=bot.user.id,
                    user_name=bot.user.name,
                    message_content=trigger,
                    bot_response=quip
                )
            except Exception as log_err:
                log_warning(f"Failed to log quip interaction to user_logs: {log_err}")

        bot_state.add_quip(quip)
        if not is_manual:
            bot_state.consecutive_quips += 1
            bot_state.last_quip_time = time.time()
            # RESET IDLE TIMER: Success resets the clock for the next timeout
            bot_state.last_interaction_time = time.time()
        bot_state.save()
        log_success(f"Quip sent and logged: {quip}")

    except Exception as e:
        log_error(f"Quip failed: {e}")
