import os
import glob
import re

log_dir = "knowledge_base/user_logs"

# Get all user names from directory names
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

def clean_file(file_path, current_user_name):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We want to keep the current user's name and "Kaia"
    # But we want to scrub other user names.
    
    # First, protect the current user's name and Kaia
    protected_placeholder = "___PROTECTED_USER___"
    kaia_placeholder = "___KAIA___"
    
    # Use regex to find current user name (case insensitive)
    # We use \b for word boundaries
    temp_content = re.sub(rf"\b{re.escape(current_user_name)}\b", protected_placeholder, content, flags=re.IGNORECASE)
    temp_content = re.sub(r"\bKaia\b", kaia_placeholder, temp_content, flags=re.IGNORECASE)
    
    # Now scrub other users
    for other_user in all_users:
        if other_user.lower() == current_user_name.lower() or other_user.lower() == "kaia":
            continue
        
        # Replace with "another user" or just strip? 
        # The user said "make sure no other user is mentioned by name".
        # Replacing with "[USER]" or "someone" is safer for context.
        temp_content = re.sub(rf"\b{re.escape(other_user)}\b", "someone", temp_content, flags=re.IGNORECASE)
    
    # Restore protected names
    final_content = temp_content.replace(protected_placeholder, current_user_name)
    final_content = final_content.replace(kaia_placeholder, "Kaia")
    
    if content != final_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        return True
    return False

def main():
    for d in user_dirs:
        current_user_name = d.name.rsplit("_", 1)[0].replace("_", " ")
        print(f"Cleaning logs for {current_user_name}...")
        log_files = glob.glob(os.path.join(d.path, "interactions_*.txt"))
        
        cleaned_count = 0
        for log_file in log_files:
            if clean_file(log_file, current_user_name):
                cleaned_count += 1
        
        print(f"  - Cleaned {cleaned_count} files.")

if __name__ == "__main__":
    main()
