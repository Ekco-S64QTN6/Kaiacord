import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.infrastructure.system.yaml_config import config

def check_health():
    print("--- RAG Indexing Health Check ---")
    
    knowledge_base_dir = config.knowledge_base_dir
    persist_dir = config.persist_dir
    manifest_path = os.path.join(persist_dir, "file_manifest.json")
    
    if not os.path.exists(manifest_path):
        print(f"❌ Manifest not found at {manifest_path}")
        return

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print(f"Loaded manifest with {len(manifest)} entries.")
    
    # Files on disk
    disk_files = {}
    supported_exts = [".pdf", ".txt", ".md", ".docx"]
    
    for root, _, files in os.walk(knowledge_base_dir):
        if "corrupt_files" in root: continue
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in supported_exts:
                full_path = os.path.abspath(os.path.join(root, file))
                disk_files[full_path] = {
                    "mtime": os.path.getmtime(full_path),
                    "size": os.path.getsize(full_path)
                }
    
    print(f"Found {len(disk_files)} supported files on disk.")
    
    # 1. Files in manifest but missing from disk
    missing_on_disk = []
    for path in manifest:
        if path not in disk_files:
            missing_on_disk.append(path)
            
    # 2. Files on disk but missing from manifest
    not_indexed = []
    # 3. Files on disk but modified since indexing
    outdated = []
    
    for path, info in disk_files.items():
        if path not in manifest:
            not_indexed.append(path)
        else:
            entry = manifest[path]
            # Handle both old (mtime only) and new (dict) manifest formats
            if isinstance(entry, dict):
                m_mtime = entry.get("mtime", 0)
                m_size = entry.get("size", 0)
                if info["mtime"] > m_mtime or (m_size > 0 and info["size"] != m_size):
                    outdated.append(path)
            else:
                # Legacy format: entry is just mtime
                if info["mtime"] > entry:
                    outdated.append(path)

    print(f"\nSummary:")
    print(f"✅ Indexed and Up-to-date: {len(disk_files) - len(not_indexed) - len(outdated)}")
    print(f"❌ Not Indexed: {len(not_indexed)}")
    print(f"🔄 Outdated (Modified): {len(outdated)}")
    print(f"⚠️  Missing from disk (stale manifest): {len(missing_on_disk)}")
    
    if not_indexed:
        print("\n--- Not Indexed Files (Top 10) ---")
        for f in not_indexed[:10]:
            print(f"  - {os.path.relpath(f, os.getcwd())}")
        if len(not_indexed) > 10:
            print(f"  ... and {len(not_indexed) - 10} more.")
            
    if outdated:
        print("\n--- Outdated Files (Top 10) ---")
        for f in outdated[:10]:
            print(f"  - {os.path.relpath(f, os.getcwd())}")
        if len(outdated) > 10:
            print(f"  ... and {len(outdated) - 10} more.")

if __name__ == "__main__":
    check_health()
