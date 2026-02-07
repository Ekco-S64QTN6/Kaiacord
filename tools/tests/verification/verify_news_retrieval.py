import sys
import os
import asyncio

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from kaia_rag import KaiaRAG

async def verify_news_retrieval():
    rag = KaiaRAG()
    
    # Test queries for different days in the last week
    test_queries = [
        "What happened in tech on January 15th 2026?",
        "Any security incidents from Jan 18 2026?",
        "What was the tech landscape like on January 20th?",
    ]
    
    for query in test_queries:
        print(f"\n🔍 Query: {query}")
        results = rag.retrieve(query, top_k=3)
        if results:
            print(f"✅ Found {len(results)} relevant nodes.")
            for i, res in enumerate(results):
                print(f"--- Result {i+1} ---")
                print(res[:200] + "...")
        else:
            print("❌ No results found.")

if __name__ == "__main__":
    asyncio.run(verify_news_retrieval())
