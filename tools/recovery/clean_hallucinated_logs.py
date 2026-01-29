import os
import re
import shutil
from datetime import datetime

# Define the patterns to clean
CLEAN_PATTERNS = [
    r'elara vance',
    r'aurora labs',
    r'aurora project',
    r'kael drakkel',
    r'xylarite',
    r'stonecutters',
    r'crimson hand',
    r'elena',
    r'juanita',
    r'deane',
    r'bonbons'
]

USER_LOGS_DIR = "/home/ekco/github/Kaiacord/knowledge_base/user_logs"

def clean_logs():
    print(f"Starting log cleanup at {datetime.now()}")
    
    total_files = 0
    cleaned_files = 0
    total_lines_removed = 0
    
    for root, dirs, files in os.walk(USER_LOGS_DIR):
        for file in files:
            if file.endswith(".txt") and not file.endswith(".backup"):
                file_path = os.path.join(root, file)
                total_files += 1
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                new_lines = []
                lines_removed_in_file = 0
                
                # We need to handle blocks of interactions. 
                # Interactions are separated by --- TIMESTAMP ---
                current_interaction = []
                is_contaminated = False
                
                for line in lines:
                    if line.startswith("--- ") and line.strip().endswith(" ---"):
                        # Process previous interaction
                        if current_interaction:
                            if not is_contaminated:
                                new_lines.extend(current_interaction)
                            else:
                                lines_removed_in_file += len(current_interaction)
                        
                        # Start new interaction
                        current_interaction = [line]
                        is_contaminated = False
                    else:
                        current_interaction.append(line)
                        # Check for contamination
                        line_lower = line.lower()
                        if any(re.search(pattern, line_lower) for pattern in CLEAN_PATTERNS):
                            is_contaminated = True
                
                # Process the last interaction
                if current_interaction:
                    if not is_contaminated:
                        new_lines.extend(current_interaction)
                    else:
                        lines_removed_in_file += len(current_interaction)
                
                if lines_removed_in_file > 0:
                    # Create backup
                    backup_path = file_path + ".hallucination_backup"
                    shutil.copy2(file_path, backup_path)
                    
                    # Write cleaned file
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    
                    print(f"Cleaned {file_path}: removed {lines_removed_in_file} lines. Backup at {backup_path}")
                    cleaned_files += 1
                    total_lines_removed += lines_removed_in_file

    print(f"\nCleanup finished.")
    print(f"Total files scanned: {total_files}")
    print(f"Files cleaned: {cleaned_files}")
    print(f"Total lines removed: {total_lines_removed}")

if __name__ == "__main__":
    clean_logs()
