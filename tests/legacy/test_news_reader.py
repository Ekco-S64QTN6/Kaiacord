#!/usr/bin/env python3
import sys
sys.path.append('.')

from utils.proper_news_reader import ProperNewsReader

reader = ProperNewsReader()
reader.scan_news_files()

print(f"Found categories: {list(reader.news_cache.keys())}")
print(f"Total items: {sum(len(items) for items in reader.news_cache.values())}")

# Test each category
for category in ['technology', 'politics', 'security', 'business', 'science', 'general']:
    items = reader.get_news_by_category(category, limit=3)
    print(f"\n{category.upper()} ({len(items)} items):")
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item.get('text', 'No text')[:80]}...")
