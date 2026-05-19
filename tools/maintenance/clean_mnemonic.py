import re
from pathlib import Path

def clean_transcript(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Preserve YAML frontmatter
    parts = re.split(r'(---\n.*?\n---)', content, flags=re.DOTALL)
    if len(parts) >= 3:
        frontmatter = parts[1]
        text = "".join(parts[2:])
    else:
        frontmatter = ""
        text = content

    # 1. Remove "Page X/22" markers
    text = re.sub(r'Page \d+/\d+', '', text)

    # 2. Replace pipe characters with space (or just remove if they divide words)
    # Looking at the sample: "Good morning.|This is your wake-up call."
    # A space seems appropriate.
    text = text.replace('|', ' ')

    # 3. Clean up hard line breaks. 
    # This is tricky because some line breaks ARE meaningful (dialogue).
    # But many are just PDF artifacts.
    # Lines starting with "-" are likely dialogue. 
    # Lines starting with all caps are likely scene headers or character names.
    
    lines = text.split('\n')
    cleaned_lines = []
    
    current_line = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            if current_line:
                cleaned_lines.append(current_line)
                current_line = ""
            cleaned_lines.append("") # Keep empty lines
            continue
            
        # Clean pipes
        line = line.replace('|', ' ')
        
        # Determine if we should join this with the previous line
        # Logic: 
        # 1. If current_line is empty, just start it.
        # 2. If line starts with lower case, it's a continuation.
        # 3. If current_line doesn't end with sentence-ending punctuation, it's likely a continuation.
        # 4. BUT if line starts with '-' or 'NAS:', it's a break.
        
        is_break = line.startswith('-') or line.startswith('NAS:') or (line.isupper() and len(line) > 1)
        
        if not current_line:
            current_line = line
        elif is_break:
            cleaned_lines.append(current_line)
            current_line = line
        elif not re.search(r'[.?!"]$', current_line) or line[0].islower():
            current_line += " " + line
        else:
            cleaned_lines.append(current_line)
            current_line = line
                
    if current_line:
        cleaned_lines.append(current_line)

    # Final join
    final_text = frontmatter + "\n" + "\n".join(cleaned_lines)
    
    # Clean up double spaces and excessive newlines
    final_text = re.sub(r' +', ' ', final_text)
    final_text = re.sub(r'\n{3,}', '\n\n', final_text)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(final_text.strip() + "\n")

if __name__ == "__main__":
    target = "/home/ekco/github/Kaiacord/knowledge_base/Books/Johnny Mnemonic.md"
    clean_transcript(target)
    print(f"✅ Cleaned {target}")
