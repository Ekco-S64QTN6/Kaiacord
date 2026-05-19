import re
import glob
import os

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace word... word with word word
    clean = re.sub(r'([a-zA-Z])(?:…|\.{2,3})\s+([a-zA-Z])', r'\1 \2', content)

    # Optional: fix "word word" duplicates created by removing the ellipsis (e.g. "this... this" -> "this this" -> "this")
    # But only if they are the exact same word, like "this this" or "it it"
    clean = re.sub(r'\b([a-zA-Z]+)\s+\1\b', r'\1', clean, flags=re.IGNORECASE)

    if clean != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(clean)
        return True
    return False

log_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Starkind_519557167779676160"
files = glob.glob(os.path.join(log_dir, "interactions_*.md"))

changed_count = 0
for f in files:
    if clean_file(f):
        changed_count += 1
        print(f"Cleaned {os.path.basename(f)}")

print(f"Done. Cleaned {changed_count} files out of {len(files)} total.")
