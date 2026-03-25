import re
import glob
import os

log_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Starkind_519557167779676160"
files = glob.glob(os.path.join(log_dir, "*.md"))

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # We want to remove sentences that say Kaia will flag something.
    # e.g., "I'll flag this for Ekco." "A way to flag it for consistent review." "I'll have to flag that for review."
    
    # Regex to extract sentences containing 'flag'
    # Simple sentence boundary: [a-z0-9] . [A-Z] or [a-z]
    # To be safe, we'll just match the sentence containing the word 'flag' 'flagging' 'flagged' ignoring case.

    # sentences starting after a boundary
    sentences = re.split(r'(?<=[.!?])\s+', content)
    
    new_sentences = []
    changed = False
    
    for s in sentences:
        s_lower = s.lower()
        if 'flag' in s_lower:
            # Let's see if it's the annoying bot-speak
            if 'review' in s_lower or 'ekco' in s_lower or 'issue' in s_lower or 'limitation' in s_lower:
                print(f"Removing: {s.strip()}")
                changed = True
                continue
            # "I flagged it, of course"
            if 'flagged it' in s_lower or 'flag it' in s_lower or 'flag this' in s_lower or 'flag that' in s_lower:
                print(f"Removing: {s.strip()}")
                changed = True
                continue
                
        new_sentences.append(s)
        
    if changed:
        return " ".join(new_sentences)
    return None

for f in files:
    clean = clean_file(f)
    if clean:
        print(f"Modified {os.path.basename(f)}")
        # Uncomment to actually write
        # with open(f, 'w', encoding='utf-8') as file:
        #    file.write(clean)

