"""Normalise frontmatter on forum posts and user logs.

Writes in place across the whole knowledge base, so it requires an explicit
--apply. It previously had no argument parsing at all: any invocation ran it,
including `--help`, which rewrote frontmatter on 124 files before anyone could
read what the tool did.
"""
import argparse
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.core.atomic_write import write_atomic  # noqa: E402

# Resolved from this file rather than hardcoded to one developer's home.
KB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "knowledge_base",
)

DRY_RUN = True

def enrich_file(filepath, category):
    with open(filepath, 'r') as f:
        content = f.read()

    # Frontmatter only at the top of the file. Splitting on any "---" line took
    # a forum thread's post separators, or a horizontal rule in a log, for the
    # block and parsed a post as YAML.
    from utils.core.frontmatter import parse_frontmatter
    has_frontmatter = content.startswith("---\n")
    try:
        data, body = parse_frontmatter(content)
    except yaml.YAMLError as e:
        print(f"Error parsing {filepath}: {e}")
        return
    data = dict(data or {})

    modified = False
    basename = os.path.basename(filepath)
    filename_no_ext = os.path.splitext(basename)[0]

    # Try to extract title if missing
    if not data.get("title"):
        title_match = re.search(r'^#\s+(.*)$', body, re.MULTILINE)
        if title_match:
            # The heading's words, not its markdown: "**Interactions 20260919**".
            data["title"] = re.sub(r"[*_`]+", "", title_match.group(1)).strip()
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
        # No summary or keywords here. A template summary ("Activity and
        # interaction logs for user X") told enrich_metadata the file was
        # already enriched, so the model never wrote a real one; the nightly
        # pass fills both from the conversation itself.
        if not data.get("document_type"):
            data["document_type"] = "Transcript"
            modified = True

    if modified or not has_frontmatter:
        # The shared writer, and the body exactly as it was: the old join put a
        # blank line in front of it every time.
        from utils.core.frontmatter import dump_frontmatter
        new_content = dump_frontmatter(data) + body
        if DRY_RUN:
            print(f"Would update frontmatter: {filepath}")
            return
        write_atomic(filepath, new_content)
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
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true",
                    help="write changes (default: report only)")
    args = ap.parse_args()
    DRY_RUN = not args.apply
    if DRY_RUN:
        print("DRY RUN — no files will be written. Re-run with --apply.\n")
    main()
