import asyncio
from kaia_rag import KaiaRAG

async def test_retrieval():
    rag = KaiaRAG()
    # Explicitly refresh to index the clean files
    print("Refreshing knowledge base...")
    await asyncio.to_thread(rag.refresh_knowledge_base)
    
    # Ekco's ID from logs: 177011971818782721
    user_id = 177011971818782721
    user_name = "Ekco"
    
    print(f"Testing retrieval for {user_name} ({user_id})...")
    
    # Simulate "Who am I kaia" query
    query = "Who is Ekco?"
    results = await asyncio.to_thread(
        rag.retrieve, 
        query, 
        user_id=user_id, 
        user_name=user_name, 
        top_k=10
    )
    
    print(f"\nResults for '{query}':")
    for i, res in enumerate(results):
        print(f"\n--- Result {i+1} ---\n{res}")

if __name__ == "__main__":
    asyncio.run(test_retrieval())
