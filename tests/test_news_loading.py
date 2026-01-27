import sys
import os
sys.path.append(os.getcwd())
from utils.kaia_news import NewsManager

def test_news_loading():
    manager = NewsManager()
    print(f"Base path: {manager.base_path}")
    print(f"Categories in cache: {list(manager.news_cache.keys())}")
    total = sum(len(items) for items in manager.news_cache.values())
    print(f"Total items: {total}")
    
    for cat, items in manager.news_cache.items():
        print(f"  - {cat}: {len(items)} items")
        if items:
            print(f"    Example: {items[0]['text'][:50]}...")

if __name__ == "__main__":
    test_news_loading()
