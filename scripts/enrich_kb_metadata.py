import os
import yaml
import re

KB_DIR = "/home/ekco/github/Kaiacord/knowledge_base"

def enrich_file(filepath, category):
    with open(filepath, 'r') as f:
        content = f.read()
    
    parts = re.split(r'^---$', content, maxsplit=2, flags=re.MULTILINE)
    
    header = ""
    body = content
    has_frontmatter = False
    
    if len(parts) >= 3:
        header = parts[1]
        body = parts[2]
        has_frontmatter = True
        try:
            data = yaml.safe_load(header)
        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return
    else:
        data = {}

    modified = False
    basename = os.path.basename(filepath)
    filename_no_ext = os.path.splitext(basename)[0]

    # Try to extract title if missing
    if not data.get("title"):
        title_match = re.search(r'^#\s+(.*)$', body, re.MULTILINE)
        if title_match:
            data["title"] = title_match.group(1).strip()
            modified = True
        else:
            data["title"] = filename_no_ext.replace("_", " ")
            modified = True

    title = data.get("title")

    if category == "forum_posts":
        if not data.get("summary"):
            data["summary"] = f"Forum thread discussion: {title}"
            modified = True
        if not data.get("keywords") or data["keywords"] == []:
            keywords = [k.lower() for k in re.split(r'[\s_]+', title) if len(k) > 3]
            data["keywords"] = list(set(keywords + ["forum", "everquest", "p99"]))
            modified = True
        if not data.get("document_type"):
            data["document_type"] = "Forum Post"
            modified = True
            
    elif category == "user_logs":
        parent_dir = os.path.basename(os.path.dirname(filepath))
        username = parent_dir.replace("forum_", "").split("_")[0]
        if not data.get("summary"):
            data["summary"] = f"Activity and interaction logs for user '{username}'."
            modified = True
        if not data.get("keywords") or data["keywords"] == []:
            data["keywords"] = [username, "user logs", "interactions", "forum history"]
            modified = True
        if not data.get("document_type"):
            data["document_type"] = "Transcript"
            modified = True

    if modified or not has_frontmatter:
        new_header = yaml.dump(data, sort_keys=False).strip()
        new_content = "---\n" + new_header + "\n---\n" + body
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Updated/Added frontmatter for {filepath}")

def main():
    for root, dirs, files in os.walk(os.path.join(KB_DIR, "forum_posts")):
        for f in files:
            if f.endswith(".md"):
                enrich_file(os.path.join(root, f), "forum_posts")
                
    for root, dirs, files in os.walk(os.path.join(KB_DIR, "user_logs")):
        for f in files:
            if f.endswith(".md"):
                enrich_file(os.path.join(root, f), "user_logs")

if __name__ == "__main__":
    main()
