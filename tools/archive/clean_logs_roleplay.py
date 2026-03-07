import os
import re

def clean_file(filepath):
    """Remove roleplay markers (asterisks and parentheses) from a file."""
    if not os.path.isfile(filepath):
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Remove *actions*
    # Using a cautious regex to avoid stripping everything if there are unpaired asterisks
    cleaned = re.sub(r'\*.*?\*', '', content)
    
    # Remove (actions)
    # Again, cautious regex
    cleaned = re.sub(r'\(.*?\)', '', cleaned)
    
    # Clean up any triple spaces or empty lines created by stripping
    cleaned = re.sub(r'  +', ' ', cleaned)
    
    if cleaned != content:
        print(f"Cleaned {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(cleaned)
    else:
        # print(f"No changes needed for {filepath}")
        pass

def main():
    base_dir = "knowledge_base/user_logs"
    if not os.path.exists(base_dir):
        print(f"Directory {base_dir} does not exist.")
        return

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".txt") or file.endswith(".md"):
                clean_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
