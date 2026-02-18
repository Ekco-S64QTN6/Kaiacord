import sys
import os
import re
import asyncio

# Add project root to sys.path
sys.path.append(os.getcwd())

from utils.core.response_filter import BotSpeakFilter
from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_action, log_error

async def clean_logs():
    project_root = os.getcwd()
    log_dirs = [
        os.path.join(project_root, "knowledge_base", "user_logs"),
        os.path.join(project_root, "knowledge_base", "kaia_dreams")
    ]
    
    cleaned_files = []

    for log_dir in log_dirs:
        if not os.path.exists(log_dir):
            log_warning(f"Directory not found: {log_dir}")
            continue

        log_action(f"Scanning {os.path.basename(log_dir)} for conversational bait...")
        
        for root, _, files in os.walk(log_dir):
            for file in files:
                if file.endswith((".md", ".txt")) and ("interactions" in file or "dream" in file):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                            lines = f.readlines()
                        
                        original_content = "".join(lines)
                        new_lines = []
                        modified = False
                        
                        for line in lines:
                            # Only clean Kaia's responses
                            if "Kaia:" in line:
                                parts = line.split("Kaia:", 1)
                                prefix = parts[0]
                                content = parts[1]
                                # Apply the hardening filter to remove bait
                                cleaned_content = BotSpeakFilter.strip_bot_speak(content)
                                
                                if cleaned_content != content.strip():
                                    if not cleaned_content.strip():
                                        # If the entire line was bait, we might want to skip it 
                                        # or replace it with something neutral. 
                                        log_info(f"Removed full-bait response in {file}")
                                        modified = True
                                        continue
                                    else:
                                        log_info(f"Cleaned bait from line in {file}")
                                        line = f"{prefix}Kaia: {cleaned_content}\n"
                                        modified = True
                            
                            new_lines.append(line)
                        
                        if modified:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.writelines(new_lines)
                            cleaned_files.append(file_path)
                            log_success(f"Cleaned and saved: {file}")
                            
                    except Exception as e:
                        log_error(f"Failed to process {file_path if 'file_path' in locals() else 'unknown'}: {e}")

    if cleaned_files:
        log_action(f"Cleaned {len(cleaned_files)} files. Now forcing RAG re-index...")
        
        # Initialize RAG
        rag = KaiaRAG()
        await rag.initialize_async()
        
        # We need to manually prune the nodes for these files to force a full re-index
        # because logs use tail-indexing by default.
        updated_itypes = set()
        
        for file_path in cleaned_files:
            abs_path = os.path.abspath(file_path)
            for itype, index in rag.indices.items():
                # Find nodes matching this file
                nodes_to_delete = [
                    node_id for node_id, node in index.docstore.docs.items()
                    if node.metadata.get('file_path') == file_path or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
                ]
                
                if nodes_to_delete:
                    log_info(f"Deleting {len(nodes_to_delete)} nodes for {os.path.basename(file_path)} from {itype} index")
                    for node_id in nodes_to_delete:
                        index.delete_nodes([node_id])
                    updated_itypes.add(itype)
        
        if updated_itypes:
            # Persist the deletions
            rag._persist_updated_indices(updated_itypes)
            
            # Now trigger a refresh to re-index the cleaned files from scratch
            log_action("Triggering RAG refresh to re-index cleaned logs...")
            # We need to bypass the _refresh_lock or wait for it
            await asyncio.to_thread(rag.refresh_knowledge_base)
            log_success("RAG re-indexing complete.")
    else:
        log_info("No files found that required cleaning.")

if __name__ == "__main__":
    asyncio.run(clean_logs())
