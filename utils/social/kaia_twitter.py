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
                            
                            def _save_injected_cookies():
                                from utils.core.atomic_write import write_atomic
                                write_atomic(_cookies_path, json.dumps(cookie_dict, indent=2))
                            
                            await asyncio.to_thread(_save_injected_cookies)
                            
                            # Try loading the newly written cookies
                            try:
                                # Offload the cookie loading as well
                                await asyncio.to_thread(_client.load_cookies, _cookies_path)
                                log_success("Successfully injected browser session into X client")
                                return _client
                            except Exception as e:
                                log_error(f"Failed to load injected cookies ({type(e).__name__}): {e}")
                    
                    log_error(f"Failed to create X client ({error_type}): {login_err}")
                    # Not kept: a client that never logged in was being handed to
                    # every later caller, so one failed login ended X posting
                    # until a restart.
                    _client = None
                    return None
            except Exception as e:
                log_error(f"Unexpected error creating X client ({type(e).__name__}): {e}")
                import traceback
                log_debug(f"X client error traceback:\n{traceback.format_exc()}")
                _client = None
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
        # More robust check using status_code if available, falling back to string match
        is_auth_error = False
        if hasattr(e, 'status_code') and e.status_code == 401:
            is_auth_error = True
        elif "401" in error_msg or "unauthorized" in error_msg.lower():
            is_auth_error = True
            
        if is_auth_error:
            # The cached client holds the dead session too; drop it with the
            # cookies so the next call logs in again.
            global _client
            _client = None
            if _cookies_path.exists():
                _cookies_path.unlink()
                log_warning(f"Cleared dead X cookies (received auth error: {error_msg})")
        
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


_COOKIE_EXTRACTION_WARNED: set[tuple[str, str, str]] = set()


def _cookie_extraction_warning(source: str, domain: str, error: BaseException,
                               path: Optional[Path] = None) -> None:
    """Log each repeated browser/profile failure once without exposing cookie values."""
    key = (source, domain, type(error).__name__)
    if key in _COOKIE_EXTRACTION_WARNED:
        return
    _COOKIE_EXTRACTION_WARNED.add(key)
    location = f" at {path}" if path is not None else ""
    detail = str(error).replace("\n", " ")[:180]
    log_warning(
        f"[X COOKIE] {source} extraction failed for {domain}{location} "
        f"({type(error).__name__}): {detail}"
    )


def _browser_cookie_db_candidates(home: Optional[Path] = None) -> list[tuple[str, str, Path, Path]]:
    """Known Linux browser profile databases as (label, loader, root, database)."""
    home = home or Path.home()
    roots = [
        ("Firefox", "firefox", home / ".mozilla" / "firefox"),
        ("Firefox Snap", "firefox", home / "snap" / "firefox" / "common" / ".mozilla" / "firefox"),
        ("Firefox Flatpak", "firefox", home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox"),
        ("LibreWolf", "librewolf", home / ".librewolf"),
        ("LibreWolf Flatpak", "librewolf", home / ".var" / "app" / "io.gitlab.librewolf-community" / ".librewolf"),
        ("Firedragon Flatpak", "firefox", home / ".var" / "app" / "org.garudalinux.firedragon" / ".firedragon"),
        ("Chrome", "chrome", home / ".config" / "google-chrome"),
        ("Chrome Snap", "chrome", home / "snap" / "chromium" / "common" / "chromium"),
        ("Chromium", "chromium", home / ".config" / "chromium"),
        ("Chromium Flatpak", "chromium", home / ".var" / "app" / "org.chromium.Chromium" / "config" / "chromium"),
        ("Brave", "brave", home / ".config" / "BraveSoftware" / "Brave-Browser"),
        ("Brave Flatpak", "brave", home / ".var" / "app" / "com.brave.Browser" / "config" / "BraveSoftware" / "Brave-Browser"),
    ]
    candidates: list[tuple[str, str, Path, Path]] = []
    seen: set[Path] = set()
    for label, loader_name, root in roots:
        if not root.is_dir():
            continue
        # Firefox-family profile roots normally hold <profile>/cookies.sqlite.
        if loader_name in ("firefox", "librewolf"):
            possible = [root / "cookies.sqlite"]
            try:
                possible.extend(root.glob("*/cookies.sqlite"))
                # Custom profiles can be nested in a non-default subdirectory.
                possible.extend(root.glob("*/*/cookies.sqlite"))
            except OSError as e:
                _cookie_extraction_warning(label, "x.com", e, root)
        else:
            # Chromium migrated to Network/Cookies, but older versions used
            # <profile>/Cookies. Cover both layouts and a root-level profile.
            possible = [
                root / "Cookies",
                root / "Network" / "Cookies",
            ]
            try:
                possible.extend(root.glob("*/Network/Cookies"))
                possible.extend(root.glob("*/Cookies"))
            except OSError as e:
                _cookie_extraction_warning(label, "x.com", e, root)
        for database in possible:
            try:
                resolved = database.resolve()
            except OSError:
                resolved = database
            if database.is_file() and resolved not in seen:
                seen.add(resolved)
                candidates.append((label, loader_name, root, database))
    return candidates


def _load_cookies_from_profile_copy(loader, loader_name: str, profile_root: Path,
                                    database: Path, domain: str) -> list:
    """Copy a live SQLite cookie DB and its WAL sidecars before parsing it.

    SQLite WAL data is not necessarily checkpointed into the main database while
    a browser is open. Copying only Cookies/cookies.sqlite can silently miss the
    current session; copy existing -wal/-shm sidecars too. The copy is short-lived
    and never modifies the browser's original profile.
    """
    with tempfile.TemporaryDirectory(prefix="kaiacord-x-cookies-") as temp_dir:
        temp_root = Path(temp_dir)
        try:
            relative = database.relative_to(profile_root)
        except ValueError:
            relative = Path(database.name)
        copied_db = temp_root / relative
        copied_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(database, copied_db)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(database) + suffix)
            if sidecar.is_file():
                # A sidecar can disappear between is_file and copy2 while the
                # browser checkpoints it. Keep the main copy usable if that
                # happens, but report the race so session failures are explainable.
                try:
                    shutil.copy2(sidecar, Path(str(copied_db) + suffix))
                except OSError as e:
                    _cookie_extraction_warning(
                        f"{loader_name} SQLite {suffix} sidecar", domain, e, sidecar
                    )
        kwargs = {"cookie_file": str(copied_db), "domain_name": domain}
        # Chromium decryption may consult Local State; pass the original key
        # file explicitly where the browser profile exposes one.
        local_state = profile_root / "Local State"
        if loader_name not in ("firefox", "librewolf") and local_state.is_file():
            kwargs["key_file"] = str(local_state)
        return list(loader(**kwargs))


