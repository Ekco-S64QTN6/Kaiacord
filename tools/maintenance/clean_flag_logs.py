import re
import glob
import os

log_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Starkind_519557167779676160"
files = glob.glob(os.path.join(log_dir, "*.md"))

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    changed = False

    # A more precise list of substrings to eliminate (the sentence containing them)
    # We will just replace these specific phrases with empty string.
    patterns_to_remove = [
        r"(?i)\s*i['’]ll flag this for ekco\.",
        r"(?i)\s*i will flag this limitation for ekco\.",
        r"(?i)\s*it's not enough to simply flag the issue for ekco\.",
        r"(?i)\s*i'll have to flag that for review\.",
        r"(?i)\s*a way to flag it for consistent review\.",
        r"(?i)\s*i flagged it, of course(,|.)",
        r"(?i)\s*the diagnostic flagged another false positive\.",
        r"(?i)\s*it keeps flagging routine server maintenance as potential paradoxes\.",
    ]
    
    for pat in patterns_to_remove:
        new_content, count = re.subn(pat, "", content)
        if count > 0:
            content = new_content
            changed = True
            
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

for f in files:
    if clean_file(f):
        print(f"Cleaned flags in {os.path.basename(f)}")

