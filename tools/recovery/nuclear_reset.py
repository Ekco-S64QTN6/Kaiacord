"""
NUCLEAR RESET: Remove ALL contaminated logs and start fresh
"""

import os
import shutil
import re
from datetime import datetime
from pathlib import Path

def nuclear_clean_user_logs():
    """Completely clean ALL user logs of hallucinated content"""
    log_dir = Path("./knowledge_base/user_logs")
    
    if not log_dir.exists():
        print("❌ User logs directory not found")
        return 0, 0
    
    # Create backup directory
    backup_dir = log_dir.parent / "user_logs_backup_nuclear"
    backup_dir.mkdir(exist_ok=True)
    
    # Hallucination patterns to remove COMPLETELY
    hallucination_patterns = [
        "elena", "juanita", "deane", "bonbons", "agency",
        "university network", "behind the curtain", "slow burn",
        "roundabout questions", "internal comms", "terrier with a scent",
        "i remember a conversation with", "back in", "she said",
        "think tank", "middle eastern affairs"
    ]
    
    total_cleaned = 0
    total_removed = 0
    
    for user_folder in log_dir.iterdir():
        if not user_folder.is_dir():
            continue
            
        user_name = user_folder.name.split('_')[0]
        print(f"\n🔍 Processing: {user_name}")
        
        # Backup the entire folder
        backup_path = backup_dir / f"{user_folder.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not backup_path.exists():
            shutil.copytree(user_folder, backup_path)
            print(f"  ✓ Backed up to: {backup_path.name}")
        
        log_files = list(user_folder.glob("interactions_*.txt"))
        
        for log_file in log_files:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Split into blocks based on "User (" or "Kaia:" or "Got response:"
            # We want to keep the delimiters
            blocks = re.split(r'(?=User \(|Kaia:|Got response:)', content)
            
            cleaned_blocks = []
            file_changed = False
            
            for block in blocks:
                if not block.strip():
                    cleaned_blocks.append(block)
                    continue
                
                # Check if this is a Kaia response
                is_kaia = block.startswith("Kaia:") or block.startswith("Got response:")
                
                if is_kaia:
                    # Check for hallucinations
                    block_lower = block.lower()
                    has_hallucination = any(pattern in block_lower for pattern in hallucination_patterns)
                    
                    if has_hallucination:
                        print(f"  ✂️  Removing hallucinated block in {log_file.name}")
                        file_changed = True
                        # Instead of removing the whole block, let's just remove the hallucinated lines
                        # to keep as much context as possible, OR just remove the whole block if it's safer.
                        # The user said "Nuclear", so let's remove the whole block.
                        continue
                
                cleaned_blocks.append(block)
            
            if file_changed:
                cleaned_content = "".join(cleaned_blocks)
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_content)
                total_cleaned += 1
                print(f"  ✓ Cleaned: {log_file.name}")
            
            # If file is now empty or too small, remove it
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                final_content = f.read()
            if len(final_content.strip()) < 100:
                log_file.unlink()
                total_removed += 1
                print(f"  ✂️  Removed (too small): {log_file.name}")
    
    return total_cleaned, total_removed

def create_fresh_persona_response():
    """Create a clean, non-hallucinated response template"""
    clean_template = """yeah. what's up.

coffee's getting cold again. server's humming. cat's judging me from the bookshelf.
logs are... existent. always something to fix.

what do you need?"""
    
    # Save to knowledge base as a clean reference
    ref_path = Path("./knowledge_base/clean_reference.md")
    ref_path.write_text(clean_template, encoding='utf-8')
    
    return clean_template

def reset_all_profiles():
    """Delete and regenerate all user profiles"""
    log_dir = Path("./knowledge_base/user_logs")
    
    if not log_dir.exists():
        return

    for user_folder in log_dir.iterdir():
        if not user_folder.is_dir():
            continue
        
        profile_path = user_folder / "user_profile.md"
        if profile_path.exists():
            profile_path.unlink()
            print(f"✓ Removed profile: {user_folder.name}")
        
        analysis_path = user_folder / "profile_analysis.json"
        if analysis_path.exists():
            analysis_path.unlink()

def clean_rag_index():
    """Remove all RAG indices and force rebuild"""
    storage_dirs = [
        Path("./memory/rag_storage"),
        Path("./vector_store"),
        Path("./index_store")
    ]
    
    for storage_dir in storage_dirs:
        if storage_dir.exists():
            shutil.rmtree(storage_dir)
            print(f"✓ Removed: {storage_dir}")
    
    # Create fresh storage
    Path("./memory/rag_storage").mkdir(exist_ok=True)

def main():
    print("☢️  NUCLEAR RESET - COMPLETE SYSTEM CLEAN")
    print("=" * 60)
    
    # Check for environment variable to skip confirmation
    if os.getenv("CONFIRM_NUCLEAR") == "TRUE":
        confirm = "NUCLEAR"
    else:
        confirm = input("\nType 'NUCLEAR' to confirm: ").strip()
        
    if confirm != "NUCLEAR":
        print("❌ Cancelled.")
        return
    
    print("\n🚀 Starting nuclear reset...")
    
    # 1. Clean user logs
    print("\n1. Cleaning user logs...")
    cleaned, removed = nuclear_clean_user_logs()
    print(f"   ✓ Cleaned: {cleaned} files")
    print(f"   ✓ Removed: {removed} files (too small)")
    
    # 2. Create clean response template
    print("\n2. Creating clean response template...")
    create_fresh_persona_response()
    print("   ✓ Created clean_reference.md")
    
    # 3. Reset profiles
    print("\n3. Resetting user profiles...")
    reset_all_profiles()
    print("   ✓ All profiles removed")
    
    # 4. Clean RAG index
    print("\n4. Cleaning RAG indices...")
    clean_rag_index()
    print("   ✓ All indices removed")
    
    # 5. Clean cache
    print("\n5. Cleaning semantic cache...")
    cache_files = ["semantic_cache.json", "cache.db", "rag_cache.pkl"]
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print(f"   ✓ Removed: {cache_file}")
    
    print("\n" + "=" * 60)
    print("✅ NUCLEAR RESET COMPLETE")

if __name__ == "__main__":
    main()
