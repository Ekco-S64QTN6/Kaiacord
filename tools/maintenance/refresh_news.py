#!/usr/bin/env python3
"""
Script to refresh and populate news database
Run periodically via cron: */30 * * * * cd /path/to/Kaiacord && python tools/refresh_news.py
"""

import asyncio
import sys
import os
import json
import subprocess
from datetime import datetime, timedelta

# Add project root to path (go up 2 levels from tools/maintenance/)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils.kaia_news import NewsManager

async def refresh_news(force_update=False):
    """Refresh all news categories and trigger update if needed"""
    print(f"🔄 Refreshing news at {datetime.now()}")
    
    manager = NewsManager()
    
    # Check if we have recent news
    total_items = sum(len(v) for v in manager.news_cache.values())
    
    # If no news or force_update, run the update script
    if total_items == 0 or force_update:
        print("⚠️ No news found or update forced. Triggering update_kaia_news.py...")
        try:
            # Run update_kaia_news.py
            process = subprocess.run(
                [sys.executable, "tools/maintenance/update_kaia_news.py"],
                capture_output=True,
                text=True,
                check=True
            )
            print("✅ Update script completed successfully.")
            # Re-initialize manager to pick up new files
            manager = NewsManager()
            total_items = sum(len(v) for v in manager.news_cache.values())
        except subprocess.CalledProcessError as e:
            print(f"❌ Update script failed: {e.stderr}")
        except Exception as e:
            print(f"❌ Error running update script: {e}")

    print(f"📰 Loaded {total_items} news items across categories")
    
    categories = [
        "technology",
        "politics", 
        "security",
        "business",
        "science",
        "general"
    ]
    
    for category in categories:
        news = manager.get_news(category=category, limit=10)
        count = len(news) if isinstance(news, list) else 0
        print(f"  📰 {category}: {count} items")
    
    print("✅ News refresh complete")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Refresh Kaia's news database")
    parser.add_argument("--force", action="store_true", help="Force a fresh news update")
    args = parser.parse_args()
    
    asyncio.run(refresh_news(force_update=args.force))
