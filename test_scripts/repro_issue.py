import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

async def test_repro():
    rag = KaiaRAG()
    
    # Simulate Ekco talking about a general topic
    # Ekco's ID: 177011971818782721
    # Gwaihir's ID: 470028550951403531
    
    query = "what do you think of software?"
    u_id = "177011971818782721"
    u_name = "Ekco"
    
    print(f"\n--- Testing Repro: '{query}' (User: {u_name}, ID: {u_id}) ---")
    results = rag.retrieve(query, user_id=u_id, user_name=u_name)
    
    for i, res in enumerate(results):
        print(f"Result {i}: {res[:200]}...")

if __name__ == "__main__":
    asyncio.run(test_repro())
