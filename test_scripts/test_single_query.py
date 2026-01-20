import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

async def test_single():
    rag = KaiaRAG()
    query = "Tell me about Starkond the Prion"
    print(f"\n--- Testing Query: '{query}' ---")
    results = rag.retrieve(query, user_id="470028550951403531", user_name="Gwaihir the Wizend")
    
    for i, res in enumerate(results):
        print(f"Result {i}: {res[:300]}...")

if __name__ == "__main__":
    asyncio.run(test_single())
