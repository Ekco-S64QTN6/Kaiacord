import asyncio
from kaia_rag import KaiaRAG

async def test_recalibration():
    rag = KaiaRAG()
    
    # Test 1: Casual query
    print("\n--- Test 1: Casual Query ---")
    results = await asyncio.to_thread(rag.retrieve, "hey kaia, how's it going?", top_k=5)
    for i, res in enumerate(results):
        print(f"Result {i+1}: {res[:100]}...")
        
    # Test 2: Identity query
    print("\n--- Test 2: Identity Query ---")
    results = await asyncio.to_thread(rag.retrieve, "who am i?", user_id="123", user_name="TestUser", top_k=5)
    for i, res in enumerate(results):
        print(f"Result {i+1}: {res[:100]}...")
        
    # Test 3: Lore query (should have lower priority/higher threshold)
    print("\n--- Test 3: Lore Query ---")
    results = await asyncio.to_thread(rag.retrieve, "tell me about the history of the server", top_k=5)
    for i, res in enumerate(results):
        print(f"Result {i+1}: {res[:100]}...")

if __name__ == "__main__":
    asyncio.run(test_recalibration())
