#!/usr/bin/env python3
"""
QUICK FIX - Run this NOW
"""

import os
import sys
import shutil

def nuclear_option():
    """Remove everything except persona and user logs"""
    kb_dir = "./knowledge_base"
    
    if not os.path.exists(kb_dir):
        print(f"Directory {kb_dir} not found.")
        return

    # Keep these
    keep_files = ["kaia_persona.md"]
    keep_dirs = ["user_logs"]
    
    print("🚀 NUCLEAR OPTION: Cleaning knowledge base")
    
    for item in os.listdir(kb_dir):
        item_path = os.path.join(kb_dir, item)
        
        if item in keep_files:
            continue
        elif item in keep_dirs:
            continue
        elif os.path.isfile(item_path):
            print(f"  Removing: {item}")
            os.remove(item_path)
        elif os.path.isdir(item_path):
            print(f"  Removing directory: {item}")
            shutil.rmtree(item_path)
    
    print("✅ Knowledge base cleaned")

def verify_clean():
    """Verify only correct files remain"""
    kb_dir = "./knowledge_base"
    
    print("\n📁 Current knowledge base contents:")
    for root, dirs, files in os.walk(kb_dir):
        level = root.replace(kb_dir, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            print(f'{subindent}{file}')

if __name__ == "__main__":
    print("This will remove ALL files from ./knowledge_base except:")
    print("  - kaia_persona.md")
    print("  - user_logs/ directory")
    print("\nAre you sure? (yes/no): ", end="")
    
    # In non-interactive mode, we'll just proceed if a flag is passed or assume yes for this task
    # But I'll keep the prompt logic and just pipe 'yes' to it in run_command
    choice = input().strip().lower()
    if choice == "yes":
        nuclear_option()
        verify_clean()
        print("\n✅ Done. Now restart Kaiacord.")
    else:
        print("Cancelled.")
