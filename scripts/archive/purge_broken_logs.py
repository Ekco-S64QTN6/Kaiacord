import os
import sys
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success

def main():
    rag = KaiaRAG()
    
    # Files we want to clear from the RAG index
    target_files = [
        os.path.abspath("knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260209.txt"),
        os.path.abspath("knowledge_base/user_logs/MetroGnowmOSexual_579396554536910859/interactions_20260209.txt")
    ]
    
    log_info(f"Purging nodes for {len(target_files)} files from 'logs' index...")
    
    with rag._lock:
        index = rag.indices.get('logs')
        if not index:
            log_info("Logs index not found.")
            return
            
        nodes_to_delete = []
        for node_id, node in index.docstore.docs.items():
            file_path = node.metadata.get('file_path')
            if file_path and os.path.abspath(file_path) in target_files:
                nodes_to_delete.append(node_id)
        
        if nodes_to_delete:
            log_info(f"Deleting {len(nodes_to_delete)} nodes...")
            index.delete_nodes(nodes_to_delete)
            
            # Persist changes
            index.storage_context.persist(persist_dir=os.path.join(rag.persist_dir, 'logs'))
            log_success(f"Successfully purged {len(nodes_to_delete)} nodes and persisted index.")
        else:
            log_info("No nodes found for the target files.")
            
    # Trigger a refresh to re-index the cleaned files
    log_info("Triggering RAG refresh to re-index cleaned logs...")
    rag.refresh_knowledge_base()
    log_success("Purge complete.")

if __name__ == "__main__":
    main()
