import asyncio
import sys
import os
import re
from pathlib import Path

# Mock dependencies
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.kaia_rag import KaiaRAG
from utils.core.knowledge_boundary import KnowledgeBoundary

async def final_verification():
    print("=== FINAL VERIFICATION ===")
    
    # 1. Verify Knowledge Boundary
    print("\n--- 1. Knowledge Boundary Check ---")
    kb = KnowledgeBoundary()
    test_query = "User: Initializing KaiaRAG... [23:28:27] SUCCESS: Populated 659 valid indexed files. Semantic Blindness in Neuromancer and Hagakure. Predictable Rigidity in Verification. Detected unknown entities: ['Initializing', 'Populated']"
    result = kb.check_known_entities(test_query, "I am Kaia.")
    print(f"Entities found: {result['query_entities']}")
    print(f"Unknown entities: {result['unknown_in_context']}")
    if not result['unknown_in_context']:
        print("✅ PASS: All log noise filtered out.")
    else:
        print("❌ FAIL: Still detecting noise.")

    # 2. Verify RAG Lore Recall
    print("\n--- 2. RAG Lore Recall Check ---")
    rag = KaiaRAG()
    # Explicitly clear cache to ensure we use the new tokenization
    rag.bm25_cache.clear()
    
    queries = [
        "Who are Tessier and Ashpool?",
        "Who are Tessier-Ashpool?",
        "Molly Millions"
    ]
    
    for query in queries:
        print(f"\nSearching for: '{query}'")
        results = rag.retrieve(query, category='knowledge', top_k=3)
        print(f"✅ Found {len(results)} nodes.")
        for i, res in enumerate(results):
            source = res['metadata'].get('file_path', 'Unknown')
            print(f"  [{i}] Score: {res['score']:.4f} | Source: {os.path.basename(source)}")
            if "Neuromancer" in source:
                print(f"  ✅ SUCCESS: Found Neuromancer match!")

    # 3. Verify Log Integrity
    print("\n--- 3. Log Integrity Check ---")
    log_path = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260212.md"
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            content = f.read()
            if "Tessier-Ashpool. Right." in content:
                print("❌ FAIL: Hallucinated response still present in logs.")
            else:
                print("✅ PASS: Hallucinated response purged.")
            if "Initializing KaiaRAG" in content:
                print("❌ FAIL: Terminal noise still present in logs.")
            else:
                print("✅ PASS: Terminal noise purged.")

if __name__ == "__main__":
    asyncio.run(final_verification())
