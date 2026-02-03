"""
Kaia X (Twitter) Integration
=============================

Async client for posting to X/Twitter using twikit (unofficial API).

Uses username/password authentication, no API keys needed.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error

# Lazy import to avoid blocking startup
_client = None
_client_lock = asyncio.Lock()
_cookies_path = Path("memory/x_cookies.json")


def is_x_configured() -> bool:
    """Check if X credentials and enabled flag are configured."""
    from utils.infrastructure.system.yaml_config import config
    if not config.x_enabled:
        return False
        
    username = os.getenv("X_USERNAME")
    password = os.getenv("X_PASSWORD")
    return bool(username and password)


async def get_x_client():
    """Get or create the X client (lazy initialization with cookie persistence)."""
    global _client
    
    if not is_x_configured():
        return None
    
    async with _client_lock:
        if _client is None:
            try:
                from twikit import Client
                
                username = os.getenv("X_USERNAME")
                password = os.getenv("X_PASSWORD")
                
                _client = Client('en-US')
                
                # Try to load existing cookies first
                if _cookies_path.exists():
                    try:
                        _client.load_cookies(_cookies_path)
                        log_info(f"Loaded X session from cookies")
                        return _client
                    except Exception as e:
                        log_warning(f"Failed to load X cookies, will re-login: {e}")
                
                # Fresh login
                await _client.login(
                    auth_info_1=username,
                    auth_info_2=username,  # Can also be email
                    password=password
                )
                
                # Save cookies for future sessions
                _cookies_path.parent.mkdir(exist_ok=True)
                _client.save_cookies(_cookies_path)
                
                log_success(f"X client logged in as @{username}")
            except Exception as e:
                log_error(f"Failed to create X client: {e}")
                return None
        
        return _client


async def post_to_x(text: str) -> tuple[bool, Optional[str]]:
    """
    Post text to X (Twitter).
    
    Args:
        text: The post content (max 280 chars for X)
        
    Returns:
        (success, tweet_id or error_message)
    """
    client = await get_x_client()
    
    if client is None:
        return False, "X client not available"
    
    # Truncate to X's 280 char limit if needed
    if len(text) > 280:
        text = text[:277] + "..."
        log_warning(f"Truncated X post to 280 chars")
    
    try:
        tweet = await client.create_tweet(text)
        log_success(f"Posted to X: {text[:50]}...")
        return True, tweet.id
    except Exception as e:
        error_msg = str(e)
        log_error(f"X post failed: {error_msg}")
        
        # If auth error, clear cookies and try again next time
        if "auth" in error_msg.lower() or "login" in error_msg.lower():
            if _cookies_path.exists():
                _cookies_path.unlink()
                log_warning("Cleared X cookies due to auth error")
        
        return False, error_msg


async def post_quip_to_x(quip: str) -> bool:
    """
    Post an idle quip to X (convenience wrapper).
    
    Args:
        quip: The quip text to post
        
    Returns:
        True if posted successfully, False otherwise
    """
    success, result = await post_to_x(quip)
    return success
