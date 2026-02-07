import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.getcwd()))

from utils.news.kaia_news import NewsManager

def test_parsing():
    print("🔍 Testing NewsManager parsing...")
    manager = NewsManager()
    manager.refresh()
    
    found_any = False
    for category, items in manager.news_cache.items():
        if items:
            print(f"✅ Found {len(items)} items in category: {category}")
            for item in items[:2]:
                print(f"  - [{item['date']}] {item['text'][:100]}...")
            found_any = True
    
    if not found_any:
        print("❌ No news items found in cache!")
    else:
        print("✨ News cache populated successfully.")

if __name__ == "__main__":
    test_parsing()
