import asyncio
import sys
import os
from pathlib import Path

# Mock dependencies
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.kaia_rag import KaiaRAG

async def diagnose_embeddings():
    print("Initializing KaiaRAG...")
    try:
        rag = KaiaRAG()
        
        texts = [
            "Tessier-Ashpool is a corporate family from Neuromancer.",
            "The quick brown fox jumps over the lazy dog.",
            "A completely different sentence about space exploration."
        ]

        for text in texts:
            print(f"\n--- Text: '{text}' ---")
            embedding = rag.embed_model.get_text_embedding(text)
            print(f"✅ Dimension: {len(embedding)}")
            print(f"First 5 values: {embedding[:5]}")
            print(f"Sum of absolute values: {sum(abs(x) for x in embedding):.4f}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(diagnose_embeddings())
