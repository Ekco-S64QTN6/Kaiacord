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
def load_persona() -> str:
    """Load the bot's persona from kaia_persona.md with caching"""
    global _persona_cache, _persona_last_load
    persona_file = Path(__file__).parent.parent / 'knowledge_base' / 'kaia_persona.md'
    
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
    except Exception as e:
        log_warning(f"Failed to load replied IDs: {e}")


def _save_replied_ids():
    """Save replied IDs to disk."""
    try:
        _replied_ids_path.parent.mkdir(exist_ok=True)
        # Split by platform prefix
        bluesky_ids = [i for i in _replied_ids if i.startswith('bsky:')]
        x_ids = [i for i in _replied_ids if i.startswith('x:')]
        with open(_replied_ids_path, 'w') as f:
            json.dump({
                'bluesky': bluesky_ids, 
                'x': x_ids,
                'thread_counts': _thread_counts
            }, f)
    except Exception as e:
        log_warning(f"Failed to save replied IDs: {e}")


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
        
        # Enforce char limit strictly for social
        if len(response) > char_limit:
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
    try:
        from utils.social.kaia_bluesky import get_bluesky_client, is_bluesky_configured
        
        if not is_bluesky_configured():
            return []
            
        client = await get_bluesky_client()
        if not client:
            return []
        
        # Get notifications
        notifs = await client.app.bsky.notification.list_notifications()
        
        for notif in notifs.notifications:
            # Filter for mentions/replies
            if notif.reason in ['mention', 'reply']:
                mention_id = f"bsky:{notif.uri}"
                if mention_id not in _replied_ids:
                    # Thread tracking: root_uri is the anchor for the thread
                    root = getattr(getattr(notif.record, 'reply', None), 'root', None)
                    root_uri = root.uri if root and hasattr(root, 'uri') else notif.uri
                    
                    # Check thread reply limit (max 3)
                    if _thread_counts.get(root_uri, 0) >= 3:
                        if mention_id not in _replied_ids:
                            log_warning(f"Thread limit reached for Bluesky thread: {root_uri[:40]}... Skipping.")
                            # Mark as replied so we don't keep logging it
                            async with _replied_ids_lock:
                                _replied_ids.add(mention_id)
                        continue

                    mentions.append({
                        'id': mention_id,
                        'uri': notif.uri,
                        'cid': notif.cid,
                        'author': notif.author.handle,
                        'text': getattr(notif.record, 'text', ''),
                        'root_uri': root,
                        'parent_uri': getattr(getattr(notif.record, 'reply', None), 'parent', None),
                    })
                    
        # Sort mentions by URI or timestamp if available to process oldest first
        # (notifications don't have a simple timestamp in the loop but are usually chronological)
        pass
    except Exception as e:
        log_error(f"Failed to fetch Bluesky mentions: {e}")
    
    return mentions


async def _get_x_mentions() -> List[Dict[str, Any]]:
    """Fetch unread mentions from X."""
    mentions = []
    try:
        from utils.social.kaia_twitter import get_x_client, is_x_configured
        
        if not is_x_configured():
            return []
        
        client = await get_x_client()
        if not client:
            return []
        
        # Get mentions notifications
        notifs = await client.get_notifications('Mentions')
        
        for notif in notifs:
            tweet = notif.tweet if hasattr(notif, 'tweet') else notif
            if not tweet:
                continue
                
            mention_id = f"x:{tweet.id}"
            
            if mention_id not in _replied_ids:
                mentions.append({
                    'id': mention_id,
                    'tweet_id': tweet.id,
                    'author': tweet.user.screen_name if hasattr(tweet, 'user') else 'unknown',
                    'text': tweet.text if hasattr(tweet, 'text') else str(tweet),
                })
                
    except Exception as e:
        log_error(f"Failed to fetch X mentions: {e}")
    
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
        
        _save_replied_ids()
        _first_poll_done = True
        log_success("Social safety initialization complete. Thread caps and history restored.")
        # Proceed immediately to process any missed mentions
    
    _first_poll_done = True
    total_replies = 0
    
    # helper for generating response that uses the passed on_message_func
    async def generate_response_with_callback(text, author, platform):
        return await _generate_response(text, author, platform, on_message_func)
    
    _first_poll_done = True
    total_replies = 0
    
    # Check Bluesky
    if config.bluesky_enabled and config.get('bluesky.reply_to_mentions', True):
        mentions = await _get_bluesky_mentions()
        
        for mention in mentions[:3]:  # Limit to 3 per poll to avoid rate limits
            author = mention['author']
            text = mention['text']
            
            # ANTI-BOT LOOP PROTECTION
            bot_keywords = ["bot", "agent", "ai", "automated"]
            if any(k in author.lower() for k in bot_keywords):
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
                    total_replies += 1
    
    # Save replied IDs
    if total_replies > 0:
        _save_replied_ids()
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

