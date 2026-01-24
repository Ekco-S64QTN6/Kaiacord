import os
import sys
import asyncio
import argparse

# Add parent directory to path so we can import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_rag import KaiaRAG

async def purge_logs(rag):
    print("Purging all user log nodes from index...")
    nodes_to_delete = []
    purged_files = set()

    # Access the 'logs' index specifically if it exists, otherwise check all
    indices_to_check = rag.indices.values()
    
    for index in indices_to_check:
        for node_id, node in index.docstore.docs.items():
            file_path = node.metadata.get('file_path', '')
            if "user_logs" in file_path:
                nodes_to_delete.append(node_id)
                purged_files.add(os.path.abspath(file_path))
        
        if nodes_to_delete:
            print(f"Deleting {len(nodes_to_delete)} nodes from index...")
            index.delete_nodes(nodes_to_delete)
            nodes_to_delete = [] # Reset for next index

    # Clear indexed_files entries
    for file_path in purged_files:
        if file_path in rag.indexed_files:
            del rag.indexed_files[file_path]
            
    rag.persist(force=True)
    print(f"✓ Purged nodes from {len(purged_files)} files. They will be re-indexed on next boot.")

async def refresh(rag):
    print("Refreshing Knowledge Base...")
    rag.refresh_knowledge_base()
    rag.persist(force=True)
    print("✓ RAG refresh and persistence complete.")

async def main():
    parser = argparse.ArgumentParser(description="RAG Maintenance Tools")
    parser.add_argument("--purge-logs", action="store_true", help="Purge user logs from index")
    parser.add_argument("--refresh", action="store_true", help="Force refresh of knowledge base")
    args = parser.parse_args()

    if not (args.purge_logs or args.refresh):
        print("Please specify an action: --purge-logs or --refresh")
        return

    rag = KaiaRAG()

    if args.purge_logs:
        await purge_logs(rag)
    
    if args.refresh:
        await refresh(rag)

if __name__ == "__main__":
    asyncio.run(main())
