import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.news.kaia_news import NewsManager

def check_cache():
    manager = NewsManager()
    total_items = sum(len(v) for v in manager.news_cache.values())
    print(f"Total news items in cache: {total_items}")
    for cat, items in manager.news_cache.items():
        print(f"  {cat}: {len(items)} items")

if __name__ == "__main__":
    check_cache()
