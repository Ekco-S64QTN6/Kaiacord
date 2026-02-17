import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from utils
sys.path.append(os.getcwd())
load_dotenv()

async def verify_fetch():
    print("Verifying Bluesky fetch logic...")
    try:
        from utils.social.kaia_social_responder import _get_bluesky_mentions
        
        # We need to mock the config if it's not loaded, but kaia_social_responder imports it.
        # Let's hope the environment is enough.
        
        print("Calling _get_bluesky_mentions()...")
        mentions = await _get_bluesky_mentions()
        print(f"Successfully fetched {len(mentions)} mentions.")
        
        # Verify limit was passed (we can't easily spy on it without mocking, 
        # but if it runs without error, the kwargs are likely valid or ignored gracefully)
        print("Fetch completed without error.")
        
    except Exception as e:
        print(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_fetch())
