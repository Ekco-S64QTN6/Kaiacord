import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

async def test_retrieval():
    rag = KaiaRAG()
    
    # Test cases: (query, user_id, user_name)
    test_cases = [
        ("Who is Gwaihir?", "519557167779676160", "Starkond the Prion"),
        ("Is NPC in Chief trustworthy?", "519557167779676160", "Starkond the Prion"),
        ("Who am I?", "519557167779676160", "Starkond the Prion"),
        ("Tell me about Starkond the Prion", "470028550951403531", "Gwaihir the Wizend"),
        ("What do you know about Reiwa?", "519557167779676160", "Starkond the Prion"),
    ]
    
    for query, u_id, u_name in test_cases:
        print(f"\n--- Testing Query: '{query}' (User: {u_name}) ---")
        results = rag.retrieve(query, user_id=u_id, user_name=u_name)
        
        for i, res in enumerate(results):
            print(f"Result {i}: {res[:150]}...")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
