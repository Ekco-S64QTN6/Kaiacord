import asyncio
import os
import sys
import threading
import time

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from utils.core.kaia_rag import KaiaRAG


async def test_single_query(rag):
    print("\n--- Testing Single Query ---")
    query = "Tell me about Starkond the Prion"
    print(f"Query: '{query}'")
    results = rag.retrieve(query, user_id="470028550951403531", user_name="Gwaihir the Wizend")
    
    if results:
        print(f"✓ Retrieved {len(results)} results.")
        print(f"Top result: {results[0][:100]}...")
    else:
        print("✗ No results found.")

async def test_retrieval_rank(rag):
    print("\n--- Testing Retrieval Rank ---")
    query = "Tell me about Starkond the Prion"
    
    # Simulate enrichment logic
    query_lower = query.lower()
    known_users = []
    user_logs_path = os.path.join(rag.knowledge_base_dir, "user_logs")
    if os.path.exists(user_logs_path):
        for d in os.scandir(user_logs_path):
            if d.is_dir() and "_" in d.name:
                u_name = d.name.rsplit("_", 1)[0].replace("_", " ")
                known_users.append(u_name)
    
    detected_user = None
    for u_name in known_users:
        if u_name.lower() in query_lower:
            detected_user = u_name
            break
            
    enriched_query = query
    if detected_user:
        enriched_query = f"{query} user:{detected_user}"
    
    print(f"Enriched Query: '{enriched_query}'")
    
    # Use knowledge index for general ranking test
    retriever = rag.indices['knowledge'].as_retriever(similarity_top_k=10)
    nodes = retriever.retrieve(enriched_query)
    
    found = False
    for i, node_result in enumerate(nodes):
        node = node_result.node
        file_path = node.metadata.get('file_path', '')
        if 'Starkond' in file_path and 'user_profile.md' in file_path:
            print(f"✓ FOUND target profile at rank {i}! Score: {node_result.score:.4f}")
            found = True
            break
            
    if not found:
        print("✗ Target profile not found in top 10.")

def test_concurrency():
    print("\n--- Testing Concurrency (Threaded) ---")
    # Create a fresh RAG instance for threading test to avoid async loop conflicts
    rag = KaiaRAG()
    stop_event = threading.Event()
    
    def retrieval_worker():
        count = 0
        while not stop_event.is_set():
            try:
                rag.retrieve("Who is Kaia?")
                count += 1
            except Exception as e:
                print(f"!!! Retrieval error: {e}")
            time.sleep(0.1)
        print(f"Retrieval worker completed {count} ops.")
            
    def persistence_worker():
        count = 0
        while not stop_event.is_set():
            try:
                rag.persist(force=True)
                count += 1
            except Exception as e:
                print(f"!!! Persistence error: {e}")
            time.sleep(0.5)
        print(f"Persistence worker completed {count} ops.")

    t1 = threading.Thread(target=retrieval_worker)
    t2 = threading.Thread(target=persistence_worker)
    
    t1.start()
    t2.start()
    
    time.sleep(3)
    stop_event.set()
    t1.join()
    t2.join()
    print("✓ Concurrency test complete.")

async def main():
    print("=== Running RAG System Tests ===")
    rag = KaiaRAG()
    
    await test_single_query(rag)
    await test_retrieval_rank(rag)
    
    # Run concurrency test last as it uses threads
    test_concurrency()
    
    print("\n=== All RAG Tests Completed ===")

if __name__ == "__main__":
    asyncio.run(main())