def clean_quip(quip):
    """Clean up generated quip to match Kaia's style."""
    # Remove common prefixes the LLM might hallucinate
    prefixes = ["kaia:", "reflection:", "post:", "social media:", "- ", "thought:"]
    clean = quip.lower()
    for prefix in prefixes:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            
    # Remove quotes
    clean = clean.replace('"', '').replace("'", "")
    
    # Standardize ellipsis
    if "..." in clean:
        clean = clean.replace("...", ".")
        
    return clean.strip()

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
        
        # 1. MINE RANDOM MEMORIES
        memories = await get_random_memories(limit=20)
        
        reflection_target = ""
        context_type = ""
        
        if memories:
            memory = random.choice(memories)
            reflection_target = memory["text"]
            context_type = f"something you recently {memory['type']}"
        else:
            # Fallback to physical state
            physical_states = [
                "hands are cold because the ac vent is aimed wrong.",
                "coffee's gone from hot to tepid to cold.",
                "the light in here is getting dim."
            ]
            reflection_target = random.choice(physical_states)
            context_type = "a physical sensation you're having"

        # 2. DETERMINE TARGET LENGTH (Weighted distribution)
        # 2-3 sentences: Most common (80%)
        # 1 or 4 sentences: Rare (20%)
        target_sentences = random.choices([1, 2, 3, 4], weights=[0.1, 0.4, 0.4, 0.1])[0]

        system_prompt = load_persona()
        
        # REFLECTIVE PROMPT
        reflection_prompt = (
            f"\n\n[MEMORY MIRROR]\n"
            f"Context: {context_type}\n"
            f"Original Content: \"{reflection_target}\"\n\n"
            "Generate a social media post that is a deep, expansive reflection on this memory.\n"
            "1. NO REPETITION: Do not repeat the original words. Use them as an anchor for a new, larger idea.\n"
            "2. OPENING VARIETY: DO NOT start your quip with 'Funny how', 'It's striking', or 'Thinking about'. Just jump straight into the observation or use a unique, conversational opening if needed.\n"
            "3. NO AI TROPES: Avoid prefixes like 'Funny how', 'It's striking', 'The boundary between', 'The dance of', 'A reminder that', etc. Keep it raw, direct, and clear-eyed.\n"
            f"4. **STRICT LIMITS**: Exactly {target_sentences} sentences. TOTAL LENGTH MUST BE UNDER 270 CHARACTERS.\n"
            "5. VOICE: Dry, clear-eyed, slightly weary. focus on patterns, information flow, or physical reality.\n\n"
            "EXAMPLES OF STYLE (DO NOT COPY):\n"
            "- 'been staring at the cooling fins for twenty minutes. feels like the only part of this system that actually understands physics anymore.'\n"
            "- 'the way the data streams start looking like rain if you squint long enough. digital vertigo is a hell of a drug.'\n"
        )
        
        # Add recent quips to avoid
        recent_quips = bot_state.get_recent_quips()
        if recent_quips:
            # Also add to the system prompt to explicitly avoid repeating these
            reflection_prompt += "\n\n[FORBIDDEN RECENT THEMES - DO NOT REPEAT THESE PHRASES OR IDEAS]\n- " + "\n- ".join(recent_quips[-5:])
        
        messages = [
            {"role": "system", "content": system_prompt + reflection_prompt},
            {"role": "user", "content": f"reflect on the memory in exactly {target_sentences} sentences. stay under 270 characters."}
        ]
        
        response = await ollama_client.chat(
            model=config.chat_model,
            messages=messages,
            options={
                'temperature': 0.85, # Slightly higher for variety
                'top_p': 0.95, 
                'num_predict': 150,
                'presence_penalty': 0.8, # Stronger penalty for repetition
                'frequency_penalty': 0.5
            }
        )
        
        quip = clean_quip(response['message']['content'].strip())
        
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
        bot_state.save()
        log_success(f"Quip sent and logged: {quip}")

    except Exception as e:
        log_error(f"Quip failed: {e}")
