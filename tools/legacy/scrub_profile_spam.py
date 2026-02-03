import os
import re
import shutil
from datetime import datetime

LOG_DIR = "knowledge_base/user_logs"
BACKUP_DIR = "memory/backups/logs_pre_scrub_" + datetime.now().strftime("%Y%m%d_%H%M%S")

# Patterns to remove
SCRUB_PATTERNS = [
    r'^USER PROFILE:.*$',
    r'^## USER PROFILE:.*$',
    r'^QUICK REFERENCE.*$',
    r'^HOW TO INTERACT WITH THEM.*$',
    r'^SHARED HISTORY & CONTEXT.*$',
    r'^THEIR INTERESTS & EXPERTISE.*$',
    r'^CONVERSATION STYLE NOTES.*$',
    r'^RELATIONSHIP STATUS WITH KAIA.*$',
    r'^POTENTIAL TRIGGERS & SENSITIVITIES.*$',
    r'^GROWTH OPPORTUNITIES.*$',
    r'^Updated personalization for.*$',
    r'^\[optimized: saved \d+ tokens\].*$',
    r'^💾 .*$', # Cached responses indicator
]

def scrub_logs():
    if not os.path.exists(LOG_DIR):
        print(f"❌ Log directory {LOG_DIR} not found.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f"📂 Created backup directory: {BACKUP_DIR}")

    total_files = 0
    total_lines_removed = 0

    for root, dirs, files in os.walk(LOG_DIR):
        for file in files:
            if file.startswith("interactions_") and file.endswith(".txt"):
                file_path = os.path.join(root, file)
                
                # Create backup
                rel_path = os.path.relpath(file_path, LOG_DIR)
                backup_path = os.path.join(BACKUP_DIR, rel_path)
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(file_path, backup_path)

                # Scrub file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()

                new_lines = []
                lines_removed_in_file = 0
                
                # Simple line-by-line scrubbing for metadata
                # For profile blocks, we might need more complex logic if they span multiple lines
                # But usually they are prefixed with headers
                
                in_profile_block = False
                
                for line in lines:
                    stripped = line.strip()
                    
                    # Check for profile headers
                    if re.match(r'^USER PROFILE:|^## USER PROFILE:', stripped):
                        in_profile_block = True
                        lines_removed_in_file += 1
                        continue
                    
                    # If in block, check if we should exit (e.g., next message or empty line after block)
                    # This is a bit tricky, but let's look for common metadata/headers
                    if in_profile_block:
                        if re.match(r'^\[\d{4}-\d{2}-\d{2}|^--- \d{8}|^User \(|^Kaia:', stripped):
                            in_profile_block = False
                        else:
                            lines_removed_in_file += 1
                            continue
                    
                    # Check for other single-line patterns
                    should_skip = False
                    for pattern in SCRUB_PATTERNS:
                        if re.match(pattern, stripped):
                            should_skip = True
                            break
                    
                    if should_skip:
                        lines_removed_in_file += 1
                        continue
                    
                    new_lines.append(line)

                if lines_removed_in_file > 0:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    print(f"✅ Scrubbed {file_path}: Removed {lines_removed_in_file} lines.")
                    total_files += 1
                    total_lines_removed += lines_removed_in_file

    print(f"\n✨ Cleanup complete!")
    print(f"📊 Files modified: {total_files}")
    print(f"📊 Total lines removed: {total_lines_removed}")
    print(f"💾 Backups available in: {BACKUP_DIR}")

if __name__ == "__main__":
    scrub_logs()
