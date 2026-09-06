import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

# Import the core components to test
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import QueryClassifier, ContextOptimizer
from utils.core.message_processor import NEWS_AUTO_TRIGGER_ENABLED
from utils.core.response_filter import EmergencyContaminationFilter

async def test_conversational_variety():
    print("\n--- Starting Conversational Smoke Tests ---\n")
    
    rag = KaiaRAG()
    classifier = QueryClassifier()
    optimizer = ContextOptimizer()
    
    test_cases = [
        {
            "user": "ekco",
            "query": "hey kaia, how are you today?",
            "expected_news": False,
            "category": "personal/casual"
        },
        {
            "user": "ekco",
            "query": "what's new in the world?",
            "expected_news": True,
            "category": "news"
        },
        {
            "user": "ekco",
            "query": "who am i and what have we talked about?",
            "expected_news": False,
            "category": "identity/history"
        }
    ]
    
    for case in test_cases:
        print(f"Testing Query: {case['query']}")
        
        # 1. Classification
        category = await classifier.classify(case['query'])
        print(f"  - Category: {category}")
        
        # 2. Retrieval Logic (Mimicking Kaiacord.py split)
        is_news_query = NEWS_AUTO_TRIGGER_ENABLED and (category == 'news' or any(word in case['query'].lower() for word in ['news', 'what\'s new', 'whats new']))
        
        print(f"  - Is News Query: {is_news_query}")
        
        # Retrieve results
        results = await asyncio.to_thread(
            rag.retrieve, 
            case['query'], 
            include_news=is_news_query # This is the fix we implemented
        )
        
        # Check for news in results
        detected_news = any("News:" in str(res) or "Latest News:" in str(res) for res in results)
        
        if is_news_query == case['expected_news']:
            print(f"  ✅ News Retrieval: {is_news_query} (Matches expectation)")
        else:
            print(f"  ❌ News Retrieval: {is_news_query} (Does NOT match expectation: {case['expected_news']})")
            
        print(f"  - Results Found: {len(results)}")
        for i, res in enumerate(results[:2]):
            # Snippet of result
            snippet = str(res)[:100].replace('\n', ' ')
            print(f"    [{i}] {snippet}...")
            
    print("\n--- Smoke Test Completed ---\n")

if __name__ == "__main__":
    asyncio.run(test_conversational_variety())
