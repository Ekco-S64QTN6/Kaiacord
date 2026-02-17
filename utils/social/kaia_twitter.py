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
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error, log_debug

# Twikit Client is imported lazily to prevent massive startup stalls
Client = None

# Lazy client instance
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


async def get_x_client(force_new: bool = False):
    """Get or create the X client (lazy initialization with cookie persistence)."""
    global _client
    
    if force_new:
        async with _client_lock:
            _client = None
            if _cookies_path.exists():
                _cookies_path.unlink()
                log_warning(f"Forced reset of X client session (unlinked {_cookies_path})")
    
    if not is_x_configured():
        return None
    
    async with _client_lock:
        if _client is None:
            try:
                username = os.getenv("X_USERNAME")
                password = os.getenv("X_PASSWORD")
                
                # Lazy import twikit to avoid 20s+ event loop stalls during module load
                global Client
                if Client is None:
                    try:
                        from twikit import Client
                    except ImportError:
                        log_error("twikit library not found. X integration disabled.")
                        return None

                _client = await asyncio.to_thread(Client, 'en-US')
                
                # Try to load existing cookies first
                if _cookies_path.exists():
                    try:
                        # Offload the cookie loading as well
                        await asyncio.to_thread(_client.load_cookies, _cookies_path)
                        log_debug(f"Loaded X session from {_cookies_path}")
                        return _client
                    except Exception as e:
                        log_warning(f"Failed to load X cookies: {e}")
                
                # Fresh login
                email = os.getenv("X_EMAIL")
                
                try:
                    await _client.login(
                        auth_info_1=username,
                        auth_info_2=email if email else username,
                        password=password
                    )
                    # Save cookies for future sessions
                    _cookies_path.parent.mkdir(exist_ok=True)
                    # Offload the cookie saving as well
                    await asyncio.to_thread(_client.save_cookies, _cookies_path)
                    log_success(f"X client logged in as @{username}")
                    return _client
                except Exception as login_err:
                    error_type = type(login_err).__name__
                    if "cloudflare" in str(login_err).lower() or "403" in str(login_err):
                        log_warning(f"Direct X login blocked by Cloudflare ({error_type}). Attempting background cookie extraction...")
                        
                        # OFF-THREAD COOKIE EXTRACTION
                        cookie_dict = await asyncio.to_thread(_extract_browser_cookies)
                        
                        if cookie_dict:
                            log_info("Found browser cookies. Injecting session...")
                            import json
                            _cookies_path.parent.mkdir(exist_ok=True)
                            with open(_cookies_path, 'w') as f:
                                json.dump(cookie_dict, f, indent=2)
                            
                            # Try loading the newly written cookies
                            try:
                                # Offload the cookie loading as well
                                await asyncio.to_thread(_client.load_cookies, _cookies_path)
                                log_success("Successfully injected browser session into X client")
                                return _client
                            except Exception as e:
                                log_error(f"Failed to load injected cookies ({type(e).__name__}): {e}")
                    
                    log_error(f"Failed to create X client ({error_type}): {login_err}")
                    return None
            except Exception as e:
                log_error(f"Unexpected error creating X client ({type(e).__name__}): {e}")
                import traceback
                log_debug(f"X client error traceback:\n{traceback.format_exc()}")
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
        error_type = type(e).__name__
        log_error(f"X post failed ({error_type}): {error_msg}")
        
        # If auth error (401), clear cookies so they can be re-extracted on next use
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            if _cookies_path.exists():
                _cookies_path.unlink()
                log_warning("Cleared dead X cookies (received 401)")
        
        return False, f"{error_type}: {error_msg}"


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


def _extract_browser_cookies() -> dict:
    """Synchronous helper to extract X/Twitter cookies from browsers."""
    try:
        import browser_cookie3
        
        # We need to check both x.com and legacy twitter.com
        domains = ['x.com', 'twitter.com']
        all_cookies = []
        
        for domain in domains:
            try:
                # Try Chrome
                all_cookies.extend(list(browser_cookie3.chrome(domain_name=domain)))
            except: pass
            try:
                # Try Firefox
                all_cookies.extend(list(browser_cookie3.firefox(domain_name=domain)))
            except: pass

        # Specific path for Firedragon (Flatpak)
        firedragon_path = Path.home() / ".var/app/org.garudalinux.firedragon/.firedragon"
        if firedragon_path.exists():
            try:
                for profile in firedragon_path.glob("*/cookies.sqlite"):
                    for domain in domains:
                        try:
                            all_cookies.extend(list(browser_cookie3.firefox(cookie_file=str(profile), domain_name=domain)))
                        except: pass
            except: pass
        
        if all_cookies:
            # Twikit 2.x expects a flat dictionary of {name: value}
            cookie_dict = {}
            for cookie in all_cookies:
                cookie_dict[cookie.name] = cookie.value
            
            # VERIFICATION: Ensure we have the critical session cookies
            # auth_token: The main session secret
            # ct0: CSRF token
            if 'auth_token' in cookie_dict:
                log_debug("Found 'auth_token' in extracted cookies.")
                return cookie_dict
            else:
                log_warning("Extracted cookies found, but missing 'auth_token' (logged out?).")
                
    except ImportError:
        log_error("browser_cookie3 not installed. Cannot attempt cookie bypass.")
    except Exception as e:
        log_error(f"Error extracting browser cookies: {e}")
    
    return {}
