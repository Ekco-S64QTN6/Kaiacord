import os
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.response_filter import BotSpeakFilter

def sanitize_file(file_path, dry_run=True):
    """Sanitize a single markdown file of roleplay actions."""
    content = file_path.read_text(encoding='utf-8', errors='replace')
    
    # We apply the same hardening logic as used in live responses
    cleaned = BotSpeakFilter.harden(content)
    
    if content != cleaned:
        if not dry_run:
            file_path.write_text(cleaned, encoding='utf-8')
        return True
    return False

def main():
    kb_dir = Path(__file__).parent.parent / "knowledge_base" / "user_logs"
    dry_run = "--fix" not in sys.argv
    
    print(f"Scanning {kb_dir}...")
    if dry_run:
        print("DRY RUN MODE - no changes will be saved. Use --fix to apply.")
    
    count = 0
    fixed = 0
    
    # Recursively find all .md files
    for md_file in kb_dir.rglob("*.md"):
        count += 1
        if sanitize_file(md_file, dry_run=dry_run):
            fixed += 1
            status = "[FIXED]" if not dry_run else "[WOULD FIX]"
            print(f"{status} {md_file.relative_to(kb_dir.parent.parent)}")
            
    print(f"\nFinished scanning {count} files.")
    print(f"Modified {fixed} files.")

if __name__ == "__main__":
    main()
