
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action
from llama_index.core import Document

def main():
    rag = KaiaRAG()
    
    # The file we just sanitized
    target_file = "knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260209.md"
    if not os.path.exists(target_file):
        target_file = "knowledge_base/user_logs/Ekco_177011971818782721/interactions_20260208.txt"
    
    abs_path = os.path.abspath(target_file)
    
    if not os.path.exists(target_file):
        print(f"File not found: {target_file}")
        return

    log_action(f"Force-syncing RAG for {target_file}...")
    
    itype = 'logs'
    target_index = rag.indices[itype]
    
    # 1. Purge ALL nodes for this file
    nodes_to_delete = [
        node_id for node_id, node in target_index.docstore.docs.items()
        if node.metadata.get('file_path') == target_file or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
    ]
    
    if nodes_to_delete:
        log_info(f"Deleting {len(nodes_to_delete)} old nodes...")
        for node_id in nodes_to_delete:
            target_index.delete_nodes([node_id])
    
    # 2. Re-index the FULL content (bypassing tail-indexing)
    log_info(f"Re-indexing full file content...")
    with open(target_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.strip():
        doc = Document(
            text=content,
            metadata={
                "file_path": abs_path,
                "last_modified_at": os.path.getmtime(abs_path),
                "file_offset": 0,
                "content_length": len(content),
                "source": "user_logs"
            }
        )
        rag._apply_priority_metadata(doc, itype, target_file)
        parser = rag._get_node_parser_for_doc(itype, target_file)
        nodes = parser.get_nodes_from_documents([doc])
        target_index.insert_nodes(nodes)
        
        # Update indexed_files map to prevent refresh_knowledge_base from thinking it's different
        rag.indexed_files[abs_path] = os.path.getmtime(abs_path)
        
        log_success(f"Successfully re-indexed {len(nodes)} new nodes.")

    # 3. Persist
    rag.persist(force=True)
    log_success("RAG index synchronization complete.")

if __name__ == "__main__":
    main()
