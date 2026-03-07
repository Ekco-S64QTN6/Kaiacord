import os
import re
import asyncio
import ollama
from pypdf import PdfReader
from pathlib import Path
from utils.infrastructure.system.yaml_config import config

# Configuration
KB_DIR = Path("knowledge_base")

async def generate_metadata(client, content, filename):
    """Generate YAML frontmatter using LLM with strict formatting"""
    prompt = (
        f"You are a Knowledge Base Enrichment Engine. Analyze the following document snippet from '{filename}'.\n"
        "Output ONLY valid YAML frontmatter between '---' delimiters. Do NOT use code blocks.\n"
        "REQUIRED KEYS:\n"
        "1. summary: A 1-2 sentence overview of the document.\n"
        "2. keywords: A YAML list [word1, word2, ...] of 5-8 relevant tags.\n"
        "3. document_type: One word (e.g., Book, Transcript, Article, Manual).\n\n"
        "Example Output:\n"
        "---\n"
        "summary: \"Example summary.\"\n"
        "keywords: [key1, key2]\n"
        "document_type: Article\n"
        "---\n\n"
        f"SNIPPET:\n{content[:2000]}\n\n"
        "YAML:"
    )
    
    try:
        response = await client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}
        )
        meta_yaml = response['message']['content'].strip()
        
        # Aggressively clean output
        meta_yaml = meta_yaml.replace("```yaml", "").replace("```", "").strip()
        
        # Ensure it starts and ends with ---
        if not meta_yaml.startswith("---"):
            meta_yaml = "---\n" + meta_yaml
        if not meta_yaml.endswith("---"):
            meta_yaml = meta_yaml + "\n---"
            
        # Validate keys exist (basic check)
        lower_meta = meta_yaml.lower()
        if "summary:" not in lower_meta or "keywords:" not in lower_meta or "document_type:" not in lower_meta:
             print(f"⚠️ Warning: Model output for {filename} might be missing keys.")
             
        return meta_yaml
        
    except Exception as e:
        print(f"Error generating metadata for {filename}: {e}")
        return f"---\nsummary: \"Generation failed.\"\nkeywords: []\ndocument_type: Unknown\n---"

def convert_to_md(file_path):
    """Convert PDF or TXT to MD with improved line joining"""
    md_path = file_path.with_suffix(".md")
    try:
        if file_path.suffix.lower() == ".pdf":
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text() or ""
                # Improved line joining: if a line is short or doesn't end in punctuation, join it
                lines = page_text.split("\n")
                joined_page = ""
                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        joined_page += "\n\n"
                        continue
                    
                    joined_page += line
                    # Heuristic: if line is short and doesn't end in punctuation, it's likely a mid-sentence break
                    if len(line) < 60 and i < len(lines) - 1 and not re.search(r'[.!?:]$', line):
                        joined_page += " "
                    else:
                        joined_page += "\n"
                text += joined_page + "\n"
        else: # TXT
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
                
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✅ Converted: {file_path.name} -> {md_path.name}")
        return md_path
    except Exception as e:
        print(f"❌ Failed to convert {file_path.name}: {e}")
        return None

async def process_file(client, file_path):
    """Add metadata and summary to MD file"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        # Check if already has valid frontmatter (don't skip failed ones)
        if content.startswith("---") and "title: Error" not in content[:100]:
            print(f"⏩ Skipping {file_path.name} (Already has metadata)")
            return

        # If it was a failed one, strip the old 'Error' header
        if content.startswith("---"):
            content = re.sub(r"---.*?---\s*", "", content, flags=re.DOTALL)

        meta_yaml = await generate_metadata(client, content, file_path.name)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(meta_yaml + "\n\n" + content)
        print(f"✨ Enriched: {file_path.name}")
    except Exception as e:
        print(f"❌ Failed to process {file_path.name}: {e}")

async def main():
    client = ollama.AsyncClient()
    
    # 1. Convert PDFs and TXTs
    print("Converting PDFs and TXTs...")
    conv_files = []
    for ext in ["*.pdf", "*.txt"]:
        conv_files.extend(list(KB_DIR.rglob(ext)))
        
    for f in conv_files:
        if f.name.startswith(".") or "interactions" in f.name: continue # Skip hidden and logs
        convert_to_md(f)
        
    # 2. Process all MDs
    print("Enriching files with metadata...")
    md_files = list(KB_DIR.rglob("*.md"))
    for md in md_files:
        if "kaia_persona.md" in md.name or "walkthrough" in md.name: continue
        await process_file(client, md)
        
    # 3. Cleanup original files (Optional - but recommended for this task)
    print("Cleaning up original PDF/TXT files...")
    for f in conv_files:
        if f.name.startswith(".") or "interactions" in f.name: continue
        if f.with_suffix(".md").exists():
            f.unlink()
            print(f"🗑️ Removed original: {f.name}")

if __name__ == "__main__":
    asyncio.run(main())
