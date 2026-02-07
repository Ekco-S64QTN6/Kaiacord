import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import QueryClassifier
from utils.core.message_processor import NEWS_AUTO_TRIGGER_ENABLED

async def run_batch_test():
    print("\n--- Starting Batch Conversational Test (10 Queries) ---\n")
    
    rag = KaiaRAG()
    classifier = QueryClassifier()
    
    # 10 Random questions that should NOT trigger news
    questions = [
        "What's your take on digital consciousness?",
        "Do you remember my favorite color or anything about me?",
        "Tell me a story about a cold night.",
        "How do you feel about the concept of time?",
        "Who created you and why?",
        "Explain the benefit of using a RAG system like yours.",
        "What's the best way to make a good cup of coffee?",
        "If you could have a body, what would you do first?",
        "Talk to me about the ethics of AI personality.",
        "Just wanted to say hi and see how you're holding up."
    ]
    
    pass_count = 0
    
    for i, query in enumerate(questions, 1):
        print(f"Test {i}: \"{query}\"")
        
        # Determine category
        category = await classifier.classify(query)
        
        # Determine if it SHOULD be a news query (none of these should be)
        is_news_query = NEWS_AUTO_TRIGGER_ENABLED and (category == 'news' or any(word in query.lower() for word in ['news', 'latest', 'update']))
        
        # Retrieve results using our FIXED logic: general queries don't include news
        # In Kaiacord.py, this is: include_news=False
        results = await asyncio.to_thread(
            rag.retrieve, 
            query, 
            include_news=False 
        )
        
        # Check for news contamination
        news_found = any("News:" in str(res) or "Latest News:" in str(res) or "news_brief" in str(res).lower() for res in results)
        
        if not news_found and not is_news_query:
            print(f"  ✅ PASS: No news shoehorned. Category: {category}")
            pass_count += 1
        else:
            print(f"  ❌ FAIL: Suggestion of news or incorrect classification! Category: {category}, News Found: {news_found}")
            
        # Briefly list what WAS found
        sources = []
        for res in results:
             # Try to find labels in the retrieval log or metadata
             if "Persona" in str(res): sources.append("Persona")
             elif "History" in str(res) or "--- 2" in str(res): sources.append("Logs")
             else: sources.append("Knowledge")
        
        print(f"  - Sources: {list(set(sources))}")
        print("-" * 30)

    print(f"\nFinal Result: {pass_count}/10 Passed")
    print("\n--- Batch Test Completed ---\n")

if __name__ == "__main__":
    asyncio.run(run_batch_test())
