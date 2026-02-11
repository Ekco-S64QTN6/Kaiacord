import sys
import os
from pathlib import Path

# Add project root to sys.path
# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from utils.news.kaia_news import NewsManager


def test_news_manager():
    print("Testing NewsManager...")
    # Use absolute path for base_path to be safe
    base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "knowledge_base", "news")


    nm = NewsManager(base_path=base_path)
    nm.refresh()
    
    print(f"Total items in cache: {sum(len(items) for items in nm.news_cache.values())}")
    for cat, items in nm.news_cache.items():
        print(f"Category '{cat}': {len(items)} items")
    
    # Verify that items are strings and not dicts (common parsing error)
    for cat, items in nm.news_cache.items():
        for item in items:
            if not isinstance(item.get('text'), str):
                print(f"❌ Error: Item in category '{cat}' has non-string text: {type(item.get('text'))}")
                sys.exit(1)
            if item.get('text').startswith('{'):
                print(f"❌ Error: Item in category '{cat}' looks like a stringified dict: {item.get('text')[:50]}...")
                sys.exit(1)
            
            # Check for excluded content
            excluded_keywords = ['Reuters', 'The Record', 'BleepingComputer', 'Financial Times', '404 Media']
            if item.get('text') in excluded_keywords:
                print(f"❌ Error: Found excluded source '{item.get('text')}' in category '{cat}'")
                sys.exit(1)
                
    print("\nTesting get_news('culture')...")
    news = nm.get_news('culture', limit=5)
    if not news:
        print(f"❌ Error: get_news('culture') returned 0 items")
        sys.exit(1)
    else:
        print(f"✅ get_news('culture') correctly returned {len(news)} items.")

    print("\nTesting get_news('hacker')...")
    news = nm.get_news('hacker', limit=5)
    print(f"Got {len(news)} hacker news items")
    for i, item in enumerate(news, 1):
        print(f"{i}. [{item.get('date')}] {item.get('text')[:100]}...")

    print("\n✅ All news manager tests passed.")
if __name__ == "__main__":
    test_news_manager()
