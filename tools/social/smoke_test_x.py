import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.social.kaia_twitter import get_x_client, post_to_x
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error

async def smoke_test_x():
    log_info("Starting X/Twitter Smoke Test...")
    
    # Check environment variables
    load_dotenv()
    username = os.getenv("X_USERNAME")
    password = os.getenv("X_PASSWORD")
    
    if not username or not password:
        log_error("X_USERNAME or X_PASSWORD not found in .env")
        return

    log_info(f"Testing login for @{username}...")
    
    try:
        client = await get_x_client()
        if client:
            log_success(f"Successfully connected to X as @{username}")
            
            # Check if we can get account info (minimal read test)
            try:
                # user = await client.user() # Some versions might differ, let's try a simple property or method
                # Better to just try to get the user ID or similar
                me = await client.get_user_by_screen_name(username)
                log_success(f"Verified account info: {me.name} (ID: {me.id})")
                
                # OPTIONAL: Uncomment to test actual posting
                # success, tweet_id = await post_to_x("Kaia System Restoration: Social connection verified. [Smoke Test]")
                # if success:
                #     log_success(f"Successfully posted test tweet! ID: {tweet_id}")
                # else:
                #     log_error(f"Failed to post test tweet: {tweet_id}")
                
            except Exception as e:
                log_error(f"Failed to verify account info: {e}")
        else:
            log_error("Failed to initialize X client (check logs or cookies)")
            
    except Exception as e:
        log_error(f"X Smoke Test failed with exception: {e}")

if __name__ == "__main__":
    asyncio.run(smoke_test_x())
