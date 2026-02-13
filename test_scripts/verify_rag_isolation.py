import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.kaia_rag import KaiaRAG
from utils.social.kaia_identities import registry

def verify_isolation():
    rag = KaiaRAG()
    
    starkind_id = "519557167779676160"
    brad_id = "Identity_Brad_Shovel"
    
    print(f"\n1. Testing RAG retrieval for Starkind ({starkind_id})...")
    # Using a query that might have high general knowledge overlap
    results = rag.retrieve("Are we allowed to like AI art?", user_id=starkind_id)
    
    print(f"Retrieved {len(results)} nodes.")
    for i, node in enumerate(results):
        meta = node.get('metadata', {})
        fp = meta.get('file_path', '')
        score = node.get('score', 0.0)
        print(f"  {i+1}. [{score:.3f}] {fp}")
        if "Ekco_177011971818782721" in fp:
            print(f"❌ LEAK: Found Ekco's logs in Starkind's results!")

    print(f"\n2. Testing RAG retrieval for linked identity {brad_id}...")
    # Specifically asking for shovelquest context
    results = rag.retrieve("What did Shovelquest say in the forums about computers?", user_id=brad_id)
    
    print(f"Retrieved {len(results)} nodes.")
    found_shovel = False
    for i, node in enumerate(results):
        meta = node.get('metadata', {})
        fp = meta.get('file_path', '')
        score = node.get('score', 0.0)
        print(f"  {i+1}. [{score:.3f}] {fp}")
        if "shovelquest" in fp.lower() or "202089" in fp:
            found_shovel = True
            
    if found_shovel:
        print("✅ PASS: Correctly retrieved Shovelquest's logs for BradZax identity.")
    else:
        print("❌ FAIL: Could not retrieve Shovelquest's logs for BradZax identity.")

if __name__ == "__main__":
    verify_isolation()
