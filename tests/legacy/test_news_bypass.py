import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append('/home/ekco/github/Kaiacord')

from utils.kaia_intelligence_fixed import FixedQueryClassifier
from utils.fast_news import FastNewsRetriever

async def test_classifier():
    print("Testing FixedQueryClassifier...")
    classifier = FixedQueryClassifier(timeout=2.0)
    
    # Test rule-based
    res = await classifier.classify("kaia whats the news")
    print(f"Rule-based result: {res}")
    assert res == "news" or res == "general" # Depending on exact regex match
    
    # Test timeout (mocking the sync client would be ideal, but we can just rely on the timeout)
    # This might actually call the model if we don't mock, but it should respect timeout
    print("Testing timeout (this might take a few seconds)...")
    res = await classifier.classify("tell me a story about a dragon")
    print(f"Model/Timeout result: {res}")

def test_fast_news():
    print("\nTesting FastNewsRetriever...")
    retriever = FastNewsRetriever()
    
    # Test categorization
    tech_news = retriever.get_news_by_category("technology")
    print(f"Tech news count: {len(tech_news)}")
    if tech_news:
        print(f"Sample: {tech_news[0]}")
        
    # Test fallback
    random_news = retriever.get_news_by_category("nonexistent_category")
    print(f"Fallback news count: {len(random_news)}")

if __name__ == "__main__":
    asyncio.run(test_classifier())
    test_fast_news()
