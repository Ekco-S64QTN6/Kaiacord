import os
import re
from pathlib import Path

# Paths to clean
LOGS_DIR = Path("/home/ekco/github/Kaiacord/knowledge_base/user_logs")

# Patterns to remove
PATTERNS = [
    r"hydroponics lab",
    r"automated irrigation",
    r"fungal infestation",
    r"nutrient balance"
]

def clean_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    modified = False
    # Split into entries (Kaia: ... or User: ...)
    entries = re.split(r'(Kaia:|User:)', content)
    
    cleaned_entries = []
    # entries[0] is everything before first speaker tag
    cleaned_entries.append(entries[0])
    
    for i in range(1, len(entries), 2):
        speaker = entries[i]
        text = entries[i+1]
        
        has_hallucination = any(re.search(p, text, re.IGNORECASE) for p in PATTERNS)
        
        if has_hallucination:
            print(f"Purging hallucination from {file_path}")
            # Replace the text after the speaker with a placeholder if it's Kaia
            if speaker == "Kaia:":
                text = " [EXCISED HALLUCINATION]\n"
            else:
                # If it's a user query that triggered it, we might want to keep it or excise it too
                # Let's excise if it contains the patterns too
                text = " [EXCISED HALLUCINATION TRIGGER]\n"
            modified = True
        
        cleaned_entries.append(speaker + text)
    
    if modified:
        new_content = "".join(cleaned_entries)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    return False

def main():
    if not LOGS_DIR.exists():
        print(f"Directory {LOGS_DIR} does not exist.")
        return

    count = 0
    for file_path in LOGS_DIR.rglob("*.txt"):
        if clean_file(file_path):
            count += 1
    
    print(f"Cleaned {count} files.")

if __name__ == "__main__":
    main()
