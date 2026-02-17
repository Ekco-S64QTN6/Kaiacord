import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.social.kaia_forum import get_forum_client

async def debug():
    client = await get_forum_client()
    if not client:
        print("Forum client failure")
        return
    
    print("Scraping Page 1 listing...")
    threads = await client.scrape_forum_listing(page=1)
    for t in threads:
        print(f"[{t.thread_id}] {t.title} (Sticky: {t.is_sticky})")
        if t.thread_id == 434298:
            print(">>> FOUND TARGET THREAD 434298 <<<")

if __name__ == "__main__":
    asyncio.run(debug())
