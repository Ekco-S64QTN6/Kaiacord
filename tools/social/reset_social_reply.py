#!/usr/bin/env python3
import os
import asyncio
from atproto import models
from utils.social.kaia_bluesky import get_bluesky_client
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error

async def reset_error_replies():
    """Find and delete 'Something went wrong in my head' posts from the bot's feed."""
    client = await get_bluesky_client()
    if not client:
        log_error("Could not initialize Bluesky client.")
        return

    handle = os.getenv("BLUESKY_HANDLE")
    log_info(f"Scanning feed for @{handle} to remove error replies...")
    
    try:
        # Get bot's recent posts
        response = await client.app.bsky.feed.get_author_feed(
            params=models.AppBskyFeedGetAuthorFeed.Params(actor=handle, limit=20)
        )
        
        target_parent = "at://did:plc:tvwmytdtnxhuplzc2waz2lue/app.bsky.feed.post/3meuk5bfuhz25"
        deleted_count = 0
        
        for item in response.feed:
            post = item.post
            parent = getattr(post.record, 'reply', None)
            parent_uri = parent.parent.uri if parent and parent.parent else None
            
            text = getattr(post.record, 'text', str(getattr(post.record, 'value', '')))
            log_info(f"Checking post: '{text[:20]}...' (Parent: {parent_uri})")
            
            # Match either by text or by the specific parent we know from the log
            if (parent_uri == target_parent) or ("Something went wrong" in text):
                log_info(f"MATCH! Deleting {post.uri}")
                await client.delete_post(post.uri)
                deleted_count += 1
        
        if deleted_count > 0:
            log_success(f"Successfully deleted {deleted_count} error replies.")
        else:
            log_info("No error replies found in recent feed.")
            
    except Exception as e:
        log_error(f"Failed to reset social replies: {e}")

if __name__ == "__main__":
    asyncio.run(reset_error_replies())
