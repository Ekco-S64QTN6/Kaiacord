import os
import re
import shutil

log_path = "/home/ekco/github/Kaiacord/logs/kaiacord.log"
repo_root = "/home/ekco/github/Kaiacord"
source_dir = os.path.join(repo_root, "knowledge_base", "kaia_dreams", "other")
interactions_dir = os.path.join(repo_root, "knowledge_base", "kaia_dreams", "interactions")

os.makedirs(interactions_dir, exist_ok=True)
os.makedirs(os.path.join(repo_root, "knowledge_base", "Books"), exist_ok=True)
os.makedirs(os.path.join(repo_root, "knowledge_base", "documents"), exist_ok=True)
os.makedirs(os.path.join(repo_root, "knowledge_base", "news"), exist_ok=True)
os.makedirs(os.path.join(repo_root, "knowledge_base", "deep_dive_reports"), exist_ok=True)

# Find all original paths from the log
original_paths = {}

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        match = re.search(r'ERROR: Failed to load file \./knowledge_base/(.*?): this model does not support embeddings', line)
        if match:
            rel_path = match.group(1)
            full_original_path = os.path.join(repo_root, "knowledge_base", rel_path)
            basename = os.path.basename(rel_path)
            original_paths[basename] = full_original_path

count = 0
if os.path.exists(source_dir):
    for filename in os.listdir(source_dir):
        src_path = os.path.join(source_dir, filename)
        if not os.path.isfile(src_path):
            continue
            
        dest_path = None
        
        # Check if we have its original path logged
        if filename in original_paths:
            dest_path = original_paths[filename]
            # Override for dreams to enforce they go to interactions/
            if "kaia_dreams" in dest_path and filename.startswith("dream_"):
                dest_path = os.path.join(interactions_dir, filename)
        else:
            # Fallback heuristics
            if filename.startswith("dream_"):
                dest_path = os.path.join(interactions_dir, filename)
            elif re.match(r"^\d{4}-\d{2}-\d{2}", filename):
                dest_path = os.path.join(repo_root, "knowledge_base", "news", filename)
            else:
                dest_path = os.path.join(repo_root, "knowledge_base", "documents", filename)
    
        if src_path != dest_path:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(src_path, dest_path)
            count += 1
            print(f"Moved {filename} -> {os.path.relpath(os.path.dirname(dest_path), repo_root)}")

print(f"Total files restored/moved: {count}")
