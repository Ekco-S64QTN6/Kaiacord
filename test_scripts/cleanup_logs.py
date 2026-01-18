import os
import re
import glob

log_dir = "knowledge_base/user_logs"

def cleanup_all_logs():
    if not os.path.exists(log_dir):
        print(f"Directory {log_dir} not found.")
        return

    # Find all interaction log files
    log_files = glob.glob(os.path.join(log_dir, "**", "interactions_*.txt"), recursive=True)

    for log_file in log_files:
        print(f"Cleaning {log_file}...")
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Split by the separator, keeping the separator
        blocks = re.split(r'(--- \d{8}_\d{6} ---)', content)

        new_content = []
        if blocks[0].strip():
            new_content.append(blocks[0])

        removed_count = 0
        for i in range(1, len(blocks), 2):
            sep = blocks[i]
            block_content = blocks[i+1]
            
            # Check if this block should be removed
            # We remove it if the User line contains "who am i" or "who are you"
            user_line_match = re.search(r'User \(.*?\): (.*)', block_content, re.IGNORECASE)
            if user_line_match:
                query = user_line_match.group(1).lower()
                if "who am i" in query or "who are you" in query:
                    removed_count += 1
                    continue
                    
            new_content.append(sep)
            new_content.append(block_content)

        if removed_count > 0:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("".join(new_content))
            print(f"✓ Removed {removed_count} bad interactions from {log_file}")
        else:
            print(f"No bad interactions found in {log_file}")

    print("Global log cleanup complete.")

if __name__ == "__main__":
    cleanup_all_logs()
