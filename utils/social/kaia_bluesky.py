"""
Kaia Bluesky Integration
========================

Async client for posting to Bluesky with Kaia's personality.

Uses the atproto SDK to connect to the AT Protocol (Bluesky).
"""

import os
import asyncio
from typing import Optional
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_warning, log_error, log_debug

# Lazy import to avoid blocking startup
_client = None
_client_lock = asyncio.Lock()


def is_bluesky_configured() -> bool:
    """Check if Bluesky credentials and enabled flag are configured."""
    from utils.infrastructure.system.yaml_config import config
    if not config.bluesky_enabled:
        return False
        
    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_APP_PASSWORD")
    return bool(handle and password)


async def get_bluesky_client(force_new: bool = False):
    """Get or create the Bluesky client (lazy initialization)."""
    global _client
    
    if not is_bluesky_configured():
        return None
    
    async with _client_lock:
        if force_new:
            _client = None
            log_info("Forcing new Bluesky client session...")
            
        if _client is None:
            try:
                from atproto import AsyncClient, AsyncRequest
                
                handle = os.getenv("BLUESKY_HANDLE")
                password = os.getenv("BLUESKY_APP_PASSWORD")
                
                # Increase timeout from default 5s to 20s to handle orbital network lag
                request = AsyncRequest(timeout=20.0)
                _client = AsyncClient(request=request)
                await _client.login(handle, password)
                log_success(f"Bluesky client logged in as {handle} (Timeout: 20s)")
            except Exception as e:
                log_error(f"Failed to create Bluesky client ({type(e).__name__}): {e}")
                import traceback
                log_debug(f"Client creation traceback:\n{traceback.format_exc()}")
                _client = None
                return None
        
        return _client


def _split_into_thread(text: str, max_chars: int = 300) -> list[str]:
    """
    Split long text into thread-friendly chunks at natural sentence boundaries.
    
    Returns a list of strings, each under max_chars.
    """
    if len(text) <= max_chars:
        return [text]
    
    import re
    # Split on sentence endings while keeping the punctuation
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # Check if adding this sentence would exceed the limit
        candidate = (current_chunk + " " + sentence).strip() if current_chunk else sentence
        
        if len(candidate) <= max_chars:
            current_chunk = candidate
        else:
            # Save current chunk if it has content
            if current_chunk:
                chunks.append(current_chunk)
            
            # If single sentence exceeds limit, split mid-sentence at word boundary
            if len(sentence) > max_chars:
                words = sentence.split()
                current_chunk = ""
                for word in words:
                    candidate = (current_chunk + " " + word).strip() if current_chunk else word
                    if len(candidate) <= max_chars - 3:  # Leave room for "..."
                        current_chunk = candidate
                    else:
                        if current_chunk:
                            chunks.append(current_chunk + "...")
                        current_chunk = word
            else:
                current_chunk = sentence
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


async def post_to_bluesky(text: str) -> tuple[bool, Optional[str]]:
    """
    Post text to Bluesky. If text exceeds 300 chars, create a thread
    by replying to self to finish the thought naturally.
    
    Args:
        text: The post content
        
    Returns:
        (success, post_uri or error_message)
    """
    from atproto import models
    
    client = await get_bluesky_client()
    
    if client is None:
        return False, "Bluesky client not available"
    
    # Split into thread chunks if needed
    chunks = _split_into_thread(text, max_chars=300)
    
    try:
        # Post the first chunk
        first_post = await client.send_post(chunks[0])
        log_success(f"Posted to Bluesky: {chunks[0][:50]}...")
        
        # If there are more chunks, reply to self to create a thread
        if len(chunks) > 1:
            log_info(f"Creating Bluesky thread with {len(chunks)} posts...")
            
            # Track the previous post for threading
            prev_uri = first_post.uri
            prev_cid = first_post.cid
            root_uri = first_post.uri
            root_cid = first_post.cid
            
            for i, chunk in enumerate(chunks[1:], 2):
                # Build reply reference
                parent_ref = models.ComAtprotoRepoStrongRef.Main(uri=prev_uri, cid=prev_cid)
                root_ref = models.ComAtprotoRepoStrongRef.Main(uri=root_uri, cid=root_cid)
                reply_ref = models.AppBskyFeedPost.ReplyRef(root=root_ref, parent=parent_ref)
                
                # Post the continuation
                continuation = await client.send_post(chunk, reply_to=reply_ref)
                log_debug(f"Thread post {i}/{len(chunks)}: {chunk[:40]}...")
                
                # Update for next iteration
                prev_uri = continuation.uri
                prev_cid = continuation.cid
            
            log_success(f"Bluesky thread complete ({len(chunks)} posts)")
        
        return True, first_post.uri
        
    except Exception as e:
        log_error(f"Bluesky post failed: {e}")
        return False, str(e)


def needs_thread_expansion(text: str, min_second_chunk: int = 100) -> tuple[bool, str]:
    """
    Check if a text would result in an awkwardly short second post.
    
    Returns:
        (needs_expansion, remainder_text) - if needs_expansion is True,
        the remainder_text is what would be the short second post.
    """
    chunks = _split_into_thread(text, max_chars=300)
    
    if len(chunks) <= 1:
        return False, ""
    
    # Check if the last chunk is too short
    last_chunk = chunks[-1]
    if len(last_chunk) < min_second_chunk:
        return True, last_chunk
    
    return False, ""


async def post_thread_to_bluesky(chunks: list[str]) -> tuple[bool, Optional[str]]:
    """
    Post a pre-chunked thread to Bluesky.
    
    Use this when you've already prepared the thread content
    (e.g., after expanding a short second post).
    
    Args:
        chunks: List of post texts, each under 300 chars
        
    Returns:
        (success, first_post_uri or error_message)
    """
    from atproto import models
    
    client = await get_bluesky_client()
    
    if client is None:
        return False, "Bluesky client not available"
    
    if not chunks:
        return False, "No content to post"
    
    try:
        # Post the first chunk
        first_post = await client.send_post(chunks[0])
        log_success(f"Posted to Bluesky: {chunks[0][:50]}...")
        
        # If there are more chunks, reply to self to create a thread
        if len(chunks) > 1:
            log_info(f"Creating Bluesky thread with {len(chunks)} posts...")
            
            prev_uri = first_post.uri
            prev_cid = first_post.cid
            root_uri = first_post.uri
            root_cid = first_post.cid
            
            for i, chunk in enumerate(chunks[1:], 2):
                parent_ref = models.ComAtprotoRepoStrongRef.Main(uri=prev_uri, cid=prev_cid)
                root_ref = models.ComAtprotoRepoStrongRef.Main(uri=root_uri, cid=root_cid)
                reply_ref = models.AppBskyFeedPost.ReplyRef(root=root_ref, parent=parent_ref)
                
                continuation = await client.send_post(chunk, reply_to=reply_ref)
                log_debug(f"Thread post {i}/{len(chunks)}: {chunk[:40]}...")
                
                prev_uri = continuation.uri
                prev_cid = continuation.cid
            
            log_success(f"Bluesky thread complete ({len(chunks)} posts)")
        
        return True, first_post.uri
        
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
