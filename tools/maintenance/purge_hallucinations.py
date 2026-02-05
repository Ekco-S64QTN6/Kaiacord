import os
import re
import sys

# Add project root to path for imports
sys.path.append(os.getcwd())

from utils.infrastructure.logging.kaia_logger import log_success, log_info, log_action

def purge_cheese():
    """Surgically remove 'cheese situation in China' and related hallucinations from logs."""
    search_dirs = ["knowledge_base/user_logs", "memory"]
    patterns = [
        r"\bcheese\b"
    ]
    # We skip the "lioness crouching" one as that seemed like a legitimate (if weird) user conversation
    
    count = 0
    for root_dir in search_dirs:
        if not os.path.exists(root_dir):
            continue
            
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith((".txt", ".md", ".json")):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        new_content = content
                        for pattern in patterns:
                            # Replace matching lines or sentences with neutral text or remove them
                            lines = new_content.split('\n')
                            filtered_lines = []
                            for line in lines:
                                if re.search(pattern, line, re.IGNORECASE):
                                    # log_info(f"Purging match from {file_path}: {line[:50]}...")
                                    count += 1
                                    continue # Skip this line
                                filtered_lines.append(line)
                            new_content = '\n'.join(filtered_lines)
                        
                        if new_content != content:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(new_content)
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")

    print(f"Purged {count} entries from logs and memory.")

if __name__ == "__main__":
    purge_cheese()
