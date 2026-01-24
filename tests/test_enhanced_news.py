import asyncio
import sys
import os

# Add project root to path
sys.path.append('/home/ekco/github/Kaiacord')

from utils.enhanced_news_integration import EnhancedNewsHandler

async def test_enhanced_news():
    print("Testing EnhancedNewsHandler...")
    handler = EnhancedNewsHandler()
    
    categories = ["technology", "politics", "security", "general"]
    
    for category in categories:
        print(f"\n📰 Fetching {category} news...")
        news = await handler.fetch_news(category, limit=3)
        print(f"✅ Got {len(news)} items")
        
        formatted = handler.format_news_items(news, category)
        print(f"📝 Formatted output preview:\n{formatted[:200]}...")

if __name__ == "__main__":
    asyncio.run(test_enhanced_news())
