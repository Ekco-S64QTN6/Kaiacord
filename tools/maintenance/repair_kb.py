import os
import re
from pathlib import Path

KB_DIR = Path("knowledge_base")

def repair_frontmatter(content):
    """Clean up malformed YAML frontmatter"""
    # 1. Handle triple backtick wrap
    content = re.sub(r"---[\s\n]*```yaml\n(.*?)\n```[\s\n]*---", r"---\n\1\n---", content, flags=re.DOTALL)
    content = re.sub(r"---[\s\n]*```\n(.*?)\n```[\s\n]*---", r"---\n\1\n---", content, flags=re.DOTALL)
    
    # 2. Handle cases where the model put backticks INSIDE the delimiters
    match = re.search(r"---(.*?)---", content, re.DOTALL)
    if match:
        inner = match.group(1)
        cleaned_inner = inner.replace("```yaml", "").replace("```", "").strip()
        content = content[:match.start()] + "---\n" + cleaned_inner + "\n---" + content[match.end():]

    return content

def repair_line_breaks(content):
    """Aggressively join lines if the file is extremely fragmented"""
    parts = re.split(r"(---\n.*?---\n)", content, flags=re.DOTALL)
    if len(parts) < 3:
        return content
    
    frontmatter = parts[1]
    body = "".join(parts[2:])
    
    # If there are many single-word lines followed by empty lines
    # Let's strip excess newlines and join
    
    # Heuristic: if average line length is extremely low
    lines = [l.strip() for l in body.split("\n")]
    if not lines: return content
    
    non_empty_lines = [l for l in lines if l]
    if not non_empty_lines: return content
    
    avg_len = sum(len(l) for l in non_empty_lines) / len(non_empty_lines)
    
    if avg_len < 15: # Highly fragmented
        print(f"  Aggressive repair triggered (avg len: {avg_len:.1f})")
        # Join all non-empty lines with space, handle double newlines as paragraphs
        paragraphs = re.split(r'\n\s*\n', body)
        repaired_paragraphs = []
        for p in paragraphs:
            # Join all words in paragraph
            joined = " ".join(p.split())
            if joined:
                repaired_paragraphs.append(joined)
        
        repaired_body = "\n\n".join(repaired_paragraphs)
        return frontmatter + "\n\n" + repaired_body
    
    # Standard repair for moderately broken lines
    repaired_body = ""
    for i, line in enumerate(lines):
        if not line:
            repaired_body += "\n\n"
            continue
        
        repaired_body += line
        if len(line) < 50 and i < len(lines) - 1 and lines[i+1] and not re.search(r'[.!?:]$', line):
            repaired_body += " "
        else:
            repaired_body += "\n"
            
    return frontmatter + "\n\n" + repaired_body

def process_kb():
    print("Starting Knowledge Base repair...")
    for md_path in KB_DIR.rglob("*.md"):
        if "kaia_persona.md" in md_path.name or "walkthrough" in md_path.name:
            continue
            
        with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        original = content
        content = repair_frontmatter(content)
        content = repair_line_breaks(content)
            
        if content != original:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✅ Fixed {md_path.relative_to(KB_DIR)}.")

if __name__ == "__main__":
    process_kb()
