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

# Lazy import to prevent hangs during initialization
AsyncClient = AsyncRequest = models = None

def _ensure_atproto():
    """Lazy import atproto to avoid blocking startup."""
    global AsyncClient, AsyncRequest, models
    if AsyncClient is None:
        try:
            from atproto import AsyncClient as _AC, AsyncRequest as _AR, models as _m
            AsyncClient, AsyncRequest, models = _AC, _AR, _m
        except ImportError:
            log_warning("atproto library not found. Bluesky integration will be disabled.")
    return AsyncClient is not None

# Lazy client instance
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
        
    # Offload the blocking atproto import to a thread on first call.
    # atproto is large — its first import takes 8-10s and will stall the event loop.
    if AsyncClient is None:
        await asyncio.to_thread(_ensure_atproto)
    
    async with _client_lock:
        if force_new:
            _client = None
            log_info("Forcing new Bluesky client session...")
            
        if _client is None:
            if AsyncClient is None:
                log_error("Cannot create Bluesky client: atproto not installed.")
                return None
                
            try:
                handle = os.getenv("BLUESKY_HANDLE")
                password = os.getenv("BLUESKY_APP_PASSWORD")
                
                # Increase timeout from default 5s to 60s to handle significant network lag
                request = AsyncRequest(timeout=60.0)
                _client = AsyncClient(request=request)
                
                # Simple retry logic for login
                for attempt in range(3):
                    try:
                        await _client.login(handle, password)
                        log_success(f"Bluesky client logged in as {handle} (Timeout: 60s, Attempt: {attempt+1})")
                        break
                    except Exception as e:
                        if attempt == 2: raise
                        log_warning(f"Bluesky login attempt {attempt+1} failed: {e}. Retrying...")
                        await asyncio.sleep(2 * (attempt + 1))
            except Exception as e:
                log_error(f"Failed to create Bluesky client ({type(e).__name__}): {e}")
                import traceback
                log_debug(f"Client creation traceback:\n{traceback.format_exc()}")
                _client = None
                return None
        
        return _client


