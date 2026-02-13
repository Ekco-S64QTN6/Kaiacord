import os
import re
from pathlib import Path

def cleanup_youtube_logs():
    print("--- Scrubbing YouTube IDs from Forum Logs ---")
    
    user_logs_dir = Path("./knowledge_base/user_logs")
    if not user_logs_dir.exists():
        print("User logs directory not found.")
        return

    # Pattern for 11-char YouTube-like IDs (standalone or as list item)
    # Matches: "- PSl_3IVyWqw", "  PSl_3IVyWqw", "PSl_3IVyWqw"
    yt_pattern = re.compile(r'^(\s*-?\s*)([a-zA-Z0-9_-]{11})(\s*)$')
    
    files_updated = 0
    lines_removed = 0

    for md_file in user_logs_dir.rglob("*.md"):
        content = md_file.read_text(encoding='utf-8', errors='replace')
        lines = content.split('\n')
        
        filtered_lines = []
        file_changed = False
        
        for line in lines:
            if yt_pattern.match(line):
                file_changed = True
                lines_removed += 1
                continue
            filtered_lines.append(line)
        
        if file_changed:
            md_file.write_text('\n'.join(filtered_lines), encoding='utf-8')
            files_updated += 1
            print(f"  Cleaned: {md_file.relative_to(user_logs_dir)}")

    print(f"\nSummary:")
    print(f"  Files updated: {files_updated}")
    print(f"  Lines removed: {lines_removed}")
    print("--- Cleanup Complete ---")

if __name__ == "__main__":
    cleanup_youtube_logs()
