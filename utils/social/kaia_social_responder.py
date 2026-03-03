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


# ── Extracted Platform Polling (Phase 28 / CQ-01) ────────────────────────
from utils.social.social_bluesky_polling import (              # noqa: F401
    _reconstruct_bluesky_history,
    _get_bluesky_mentions,
    _reply_to_bluesky,
    _bluesky_breaker,
)
from utils.social.social_twitter_polling import (              # noqa: F401
    _reconstruct_x_history,
    _get_x_mentions,
    _reply_to_x,
    _x_breaker,
)


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
            tasks.append(_reconstruct_bluesky_history(_silenced_replied_ids))
        else:
            log_debug("Bluesky disabled - skipping history reconstruction.")
            
        if config.x_enabled:
            tasks.append(_reconstruct_x_history(_silenced_replied_ids))
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
        mentions = await _get_bluesky_mentions(_silenced_replied_ids, _save_replied_ids_async)
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
        mentions = await _get_x_mentions(_silenced_replied_ids)
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


