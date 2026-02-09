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
    """Generate YAML frontmatter using LLM"""
    prompt = (
        f"You are a Knowledge Base Enrichment Engine. Analyze the following document snippet from '{filename}'.\n"
        f"Generate a concise 1-2 sentence summary and 5-8 relevant SEO tags/keywords.\n"
        f"Identify the document type (Book, Transcript, Article, Manual, etc.).\n"
        f"OUTPUT FORMAT: YAML FRONTMATTER ONLY (--- ... ---)\n\n"
        f"SNIPPET:\n{content[:2000]}\n\n"
        f"YAML:"
    )
    
    try:
        response = await client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2}
        )
        meta_yaml = response['message']['content'].strip()
        
        # Robust parsing: Look for frontmatter blocks
        match = re.search(r"---(.*?)---", meta_yaml, re.DOTALL)
        if match:
            return f"---{match.group(1)}---"
        
        # Fallback if model omitted delimiters but provided key-value pairs
        if "summary:" in meta_yaml.lower() or "tags:" in meta_yaml.lower():
            # Ensure it starts and ends with ---
            processed = meta_yaml
            if not processed.startswith("---"): processed = "---\n" + processed
            if not processed.endswith("---"): processed = processed + "\n---"
            return processed

        raise ValueError("Model output did not contain valid metadata structure")
        
    except Exception as e:
        print(f"Error generating metadata for {filename}: {e}")
        # Absolute minimal fallback so RAG still has a title
        clean_title = filename.replace(".md", "").replace("_", " ")
        return f"---\ntitle: {clean_title}\ntype: Unknown\n---"

def convert_to_md(file_path):
    """Convert PDF or TXT to MD"""
    md_path = file_path.with_suffix(".md")
    try:
        if file_path.suffix.lower() == ".pdf":
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
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
