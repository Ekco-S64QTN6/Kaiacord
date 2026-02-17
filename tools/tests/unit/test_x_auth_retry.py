import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.social.kaia_social_responder import _get_x_mentions, _load_replied_ids
from utils.social.kaia_twitter import _cookies_path
from utils.infrastructure.logging.kaia_logger import log_info, log_success

async def test_x_retry():
    log_info("Starting X Auth Retry Verification...")
    
    # 1. Initialize replicated IDs
    _load_replied_ids()
    
    # 2. Check if cookies exist
    if _cookies_path.exists():
        log_info(f"Existing cookies found at {_cookies_path}")
    else:
        log_info("No existing cookies found. A fresh login will be attempted.")

    # 3. Call _get_x_mentions which now has the retry logic
    # This should:
    # - Attempt to fetch with existing cookies
    # - If 401 occurs, clear everything and retry
    mentions = await _get_x_mentions()
    
    if mentions is not None:
        log_success(f"Successfully fetched {len(mentions)} X mentions using the responder logic.")
        for m in mentions[:2]:
            print(f"  - From @{m['author']}: {m['text'][:50]}")
    else:
        print("Failed to fetch X mentions even with retry logic.")

if __name__ == "__main__":
    asyncio.run(test_x_retry())
