import sys
import os
# Ensure project root is in path
sys.path.append(os.getcwd())

import json
import re
import asyncio
import ollama
from pathlib import Path
from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error

# Configuration
LOG_DIRS = [
    Path("knowledge_base/user_logs"),
    Path("knowledge_base/kaia_dreams")
]

async def cleanse_content_with_llm(client, content):
    """Use LLM to remove junk, redundancy, and roleplay while preserving facts."""
    prompt = (
        "You are a Data Sanitization Engine. Clean the following chat log between 'User' and 'Kaia'.\n"
        "1. Remove ALL roleplay markers like (actions), [meta-talk], or *italicized actions*.\n"
        "2. Remove redundant or repetitive turns (e.g., the user asking the same question 5 times to test responses).\n"
        "3. Preserve all factual information, technical details, and meaningful relationship developments.\n"
        "4. Fix any formatting so it follows a clean 'User: ...' / 'Kaia: ...' pattern.\n"
        "5. If a turn is pure junk/test data with no value, omit it entirely.\n\n"
        f"CHAT LOG:\n{content}\n\n"
        "CLEANED LOG (preserving ONLY high-value interactions):"
    )
    
    try:
        response = await client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}
        )
        return response['message']['content'].strip()
    except Exception as e:
        log_error(f"Error cleansing content: {e}")
        return content

async def generate_metadata(client, content):
    """Generate summary and keywords for the log using LLM."""
    prompt = (
        "Analyze the following chat log and provide a JSON response with 'summary' and 'keywords'.\n"
        "1. 'summary': A concise 1-2 sentence overview of the conversation topics.\n"
        "2. 'keywords': A list of 5-10 relevant keywords or names mentioned.\n\n"
        f"CHAT LOG:\n{content[:4000]}\n\n" # Limit to avoid context overflow
        "JSON RESPONSE (format: {\"summary\": \"...\", \"keywords\": [...] }):"
    )
    
    try:
        response = await client.chat(
            model=config.chat_model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1},
            format="json"
        )
        data = json.loads(response['message']['content'])
        return data.get('summary', ""), data.get('keywords', [])
    except Exception as e:
        log_error(f"Error generating metadata: {e}")
        return "", []

async def cleanse_file(client, file_path):
    """Enforce roleplay rules, denoise a log file, and update metadata."""
    log_info(f"Processing: {file_path}")
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            full_content = f.read()
            
        # Parse frontmatter if present
        frontmatter = ""
        content = full_content
        if full_content.startswith("---"):
            parts = full_content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content = parts[2].strip()
                
                # Check if it has populated metadata (already processed)
                summary_match = re.search(r'summary:\s*(.*)', frontmatter)
                keywords_match = re.search(r'keywords:\s*(.*)', frontmatter)
                
                def is_populated(match):
                    if not match: return False
                    val = match.group(1).strip()
                    if not val or val in ['""', "''", "[]"]: return False
                    return True
                
                if is_populated(summary_match) and is_populated(keywords_match):
                    log_info(f"Skipping {file_path.name}: ALREADY PROCESSED (has valid metadata).")
                    return

        # 1. Faster Regex Pre-Pass (Remove asterisks and square brackets)
        content = re.sub(r'\*.*?\*', '', content)
        content = re.sub(r'\[(a )?(long |dry |slight )?(pause|chuckle|sigh|thought|reflection|action|note|interaction).*?\]', '', content, flags=re.IGNORECASE)
        
        # Smart parenthesis removal: only remove roleplay, keep technical content
        def is_roleplay_paren(match):
            paren_content = match.group(1).strip().lower()
            
            # Keep very short (likely abbreviations) or very long (likely technical)
            if len(paren_content) < 3 or len(paren_content) > 100:
                return False
            
            # Keep if it contains code-like symbols
            if any(char in paren_content for char in ['=', ':', ';', '{', '}', '[', ']', '<', '>', '/']):
                return False
            
            # Keep if it starts with a number
            if paren_content[0].isdigit():
                return False
            
            # Remove if it matches roleplay patterns
            roleplay_verbs = ['type', 'sigh', 'pause', 'nod', 'smile', 'frown', 'look', 'glance',
                             'think', 'wonder', 'consider', 'tilt', 'lean', 'shift', 'adjust',
                             'a long', 'a dry', 'a slight', 'softly', 'quietly', 'slowly', 'gently',
                             'after a', 'with a', 'almost']
            if any(paren_content.startswith(verb) for verb in roleplay_verbs):
                return True
            
            return False
        
        content = re.sub(r'\((.*?)\)', lambda m: '' if is_roleplay_paren(m) else m.group(0), content)
        
        # Strip atmospheric flavor text specifically
        atmosphere_patterns = [
            r"hum\s+of\s+the\s+servers",
            r"neon\s+flickering",
            r"terminal\s+glow",
            r"silence\s+hangs",
            r"ambient\s+noise",
            r"environmental\s+vibe",
            r"echo\s+of\s+the",
            r"steady\s+pulse"
        ]
        for pattern in atmosphere_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
        
        # 2. LLM Denoising for Junk/Redundancy (Only if content is significant)
        if len(content) > 500:
            content = await cleanse_content_with_llm(client, content)
            
        # 3. Generate/Update Metadata for .md files
        if file_path.suffix == ".md":
            summary, keywords = await generate_metadata(client, content)
            if summary:
                # Simple YAML injection/replacement
                keywords_str = json.dumps(keywords)
                new_frontmatter = f"\nsummary: {json.dumps(summary)}\nkeywords: {keywords_str}\ndocument_type: Transcript\n"
                frontmatter = new_frontmatter

        # 4. Final Spacing Cleanup
        content = re.sub(r'\n{3,}', '\n\n', content).strip()
        
        with open(file_path, "w", encoding="utf-8") as f:
            if frontmatter:
                f.write(f"---{frontmatter}---\n\n")
            f.write(content)
        log_success(f"Sanitized: {file_path.name}")
        
    except Exception as e:
        log_error(f"Failed to cleanse {file_path.name}: {e}")

async def cleanse_all_logs():
    """Entry point for maintenance tasks."""
    client = ollama.AsyncClient()
    
    log_files = []
    for dir_path in LOG_DIRS:
        if dir_path.exists():
            log_files.extend(list(dir_path.rglob("*.md")))
            log_files.extend(list(dir_path.rglob("*.txt")))
    
    for f in log_files:
        if "user_profile.md" in f.name or f.name.startswith("."):
            continue
        await cleanse_file(client, f)

async def main():
    await cleanse_all_logs()

if __name__ == "__main__":
    asyncio.run(main())
