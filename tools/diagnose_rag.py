import asyncio
import sys
import os
import re
from pathlib import Path

# Mock dependencies
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.kaia_rag import KaiaRAG, SimpleBM25Retriever, HybridRetriever

async def debug_hybrid():
    print("Initializing KaiaRAG for deep debug...")
    try:
        rag = KaiaRAG()
        # Initialize the indices first so they actually exist in memory
        await rag.initialize_async()
        
        index = rag.indices.get('knowledge')
        if not index:
            print("❌ 'knowledge' index not found.")
            return

        # Explicitly build BM25 retriever for 'knowledge'
        docs = list(index.storage_context.docstore.docs.values())
        print(f"Found {len(docs)} documents/nodes in docstore.")
        
        if not docs:
            print("❌ Docstore is empty!")
            return

        # Test tokenization on a specific node if possible
        # Test tokenization on a specific node if possible
        neuromancer_nodes = [n for n in docs if "aquarium" in n.metadata.get('file_path', '').lower()]
        print(f"Found {len(neuromancer_nodes)} nodes for Aquarium.")
        if neuromancer_nodes:
            sample_text = neuromancer_nodes[0].get_content()
            print(f"Sample snippet: {sample_text[:100]}...")
            # Check tokenizer
            def _tokenize(text):
                return re.sub(r'[^\w\s]', ' ', text.lower()).split()
            tokens = _tokenize(sample_text)
            print(f"Tokenized snippet (first 10): {tokens[:10]}")
            if "aquarium" in tokens or any("aquarium" in t for t in tokens):
                print("✅ Found 'aquarium' in tokens.")
            else:
                print("❌ 'aquarium' NOT found in tokens.")

        bm25_retriever = SimpleBM25Retriever(docs)
        hybrid = HybridRetriever(index, bm25_retriever)

        queries = [
            "Kaia have you had a chance to take a look at the aquarium research for kaia file?",
            "Aquarium research for Kaia",
            "What makes a good planted tank?"
        ]

        for query in queries:
            print(f"\n--- Debugging Query: '{query}' ---")
            
            # 1. Check Vector Retrieval results
            v_retriever = index.as_retriever(similarity_top_k=10)
            v_results = await v_retriever.aretrieve(query)
            print(f"  Vector found {len(v_results)} nodes.")
            for i, res in enumerate(v_results[:3]):
                print(f"    V[{i}] Score: {res.score:.4f} | Source: {res.node.metadata.get('file_path','')}")

            # 2. Check BM25 Retrieval results
            b_results = bm25_retriever.retrieve(query, top_k=10)
            print(f"  BM25 found {len(b_results)} nodes.")
            for i, (node, score) in enumerate(b_results[:3]):
                print(f"    B[{i}] Score: {score:.4f} | Source: {node.metadata.get('file_path','')}")

            # 3. Check Hybrid RRF results
            h_results = await hybrid.retrieve(query, top_k=5)
            print(f"  Hybrid (RRF scaled) found {len(h_results)} nodes.")
            for i, res in enumerate(h_results):
                print(f"    H[{i}] RRF Scaled Score: {res.score:.4f} | Source: {res.node.metadata.get('file_path','')}")
                if res.score < 0.70:
                    print(f"      ⚠️ WOULD BE FILTERED (Threshold 0.70)")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_hybrid())
