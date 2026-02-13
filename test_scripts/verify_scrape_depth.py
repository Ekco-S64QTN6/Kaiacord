import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Add project root to path
sys.path.append(os.getcwd())

from utils.commands.forum_handler import _handle_scrape
from utils.social.kaia_forum import ThreadInfo

async def test_scrape_depth():
    print("--- Testing Forum Scrape Depth Logic ---")
    
    # Mock Context
    ctx = MagicMock()
    msg = MagicMock()
    # User command: !forum scrape 50
    msg.content = "!forum scrape 50"
    msg.channel.send = AsyncMock()
    
    # Mock Forum Client
    client = MagicMock()
    client.scrape_forum_listing = AsyncMock()
    client.scrape_thread = AsyncMock()
    client.is_thread_update_needed = MagicMock(return_value=True)
    
    # Generate mock threads for multiple pages
    page1_threads = [ThreadInfo(thread_id=i, title=f"Thread {i}", is_sticky=False, reply_count=1) for i in range(1, 21)]
    page2_threads = [ThreadInfo(thread_id=i, title=f"Thread {i}", is_sticky=False, reply_count=1) for i in range(21, 41)]
    page3_threads = [ThreadInfo(thread_id=i, title=f"Thread {i}", is_sticky=False, reply_count=1) for i in range(41, 61)]
    
    client.scrape_forum_listing.side_effect = [page1_threads, page2_threads, page3_threads]
    client.scrape_thread.return_value = {'thread_id': 1, 'posts': [{'author': 'bot', 'content': 'test'}]}
    
    with patch('utils.social.kaia_forum.get_forum_client', AsyncMock(return_value=client)):
        await _handle_scrape(ctx, msg)
        
    # Verify calls
    listing_calls = client.scrape_forum_listing.call_count
    print(f"Forum listing scraped {listing_calls} times.")
    
    scraped_threads_count = client.scrape_thread.call_count
    print(f"Individual threads scraped: {scraped_threads_count}")
    
    # We requested 50, so it should scrape 3 pages (20 + 20 + 10)
    if listing_calls == 3:
        print("✅ SUCCESS: Scraped 3 pages for target of 50 threads.")
    else:
        print(f"❌ FAILURE: Expected 3 listing scrapes, got {listing_calls}")
        
    if scraped_threads_count == 50:
        print("✅ SUCCESS: Attempted to scrape 50 individual threads.")
    else:
        print(f"❌ FAILURE: Expected 50 thread scrapes, got {scraped_threads_count}")

if __name__ == "__main__":
    asyncio.run(test_scrape_depth())
