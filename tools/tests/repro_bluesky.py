import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
from atproto import AsyncClient
from datetime import datetime, timezone, timedelta

async def test_bluesky():
    load_dotenv()
    handle = os.getenv("BLUESKY_HANDLE")
    password = os.getenv("BLUESKY_APP_PASSWORD")
    
    print(f"Attempting login as {handle}...")
    try:
        from utils.social.kaia_bluesky import get_bluesky_client
        
        # Test 1: Initial login
        client = await get_bluesky_client()
        if client:
            print("Login successful!")
        
        # Test 2: Force new login
        print("Testing force_new login...")
        client2 = await get_bluesky_client(force_new=True)
        if client2:
            print("Force login successful!")
            
        print("Fetching notifications...")
        notifs = await client2.app.bsky.notification.list_notifications()
        print(f"Fetched {len(notifs.notifications)} notifications.")
        
        for notif in notifs.notifications:
            print(f"--- Notification: {notif.reason} from {notif.author.handle} ---")
            if notif.reason in ['mention', 'reply']:
                print(f"ID: bsky:{notif.uri}")
                try:
                    # Match bot logic:
                    # 1. Access record
                    record = notif.record
                    print(f"Record type: {type(record)}")
                    
                    # 2. Access reply/root
                    reply_attr = getattr(record, 'reply', None)
                    print(f"Reply attr: {reply_attr}")
                    
                    root = getattr(reply_attr, 'root', None)
                    print(f"Root: {root}")
                    
                    root_uri = root.uri if root and hasattr(root, 'uri') else notif.uri
                    print(f"Root URI: {root_uri}")
                    
                    # 3. Access text
                    text = getattr(record, 'text', '')
                    print(f"Text: {text[:50]}")
                    
                except Exception as loop_e:
                    print(f"Loop Error: {loop_e}")
                    import traceback
                    traceback.print_exc()
            
    except Exception as e:
        print(f"Main Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_bluesky())
