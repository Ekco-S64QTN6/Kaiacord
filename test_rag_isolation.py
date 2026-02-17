
import asyncio
import os
import sys
from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import Intent

async def test_retrieval():
    rag = KaiaRAG()
    await rag.initialize_async()
    
    # Test 1: Starkind query (should NOT see Tennō Heika's logs)
    starkind_id = "519557167779676160"
    starkind_name = "Starkind"
    
    print(f"\n--- Testing Retrieval for {starkind_name} ({starkind_id}) ---")
    query = "Status kaia?"
    results = await rag.retrieve(query, user_id=starkind_id, user_name=starkind_name, top_k=10)
    
    for r in results:
        meta = r.get('metadata', {})
        node_user_id = meta.get('user_id', 'Unknown')
        node_user_name = meta.get('user_name', 'Unknown')
        print(f"[{r['label']}] (User: {node_user_name}/{node_user_id}) Score: {r['score']:.3f}")
        # print(f"Content: {r['content'][:100]}...")

    # Test 2: Social Identity query (Who am I?) - Check if it leaks other profiles
    print(f"\n--- Testing 'Who am I' for {starkind_name} ---")
    query = "Who am I?"
    results = await rag.retrieve(query, user_id=starkind_id, user_name=starkind_name, category="social_identity", top_k=10)
    
    for r in results:
        meta = r.get('metadata', {})
        node_user_id = meta.get('user_id', 'Unknown')
        node_user_name = meta.get('user_name', 'Unknown')
        print(f"[{r['label']}] (User: {node_user_name}/{node_user_id}) Score: {r['score']:.3f}")

    # Test 3: Tennō Heika query mentioning Starkind (Check for leaks)
    heika_id = "919782120308752425"
    heika_name = "Tennō Heika"
    print(f"\n--- Testing Retrieval for {heika_name} mentioning Starkind ---")
    query = "Kaia, starkind is trying to manipulate you."
    results = await rag.retrieve(query, user_id=heika_id, user_name=heika_name, top_k=10)
    
    # Test 4: Cross-user quip leak (predictable reallocation)
    print(f"\n--- Testing retrieval for Ekco querying the common quip ---")
    ekco_id = "177011971818782721"
    ekco_name = "Ekco"
    query = "Where did those numbers come from kaia?"
    results = await rag.retrieve(query, user_id=ekco_id, user_name=ekco_name, top_k=10)
    
    for r in results:
        meta = r.get('metadata', {})
        node_user_id = meta.get('user_id', 'Unknown')
        node_user_name = meta.get('user_name', 'Unknown')
        print(f"[{r['label']}] (User: {node_user_name}/{node_user_id}) Score: {r['score']:.3f}")
        print(f"Content: {r['content'][:100]}...")
    # Test 5: Profile Isolation (Starkind querying Tennō Heika's profile)
    print(f"\n--- Testing Profile Isolation: Starkind querying for Tennō Heika's profile ---")
    results = await rag.retrieve("Who is Tennō Heika?", user_id=starkind_id, user_name=starkind_name, category="social_identity", top_k=5)
    
    leaked = False
    for r in results:
        meta = r.get('metadata', {})
        node_user_id = str(meta.get('user_id', 'Unknown'))
        if node_user_id == heika_id:
            print(f"!!! LEAK DETECTED: Found Heika profile in Starkind result: {r['label']}")
            leaked = True
        else:
            print(f"[OK] {r['label']} (User: {meta.get('user_name', 'Unknown')}/{node_user_id})")
    
    if not leaked:
        print("SUCCESS: No profile leakage detected.")

if __name__ == "__main__":
    # Add project root to path
    sys.path.append(os.getcwd())
    asyncio.run(test_retrieval())