def _split_into_thread(text: str, max_chars: int = 300, max_posts: int = 5) -> list[str]:
    """Split text into posts of at most `max_chars`, at sentence boundaries.

    A post keeps the whitespace between its sentences, so a paragraph break
    stays a paragraph break. A sentence too long for one post is cut between
    words, and a single token too long for one post (a URL) is cut outright:
    Bluesky rejects an oversized post, which would leave the thread without
    its tail. Anything past `max_posts` is dropped, and the last post says so
    with an ellipsis rather than ending as if the thought were complete.
    """
    import re

    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    # Units are (separator-before, sentence); the separator is kept verbatim.
    parts = re.split(r"(?<=[.!?])(\s+)", text)
    units = [("", parts[0])] + [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]

    def pieces(sentence: str) -> list[str]:
        """A sentence as pieces that each fit, cut between words when needed."""
        if len(sentence) <= max_chars:
            return [sentence]
        out, cur = [], ""
        for word in sentence.split():
            while len(word) > max_chars - 1:           # a token longer than a post
                if cur:
                    out.append(cur + "…")
                    cur = ""
                out.append(word[:max_chars - 1] + "…")
                word = word[max_chars - 1:]
            cand = f"{cur} {word}" if cur else word
            if len(cand) <= max_chars - 1:
                cur = cand
            else:
                out.append(cur + "…")
                cur = word
        if cur:
            out.append(cur)
        return out

    chunks: list[str] = []
    cur = ""
    for sep, sentence in units:
        if not sentence.strip():
            continue
        cand = cur + sep + sentence if cur else sentence
        if len(cand) <= max_chars:
            cur = cand
            continue
        if cur:
            chunks.append(cur.rstrip())
        split = pieces(sentence)
        chunks.extend(split[:-1])
        cur = split[-1]
    if cur:
        chunks.append(cur.rstrip())

    if len(chunks) > max_posts:
        log_warning(f"Bluesky thread cut to {max_posts} of {len(chunks)} posts")
        chunks = chunks[:max_posts]
        last = chunks[-1].rstrip("…")
        chunks[-1] = (last if len(last) < max_chars else last[:max_chars - 1].rstrip()) + "…"
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
    # Split into thread chunks if needed, then delegate to thread poster
    from utils.infrastructure.system.yaml_config import config
    max_threads = config.get('social.max_thread_posts', 5)
    chunks = _split_into_thread(text, max_chars=300, max_posts=max_threads)
    log_debug(f"Split Bluesky message into {len(chunks)} chunks")
    return await post_thread_to_bluesky(chunks)



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
    if AsyncClient is None:
        await asyncio.to_thread(_ensure_atproto)
    if models is None:
        return False, "atproto models not available"
    
    if not chunks:
        return False, "No content to post"
    
    # Retry once with a fresh session if the first attempt fails — that handles
    # an expired token, which is a failure of the *first* call.
    #
    # Progress is tracked across attempts, so a retry resumes at the chunk that
    # failed. Retrying the whole thread instead re-posts a root that is already
    # live — two identical roots on a public timeline, the first orphaned with a
    # partial thread hanging off it.
    root = None          # (uri, cid) of the first post, once it exists
    prev = None          # (uri, cid) of the most recent post in the thread
    next_index = 0       # the chunk to post next
    last_error = "unknown error"

    for attempt in range(2):
        client = await get_bluesky_client(force_new=(attempt > 0))

        if client is None:
            return False, "Bluesky client not available"

        try:
            if root is None:
                first_post = await client.send_post(chunks[0])
                root = (first_post.uri, first_post.cid)
                prev = root
                next_index = 1
                log_success(f"Posted to Bluesky: {chunks[0][:50]}...")
                if len(chunks) > 1:
                    log_info(f"Creating Bluesky thread with {len(chunks)} posts...")

            while next_index < len(chunks):
                chunk = chunks[next_index]
                parent_ref = models.ComAtprotoRepoStrongRef.Main(uri=prev[0], cid=prev[1])
                root_ref = models.ComAtprotoRepoStrongRef.Main(uri=root[0], cid=root[1])
                reply_ref = models.AppBskyFeedPost.ReplyRef(root=root_ref, parent=parent_ref)

                continuation = await client.send_post(chunk, reply_to=reply_ref)
                log_debug(f"Thread post {next_index + 1}/{len(chunks)}: {chunk[:40]}...")

                prev = (continuation.uri, continuation.cid)
                next_index += 1

            if len(chunks) > 1:
                log_success(f"Bluesky thread complete ({len(chunks)} posts)")
            return True, root[0]

        except Exception as e:
            # A timeout's str() is empty; the type is the information.
            last_error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            if attempt == 0:
                where = "posting" if root is None else f"at chunk {next_index + 1}/{len(chunks)}"
                log_warning(f"Bluesky post failed ({where}), retrying with fresh session: {last_error}")
                continue
            log_error(f"Bluesky post failed after retry: {last_error}")
            break

    if root is not None:
        # The root is live and the thread is short of its tail. Reporting failure
        # here would invite the caller to post the whole thing again, which is
        # the outcome this function exists to avoid.
        log_error(f"Bluesky thread incomplete: {next_index}/{len(chunks)} posts up, "
                  f"root at {root[0]}. Last error: {last_error}")
        return True, root[0]
    return False, last_error


async def get_post_text(uri: str) -> Optional[str]:
    """
    Fetch the text content of a Bluesky post by its URI.
    Useful for retrieving parent context in replies.
    """
    client = await get_bluesky_client()
    if not client:
        return None
        
    try:
        # get_posts takes a list of URIs
        response = await client.app.bsky.feed.get_posts(params=models.AppBskyFeedGetPosts.Params(uris=[uri]))
        if response.posts:
            # The record contains the actual text
            return getattr(response.posts[0].record, 'text', None)
        return None
    except Exception as e:
        log_warning(f"Failed to fetch Bluesky post text for {uri}: {e}")
        return None
