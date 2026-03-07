import os
import re
import argparse

# Mapping of PUA characters to their intended text
PUA_MAPPING = {
    '\ue000': 'α',
    '\ue004': 'ff', 
    '\ue005': 'ff',
    '\ue006': 'fi',
    '\ue007': 'fi',
    '\ue008': 'fl',
    '\ue009': 'ffi',
    '\ue00a': 'ffl',
    '\ue014': '.',
    '\ue00d': '.',
    '\ue01f': '∫',
    '\ue01b': '∈',
    '\ue017': '/',
    '\ue013': 'ε',
    '\ue001': 'ε', 
    '\ue036': '{',
    '\ue037': '}',
    '\ue03a': '|',
    '\ue00f': '[',
    '\ue010': ']',
    '\ue01d': '∑',
    '\ue028': '√',
    '\ue026': '√',
    '\ue032': '⌈',
    '\ue033': '⌉',
    '\uf0b7': '•', 
    # AIMA specific (often decorative/broken formulas)
    '\ued6a': '', # 
    '\ued6b': '', # 
    '\ued19': '', # 
    '\ued18': '', # 
    '\ued17': '', # 
    '\ued1a': '', # 
}

def clean_content(content):
    # 1. Replace PUA characters
    # Sort by length descending to match longer PUA sequences first (though most are single)
    for pua in sorted(PUA_MAPPING.keys(), key=len, reverse=True):
        replacement = PUA_MAPPING[pua]
        content = content.replace(pua, replacement)
    
    # 2. Fix specific misencoded words (e.g., "fiaw" -> "flaw")
    # This is a bit of a hack but necessary if different ligatures used the same PUA.
    content = content.replace('fiaw', 'flaw')
    content = content.replace('fiagged', 'flagged')
    content = content.replace('fiow', 'flow')
    
    # 3. Fix repeating 'ff' (artifact of multiple PUA replacements)
    content = re.sub(r'f{4,}', '---', content)
    
    # 4. Fix spacing issues
    content = re.sub(r'(\w\.)([A-Z])', r'\1 \2', content)
    
    # 3. Fix missing space after closing parenthesis if followed by letters
    content = re.sub(r'(\))([a-zA-Z])', r'\1 \2', content)
    
    # 4. Fix some commonly joined math/text words
    math_terms = ['lim inf', 'lim sup', 'max', 'min', 'inf', 'sup', 'sgn']
    for term in math_terms:
        content = re.sub(r'([a-z])(' + term + r')(\b|\(|\d|_)', r'\1 \2\3', content)
    
    # 5. Fix joined variables in math-like context
    content = re.sub(r'\b(As)([a-z])\b', r'\1 \2', content)
    
    return content

def process_file(file_path, dry_run=False):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    cleaned = clean_content(content)
    
    if content != cleaned:
        if dry_run:
            print(f"[DRY-RUN] Would clean: {file_path}")
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned)
            print(f"Cleaned: {file_path}")

def delete_duplicate_logs(directory, dry_run=False):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".txt"):
                md_file = file[:-4] + ".md"
                if md_file in files:
                    txt_path = os.path.join(root, file)
                    if dry_run:
                        print(f"[DRY-RUN] Would delete duplicate log: {txt_path}")
                    else:
                        os.remove(txt_path)
                        print(f"Deleted duplicate log: {txt_path}")

def main():
    parser = argparse.ArgumentParser(description="Clean up KB artifacts")
    parser.add_argument("directory", help="Directory to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes")
    parser.add_argument("--delete-logs", action="store_true", help="Delete duplicate .txt logs in user_logs")
    args = parser.parse_args()
    
    if args.delete_logs:
        delete_duplicate_logs(args.directory, args.dry_run)
    
    for root, dirs, files in os.walk(args.directory):
        for file in files:
            if file.endswith(".md"):
                process_file(os.path.join(root, file), args.dry_run)

if __name__ == "__main__":
    main()
