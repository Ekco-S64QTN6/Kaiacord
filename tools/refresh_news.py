#!/usr/bin/env python3
"""
Script to refresh and populate news database
Run periodically via cron: */30 * * * * cd /path/to/Kaiacord && python scripts/refresh_news.py
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.enhanced_news_integration import EnhancedNewsHandler

async def refresh_news():
    """Refresh all news categories"""
    print(f"🔄 Refreshing news at {datetime.now()}")
    
    handler = EnhancedNewsHandler()
    
    categories = [
        "technology",
        "politics", 
        "security",
        "business",
        "science",
        "general"
    ]
    
    all_news = {}
    
    for category in categories:
        print(f"  📰 Fetching {category} news...")
        try:
            news = await handler.fetch_news(category, limit=10)
            all_news[category] = news
            print(f"    ✅ Got {len(news) if isinstance(news, list) else 1} items")
        except Exception as e:
            print(f"    ❌ Error: {e}")
    
    # Save to knowledge base
    output_dir = "./knowledge_base/news/daily"
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_file = os.path.join(output_dir, f"news_{timestamp}.json")
    
    with open(output_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "categories": all_news
        }, f, indent=2)
    
    print(f"💾 Saved to {output_file}")
    
    # Keep only last 7 days of files
    cleanup_old_files(output_dir, days=7)
    
    print("✅ News refresh complete")

def cleanup_old_files(directory, days=7):
    """Clean up old news files"""
    import time
    cutoff = time.time() - (days * 86400)
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.getmtime(filepath) < cutoff:
            os.remove(filepath)
            print(f"  🗑️ Removed old file: {filename}")

if __name__ == "__main__":
    asyncio.run(refresh_news())
