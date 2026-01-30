"""
Kaia Bluesky Integration
========================

Async client for posting to Bluesky with Kaia's personality.

Uses the atproto SDK to connect to the AT Protocol (Bluesky).
"""

import os
import asyncio
from typing import Optional
from utils.kaia_logger import log_info, log_success, log_warning, log_error

# Lazy import to avoid blocking startup
_client = None
_client_lock = asyncio.Lock()


def is_bluesky_configured() -> bool:
    """Check if Bluesky credentials are configured."""
    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_APP_PASSWORD")
    return bool(handle and password)


async def get_bluesky_client():
    """Get or create the Bluesky client (lazy initialization)."""
    global _client
    
    if not is_bluesky_configured():
        return None
    
    async with _client_lock:
        if _client is None:
            try:
                from atproto import AsyncClient
                
                handle = os.getenv("BLUESKY_HANDLE")
                password = os.getenv("BLUESKY_APP_PASSWORD")
                
                _client = AsyncClient()
                await _client.login(handle, password)
                log_success(f"Bluesky client logged in as {handle}")
            except Exception as e:
                log_error(f"Failed to create Bluesky client: {e}")
                return None
        
        return _client


async def post_to_bluesky(text: str) -> tuple[bool, Optional[str]]:
    """
    Post text to Bluesky.
    
    Args:
        text: The post content (max 300 chars for Bluesky)
        
    Returns:
        (success, post_uri or error_message)
    """
    client = await get_bluesky_client()
    
    if client is None:
        return False, "Bluesky client not available"
    
    # Truncate to Bluesky's 300 char limit if needed
    if len(text) > 300:
        text = text[:297] + "..."
        log_warning(f"Truncated Bluesky post to 300 chars")
    
    try:
        post = await client.send_post(text)
        log_success(f"Posted to Bluesky: {text[:50]}...")
        return True, post.uri
    except Exception as e:
        log_error(f"Bluesky post failed: {e}")
        return False, str(e)


async def post_quip_to_bluesky(quip: str) -> bool:
    """
    Post an idle quip to Bluesky (convenience wrapper).
    
    Args:
        quip: The quip text to post
        
    Returns:
        True if posted successfully, False otherwise
    """
    success, result = await post_to_bluesky(quip)
    return success
