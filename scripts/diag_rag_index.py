import os
import asyncio
from utils.core.kaia_rag import KaiaRAG

async def diag():
    rag = KaiaRAG()
    target_files = [
        os.path.abspath("knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260209.txt")
    ]
    
    print("\n--- RAG DIAGNOSTICS REFINED ---")
    index = rag.indices.get('logs')
    print(f"Total nodes in 'logs' index: {len(index.docstore.docs)}")
    
    # Print sample node metadata to check keys
    if index.docstore.docs:
        first_node = list(index.docstore.docs.values())[0]
        print(f"Sample node metadata: {first_node.metadata.keys()}")
        print(f"Sample node file_path: {first_node.metadata.get('file_path')}")
        print(f"Sample node itype: {first_node.metadata.get('itype')}")

    for tf in target_files:
        print(f"\nTarget File: {tf}")
        # Case insensitive/normalized match attempt
        nodes = [n for n in index.docstore.docs.values() if 
                 n.metadata.get('file_path') and 
                 os.path.abspath(n.metadata.get('file_path')).lower() == tf.lower()]
        
        print(f"  Nodes in index matching path (case-insensitive): {len(nodes)}")
        for n in nodes:
            print(f"    - ID: {n.id_}, Offset: {n.metadata.get('file_offset')}, Length: {n.metadata.get('content_length')}")
            
if __name__ == "__main__":
    asyncio.run(diag())
