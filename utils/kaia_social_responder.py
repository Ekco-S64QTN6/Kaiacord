"""
Kaia Social Media Responder
============================

Unified module for monitoring and responding to mentions on Bluesky and X.

Polls both platforms for mentions and generates AI responses using Kaia's persona.
"""

import os
import asyncio
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from utils.kaia_logger import log_info, log_success, log_warning, log_error, log_action

# Replied mentions tracker (persisted to disk)
_replied_ids_path = Path("storage/social_replied_ids.json")
_replied_ids: set = set()
_replied_ids_lock = asyncio.Lock()


def _load_replied_ids():
    """Load set of already-replied mention IDs from disk."""
    global _replied_ids
    try:
        if _replied_ids_path.exists():
            with open(_replied_ids_path, 'r') as f:
                data = json.load(f)
                _replied_ids = set(data.get('bluesky', []) + data.get('x', []))
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
            json.dump({'bluesky': bluesky_ids, 'x': x_ids}, f)
    except Exception as e:
        log_warning(f"Failed to save replied IDs: {e}")


def _get_persona() -> str:
    """Load Kaia's persona for response generation."""
    persona_file = Path("knowledge_base/kaia_persona.md")
    try:
        if persona_file.exists():
            return persona_file.read_text().strip()
    except:
        pass
    return "You are Kaia, a blunt and grounded AI. Keep responses short and authentic."


async def _generate_response(mention_text: str, author_name: str, platform: str) -> Optional[str]:
    """Generate a response using Ollama chat model."""
    try:
        import ollama
        from bot.managers.yaml_config import config
        
        persona = _get_persona()
        
        # Platform-specific character limits
        char_limit = 300 if platform == "bluesky" else 280
        
        system_prompt = f"""{persona}

You are responding to a mention on {platform.upper()}.
Keep your response under {char_limit} characters.
Be conversational, witty, and authentic to your personality.
Don't use hashtags or emojis excessively.
Respond directly to what they said."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"@{author_name} said: {mention_text}"}
        ]
        
        client = ollama.AsyncClient()
        response = await client.chat(
            model=config.chat_model,
            messages=messages,
            options={
                "temperature": 0.8,
                "num_predict": 150,
            }
        )
        
        reply_text = response['message']['content'].strip()
        
        # Enforce character limit
        if len(reply_text) > char_limit:
            reply_text = reply_text[:char_limit-3] + "..."
        
        return reply_text
        
    except Exception as e:
        log_error(f"Failed to generate social response: {e}")
        return None


async def _get_bluesky_mentions() -> List[Dict[str, Any]]:
    """Fetch unread mentions from Bluesky."""
    mentions = []
    try:
        from utils.kaia_bluesky import get_bluesky_client, is_bluesky_configured
        
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
                    mentions.append({
                        'id': mention_id,
                        'uri': notif.uri,
                        'cid': notif.cid,
                        'author': notif.author.handle,
                        'text': getattr(notif.record, 'text', ''),
                        'root_uri': getattr(getattr(notif.record, 'reply', None), 'root', None),
                        'parent_uri': getattr(getattr(notif.record, 'reply', None), 'parent', None),
                    })
                    
    except Exception as e:
        log_error(f"Failed to fetch Bluesky mentions: {e}")
    
    return mentions


async def _get_x_mentions() -> List[Dict[str, Any]]:
    """Fetch unread mentions from X."""
    mentions = []
    try:
        from utils.kaia_twitter import get_x_client, is_x_configured
        
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
        from utils.kaia_bluesky import get_bluesky_client
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
        from utils.kaia_twitter import get_x_client
        
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


async def check_and_reply_mentions():
    """
    Main polling function - check both platforms and reply to mentions.
    
    Call this from a periodic task loop.
    """
    global _replied_ids
    
    # Load replied IDs if not loaded
    if not _replied_ids:
        _load_replied_ids()
    
    from bot.managers.yaml_config import config
    
    total_replies = 0
    
    # Check Bluesky
    if config.bluesky_enabled and config.get('bluesky.reply_to_mentions', True):
        log_action("Checking Bluesky mentions...")
        mentions = await _get_bluesky_mentions()
        
        for mention in mentions[:3]:  # Limit to 3 per poll to avoid rate limits
            author = mention['author']
            text = mention['text']
            
            log_info(f"Bluesky mention from @{author}: {text[:50]}...")
            
            response = await _generate_response(text, author, "bluesky")
            if response:
                success = await _reply_to_bluesky(mention, response)
                if success:
                    async with _replied_ids_lock:
                        _replied_ids.add(mention['id'])
                    log_success(f"Replied to @{author} on Bluesky: {response[:50]}...")
                    total_replies += 1
    
    # Check X
    if config.x_enabled and config.get('x_twitter.reply_to_mentions', True):
        log_action("Checking X mentions...")
        mentions = await _get_x_mentions()
        
        for mention in mentions[:3]:  # Limit to 3 per poll
            author = mention['author']
            text = mention['text']
            
            log_info(f"X mention from @{author}: {text[:50]}...")
            
            response = await _generate_response(text, author, "x")
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
