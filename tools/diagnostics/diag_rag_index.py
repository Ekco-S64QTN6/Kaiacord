import os
import sys
sys.path.append(os.getcwd())
import asyncio
from utils.core.kaia_rag import KaiaRAG

async def diag():
    rag = KaiaRAG()
    await rag.initialize_async()
    
    print("\n--- RAG DIAGNOSTICS REFINED ---")
    
    # Show stats for all indices
    for itype, index in rag.indices.items():
        print(f"\n--- Index: {itype} ---")
        print(f"  Total nodes: {len(index.docstore.docs)}")
        if index.docstore.docs:
            sample = list(index.docstore.docs.values())[0]
            print(f"  Sample metadata keys: {list(sample.metadata.keys())}")
            print(f"  Sample file_path: {sample.metadata.get('file_path', 'N/A')}")
            
if __name__ == "__main__":
    asyncio.run(diag())