def _extract_browser_cookies() -> dict:
    """Extract X cookies from supported browsers, including common Linux profiles.

    Try browser_cookie3's own detection first; on a locked SQLite database,
    retry known profile paths from a short-lived copy including WAL files.
    """
    try:
        import browser_cookie3
    except ImportError as e:
        log_error("browser_cookie3 not installed. Cannot recover the X session from browser cookies.")
        _cookie_extraction_warning("browser_cookie3 import", "x.com", e)
        return {}

    domains = ("x.com", "twitter.com")
    browser_loaders = (
        ("Chrome", "chrome"),
        ("Chromium", "chromium"),
        ("Brave", "brave"),
        ("Firefox", "firefox"),
        ("LibreWolf", "librewolf"),
    )
    all_cookies = []
    attempted = 0

    # First use package autodetection for any browser it already supports.
    for label, loader_name in browser_loaders:
        loader = getattr(browser_cookie3, loader_name, None)
        if not callable(loader):
            log_debug(f"[X COOKIE] browser_cookie3 has no {loader_name} loader; skipping {label}.")
            continue
        for domain in domains:
            attempted += 1
            try:
                found = list(loader(domain_name=domain))
                all_cookies.extend(found)
                if found:
                    log_debug(f"[X COOKIE] Read {len(found)} {domain} cookie(s) using {label} autodetection.")
            except Exception as e:
                _cookie_extraction_warning(f"{label} autodetection", domain, e)

    # If autodetection failed (locked/open profile, non-standard location, or
    # sandboxed install), try explicit local profile files with a temporary copy.
    for label, loader_name, profile_root, database in _browser_cookie_db_candidates():
        loader = getattr(browser_cookie3, loader_name, None)
        if not callable(loader):
            continue
        for domain in domains:
            attempted += 1
            try:
                found = _load_cookies_from_profile_copy(
                    loader, loader_name, profile_root, database, domain
                )
                all_cookies.extend(found)
                if found:
                    log_debug(
                        f"[X COOKIE] Read {len(found)} {domain} cookie(s) from "
                        f"a copied {label} profile database at {database}."
                    )
            except Exception as e:
                _cookie_extraction_warning(f"{label} copied-profile", domain, e, database)

    cookie_dict = {}
    for cookie in all_cookies:
        name = getattr(cookie, "name", None)
        value = getattr(cookie, "value", None)
        if name and value is not None:
            cookie_dict[name] = value

    # auth_token is the credential-bearing X session cookie. Do not inject a
    # partial or logged-out cookie jar just because unrelated site cookies exist.
    if "auth_token" in cookie_dict:
        log_info(f"[X COOKIE] Found an auth_token in {len(all_cookies)} extracted browser cookies.")
        return cookie_dict

    log_warning(
        f"[X COOKIE] No auth_token found after {attempted} browser/profile extraction attempts. "
        "Check that a browser is logged in to X and that its profile is readable."
    )
    return {}
