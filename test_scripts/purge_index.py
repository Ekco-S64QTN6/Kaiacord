import os
import sys

# Add parent directory to path so we can import kaia_rag
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kaia_rag import KaiaRAG

def purge_user_logs():
    rag = KaiaRAG()
    print("Purging all user log nodes from index...")

    nodes_to_delete = []
    purged_files = set()

    for node_id, node in rag.index.docstore.docs.items():
        file_path = node.metadata.get('file_path', '')
        if "user_logs" in file_path:
            nodes_to_delete.append(node_id)
            purged_files.add(os.path.abspath(file_path))

    if nodes_to_delete:
        print(f"Deleting {len(nodes_to_delete)} nodes across {len(purged_files)} files...")
        for node_id in nodes_to_delete:
            rag.index.delete_nodes([node_id])
        
        # Clear the indexed_files entries to force a full re-index for these files
        for file_path in purged_files:
            if file_path in rag.indexed_files:
                del rag.indexed_files[file_path]
            
        rag.persist(force=True)
        print("✓ All user log nodes purged and persisted. They will be re-indexed on next boot.")
    else:
        print("No user log nodes found in index.")

if __name__ == "__main__":
    purge_user_logs()
