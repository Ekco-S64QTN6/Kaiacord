import os
import re

def clean_file(filepath):
    """Remove roleplay markers and meta-talk from a file."""
    if not os.path.isfile(filepath):
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # 1. Remove *actions*
    content = re.sub(r'\*.*?\*', '', content)
    
    # 2. Remove (actions or parentheticals)
    content = re.sub(r'\(.*?\)', '', content)
    
    # 3. Remove [actions or technical meta-talk]
    # Be careful with [brackets] as they might be used for other things, 
    # but in these logs they often represent meta-talk or injected context.
    # We'll target common roleplay/meta patterns in brackets.
    content = re.sub(r'\[(a )?(long |dry |slight )?(pause|chuckle|sigh|thought|reflection|action|note).*?\]', '', content, flags=re.IGNORECASE)
    
    # 4. Remove specific roleplay phrases that might not be in markers
    roleplay_phrases = [
        r"kaia looks up from her desk",
        r"kaia leans back",
        r"kaia taps her pen",
        r"kaia sighs",
        r"kaia chuckles",
    ]
    for phrase in roleplay_phrases:
        content = re.sub(phrase, '', content, flags=re.IGNORECASE)

    # 5. Clean up any weird spacing or empty lines
    content = re.sub(r'  +', ' ', content)
    # Remove lines that were just roleplay and are now empty (or just have "Kaia: ")
    lines = content.split('\n')
    new_lines = []
    for line in lines:
        stripped = line.strip()
        # If the line is just "Kaia: " or "Kaia:" after cleaning, skip it
        if stripped.lower() in ["kaia:", "kaia: ", "user:", "user: "]:
            continue
        if stripped:
            new_lines.append(line)
    
    content = '\n'.join(new_lines)
    
    if content != original_content:
        print(f"Cleaned {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

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
