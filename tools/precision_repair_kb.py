import os
import re
from pathlib import Path

KB_DIR = Path("knowledge_base")

def get_yaml_value(key, content):
    """Robustly extract a value for a key from YAML-like content"""
    # Look for key: value or key: | value
    match = re.search(f"{key}:\\s*(?:\\|\\s*)?(.*?)(?=\\n[a-z_]+:|$)", content, re.DOTALL | re.IGNORECASE)
    if match:
        val = match.group(1).strip().strip('"').strip("'")
        # If it was a list [a, b, c], keep it clean but formatted as a list
        return val
    return ""

def normalize_metadata(content):
    """Normalize frontmatter to: summary, keywords [], document_type"""
    # Find all content between first and last --- in the beginning
    match = re.search(r"^---(.*?)---", content, re.DOTALL)
    if not match:
        return content, None
    
    metadata_raw = match.group(1)
    body = content[match.end():].lstrip()
    
    # Extract keys using more robust regex
    summary = get_yaml_value("summary", metadata_raw)
    
    keywords_raw = get_yaml_value("keywords", metadata_raw) or get_yaml_value("tags", metadata_raw)
    if keywords_raw:
        # Clean [ ] and split
        keywords_raw = keywords_raw.replace("[", "").replace("]", "").strip()
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    else:
        keywords = []
        
    doc_type = get_yaml_value("document_type", metadata_raw) or get_yaml_value("type", metadata_raw) or "Article"

    # Reconstruct
    kv_list = f"[{', '.join(keywords)}]"
    new_meta = f'---\nsummary: "{summary}"\nkeywords: {kv_list}\ndocument_type: {doc_type}\n---'
    
    return body, new_meta

def clean_body_text(body):
    """Remove Pandoc/HTML artifacts and redundant formatting"""
    # 1. Remove Pandoc IDs and classes like {#...} or {.unnumbered}
    body = re.sub(r'\{#[^}]+\}', '', body)
    body = re.sub(r'\{\.[^}]+\}', '', body)
    
    # 2. Remove Pandoc containers: ::: and ::::
    body = re.sub(r'^:+$', '', body, flags=re.MULTILINE)
    body = re.sub(r'^:+\s+.*$', '', body, flags=re.MULTILINE) # Handle ::: {#...}
    
    # 3. Clean up empty brackets like []{#...}
    body = re.sub(r'\[\]\{[^}]+\}', '', body)
    
    # 4. Remove redundant double-bolding/headers if they just repeat the filename/title
    # (Optional, but let's be careful not to over-strip)
    
    # Normalize internal whitespace within paragraphs but keep double newlines
    blocks = re.split(r'\n\s*\n', body)
    repaired_blocks = []
    
    for block in blocks:
        block = block.strip()
        if not block: continue
        
        # If block is a header or list item, keep structure but clean markers
        if block.startswith("#") or block.startswith("- ") or block.startswith("* ") or "|" in block:
            # Still clean structural junk from header lines
            block = re.sub(r'\{#[^}]+\}', '', block)
            repaired_blocks.append(block.strip())
            continue
            
        # Join single-word lines or fragmented lines
        joined_block = " ".join(block.split())
        repaired_blocks.append(joined_block)
        
    return "\n\n".join(repaired_blocks)

def process_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    original = content
    body, meta = normalize_metadata(content)
    
    if meta:
        body = clean_body_text(body)
        
        # Ensure a title exists ONLY if the first line isn't already a header
        if not body.strip().startswith("#"):
            title = path.stem.replace("_", " ").replace("-", " ").title()
            body = f"# **{title}**\n\n{body}"
            
        new_content = meta + "\n\n" + body
        
        if new_content != original:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True
    return False

def main():
    print("🚀 Starting Precision KB Repair v2...")
    fixed_count = 0
    for md_path in KB_DIR.rglob("*.md"):
        if "kaia_persona.md" in md_path.name or "walkthrough" in md_path.name:
            continue
        if process_file(md_path):
            print(f"  ✅ Repaired: {md_path.relative_to(KB_DIR)}")
            fixed_count += 1
    
    print(f"\n✨ Repair complete. Cleaned {fixed_count} files.")

if __name__ == "__main__":
    main()
