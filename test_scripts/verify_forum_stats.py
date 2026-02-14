import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.social.kaia_forum import get_forum_client
from dotenv import load_dotenv

async def test_stats():
    load_dotenv()
    client = await get_forum_client()
    if not client:
        print("Forum client not configured.")
        return

    print("Calculating global forum stats...")
    stats = await client.get_global_stats()
    
    print("\nGlobal Forum Statistics:")
    print(f"  Total Threads Scraped: {stats['total_threads']}")
    print(f"  Total Posts Collected: {stats['total_posts']}")
    print(f"  Total Users Indexed: {stats['total_users']}")
    print(f"  Profiles Generated: {stats['total_profiles']}")
    print(f"  Disk Usage: {stats['disk_usage_mb']:.2f} MB")
    print(f"  Last Listing Thread Count: {stats['last_listing_count']}")

if __name__ == "__main__":
    asyncio.run(test_stats())
