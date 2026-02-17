import asyncio
import os
from utils.social.kaia_twitter import get_x_client

async def inspect_x_notifs():
    client = await get_x_client()
    if not client:
        print("Failed to get X client")
        return

    print("Fetching mentions notifications...")
    notifs = await client.get_notifications('Mentions')
    
    print(f"Found {len(notifs)} notifications")
    for i, notif in enumerate(notifs[:5]):
        print(f"\n--- Notification {i} ---")
        print(f"Type: {type(notif)}")
        print(f"Attributes: {dir(notif)}")
        
        tweet = getattr(notif, 'tweet', notif)
        print(f"Tweet type: {type(tweet)}")
        print(f"Tweet attributes: {dir(tweet)}")
        
        if hasattr(tweet, 'id'):
            print(f"ID: {tweet.id}")
            print(f"Text: {tweet.text}")
            print(f"In reply to: {getattr(tweet, 'in_reply_to_status_id', 'N/A')}")
            # Many unofficial clients use conversation_id for root
            print(f"Conversation ID: {getattr(tweet, 'conversation_id', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(inspect_x_notifs())
