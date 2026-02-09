import asyncio
import os
import sys
from atproto import AsyncClient, AsyncRequest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def main():
    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_APP_PASSWORD")

    if not handle or not password:
        print("Error: BLUESKY_HANDLE or BLUESKY_APP_PASSWORD not set in .env")
        return

    print(f"Attempting to connect to Bluesky as {handle}...")

    try:
        # Replicate the logic in kaia_bluesky.py
        request = AsyncRequest(timeout=60.0)
        client = AsyncClient(request=request)
        
        print("Logging in...")
        await client.login(handle, password)
        print("Login successful.")

        print("Fetching notifications...")
        # Replicate the logic in kaia_social_responder.py
        # notifs = await client.app.bsky.notification.list_notifications()
        # The actual call in kaia_social_responder.py is:
        # notifs = await client.app.bsky.notification.list_notifications()
        
        # We'll time it
        import time
        start_time = time.time()
        notifs = await client.app.bsky.notification.list_notifications()
        end_time = time.time()
        
        print(f"Notifications fetched in {end_time - start_time:.2f} seconds.")
        print(f"Count: {len(notifs.notifications)}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
