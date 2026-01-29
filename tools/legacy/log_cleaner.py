import os
import glob
import re
import argparse
from typing import List

LOG_DIR = "knowledge_base/user_logs"

def get_all_users(log_dir: str) -> List[str]:
    """Get all user names from directory names."""
    if not os.path.exists(log_dir):
        return []
        
    user_dirs = [d for d in os.scandir(log_dir) if d.is_dir()]
    all_users = []
    for d in user_dirs:
        name = d.name.rsplit("_", 1)[0].replace("_", " ")
        all_users.append(name)
        # Add parts of the name for better matching
        parts = name.split()
        if len(parts) > 1:
            all_users.extend(parts)

    # Add specific names that appeared in logs but might not be in dir names
    all_users.extend(["Gwaihir", "Reiwa", "Starkond", "Starkind", "The un-nameable one"])

    # Unique and sorted by length (longest first) to avoid partial matches
    all_users = sorted(list(set(all_users)), key=len, reverse=True)
    # Remove very short names that might cause false positives
    all_users = [u for u in all_users if len(u) > 3]
    return all_users

def clean_names(file_path: str, current_user_name: str, all_users: List[str]) -> bool:
    """Scrub other user names from the log file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # First, protect the current user's name and Kaia
    protected_placeholder = "___PROTECTED_USER___"
    kaia_placeholder = "___KAIA___"
    
    # Use regex to find current user name (case insensitive)
    temp_content = re.sub(rf"\b{re.escape(current_user_name)}\b", protected_placeholder, content, flags=re.IGNORECASE)
    temp_content = re.sub(r"\bKaia\b", kaia_placeholder, temp_content, flags=re.IGNORECASE)
    
    # Now scrub other users
    for other_user in all_users:
        if other_user.lower() == current_user_name.lower() or other_user.lower() == "kaia":
            continue
        temp_content = re.sub(rf"\b{re.escape(other_user)}\b", "someone", temp_content, flags=re.IGNORECASE)
    
    # Restore protected names
    final_content = temp_content.replace(protected_placeholder, current_user_name)
    final_content = final_content.replace(kaia_placeholder, "Kaia")
    
    if content != final_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        return True
    return False

def remove_noise(file_path: str) -> int:
    """Remove noisy system lines from the log file."""
    patterns_to_remove = [
        r"\[IDLE_QUIP:.*?\]",
        r"\[REMEMBER_COMMAND\]:.*",
        r"- IDENTITY RESONANCE:.*",
        r"- \[KAIA_PERSONA_FRAGMENT\].*",
        r"IDENTITY RESONANCE:.*",
        r"\[KAIA_PERSONA_FRAGMENT\].*",
        r"NARRATIVE AUTONOMY:.*",
        r"\[HISTORICAL_CONTEXT\].*",
        r"\[CRITICAL_RULES\].*",
        r"\[END_CONTEXT\].*",
        r"\[USER_PROFILE_AND_HISTORY:.*?\]"
    ]
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    removed_count = 0
    for line in lines:
        should_remove = False
        for pattern in patterns_to_remove:
            if re.search(pattern, line):
                should_remove = True
                break
        
        if not should_remove:
            new_lines.append(line)
        else:
            removed_count += 1
    
    if removed_count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
            
    return removed_count

def main():
    parser = argparse.ArgumentParser(description="Clean user logs of noise and other user names.")
    parser.add_argument("--names", action="store_true", help="Scrub other user names")
    parser.add_argument("--noise", action="store_true", help="Remove system noise lines")
    parser.add_argument("--all", action="store_true", help="Do both")
    args = parser.parse_args()

    if not (args.names or args.noise or args.all):
        args.all = True

    print(f"Scanning {LOG_DIR}...")
    if not os.path.exists(LOG_DIR):
        print("Log directory not found.")
        return

    all_users = get_all_users(LOG_DIR)
    user_dirs = [d for d in os.scandir(LOG_DIR) if d.is_dir()]

    for d in user_dirs:
        current_user_name = d.name.rsplit("_", 1)[0].replace("_", " ")
        print(f"Processing logs for {current_user_name}...")
        log_files = glob.glob(os.path.join(d.path, "interactions_*.txt"))
        
        for log_file in log_files:
            if args.names or args.all:
                if clean_names(log_file, current_user_name, all_users):
                    print(f"  - Scrubbed names in {os.path.basename(log_file)}")
            
            if args.noise or args.all:
                removed = remove_noise(log_file)
                if removed > 0:
                    print(f"  - Removed {removed} noisy lines in {os.path.basename(log_file)}")

if __name__ == "__main__":
    main()
