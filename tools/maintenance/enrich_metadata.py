#!/usr/bin/env python3
"""
Metadata Enrichment Pipeline
----------------------------
Backfills missing YAML frontmatter (like `summary` and `keywords`) on 
knowledge base files and user interaction transcripts using a local Ollama instance (gemma3:12b).
Can be run via CLI or triggered via Discord !enrich command.
"""

import os
import re
import sys
import json
import yaml
import time
import asyncio
import aiohttp
import argparse
from pathlib import Path

# Fix path to allow importing from utils
sys.path.append(str(Path(__file__).parent.parent.parent))
from utils.infrastructure.logging.kaia_logger import log_action, log_success, log_error, log_warning, log_info
from utils.core.atomic_write import write_atomic

OLLAMA_HOST = "http://localhost:11434"
# Resolve chat model dynamically from configuration
try:
    from utils.infrastructure.system.yaml_config import config
    MODEL = config.chat_model
except Exception:
    MODEL = "gemma3:12b"
TIMEOUT_SECONDS = 150.0
SLEEP_BETWEEN_CALLS = 1.0

# Define exactly what fields we expect back from the LLM for each category
PROMPT_TEMPLATES = {
    'knowledge': {
        'prompt': (
            "You are a metadata generator. Read the following document and respond ONLY with a JSON object, no preamble, no explanation, no markdown fences.\n"
            "The JSON must have exactly these fields:\n"
            "{\n"
            "\"title\": \"concise document title, max 80 chars\",\n"
            "\"summary\": \"2-3 sentence summary of the main argument or content\",\n"
            "\"keywords\": [\"keyword1\", \"keyword2\", \"keyword3\", \"keyword4\", \"keyword5\"],\n"
            "\"document_type\": \"one of: article, transcript, research, guide, discussion, reference\"\n"
            "}\n"
            "Document:\n"
            "{text}"
        ),
        'char_limit': 3000
    },
    'logs': {
        'prompt': (
            "You are a metadata generator. Read the following conversation transcript and respond ONLY with a JSON object, no preamble, no explanation, no markdown fences.\n"
            "The JSON must have exactly these fields:\n"
            "{\n"
            "\"summary\": \"1-2 sentence summary of the main topics discussed\",\n"
            "\"keywords\": [\"topic1\", \"topic2\", \"topic3\", \"topic4\"]\n"
            "}\n"
            "Transcript:\n"
            "{text}"
        ),
        'char_limit': 2000
    }
}


def parse_frontmatter(content: str) -> tuple[dict, str, str]:
    """Parse a markdown file with YAML frontmatter.
    Returns: (frontmatter_dict, raw_frontmatter_text, body_text)
    """
    if not content.startswith("---\n"):
        return {}, "", content
        
    parts = content.split("---\n", 2)
    if len(parts) < 3:
        return {}, "", content
        
    raw_frontmatter = parts[1]
    body = parts[2]
    
    try:
        data = yaml.safe_load(raw_frontmatter)
        if not isinstance(data, dict):
            data = {}
        return data, raw_frontmatter, body
    except yaml.YAMLError:
        return {}, "", content

def dump_frontmatter(data: dict) -> str:
    """Format a dictionary into a markdown YAML frontmatter block."""
    try:
        # Use safe_dump, maintain dict order, disable document end/start markers, disable sorting
        yaml_str = yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return f"---\n{yaml_str}---\n"
    except Exception as e:
        log_error(f"Failed to dump YAML: {e}")
        return "---\n---\n"

def is_eligible_for_enrichment(frontmatter: dict, body: str) -> bool:
    """Check if the document needs enrichment."""
    # Skip short files
    if len(body.strip()) < 200:
        return False
        
    summary = frontmatter.get('summary')
    keywords = frontmatter.get('keywords')
    
    # If it has both and they aren't empty, it's already enriched
    if summary and isinstance(summary, str) and summary.strip() and \
       keywords and isinstance(keywords, list) and len(keywords) > 0:
        return False
        
    # Otherwise, it needs enrichment
    return True

async def generate_metadata(session: aiohttp.ClientSession, category: str, body: str) -> dict:
    """Call Ollama to generate metadata based on the category template."""
    template = PROMPT_TEMPLATES[category]
    # Truncate body to fit context constraints
    truncated_body = body.strip()[:template['char_limit']]
    
    prompt = template['prompt'].replace('{text}', truncated_body)
    
    # Resolve consistent GPU options
    try:
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        gpu_manager = OllamaGPUManager(MODEL)
        opts = gpu_manager.get_gpu_options(for_chat=True)
        opts["temperature"] = 0.2
        opts["num_predict"] = 400
    except Exception:
        opts = {
            "temperature": 0.2,
            "num_predict": 400
        }

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": opts
    }
    
    async def _post():
        async with session.post(f"{OLLAMA_HOST}/api/generate", json=payload,
                                timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                log_warning(f"Ollama returned {response.status}")
                return None
            return await response.json()

    try:
        # Behind the GPU guard at BACKGROUND priority.
        #
        # This posted straight to localhost:11434, so it was invisible to
        # `gpu_memory_manager` and could not yield to anything. Running a
        # backlog through it held the card at 98% back-to-back on gemma3:12b
        # while the bot was live — every message she received queued behind
        # whichever document was mid-enrichment, and the priority system had no
        # way to know. CLAUDE.md §4: all Ollama calls go through the guard.
        try:
            from utils.infrastructure.gpu.gpu_manager import (
                gpu_memory_manager, GPUTaskPriority)
            import uuid as _uuid
            data = await gpu_memory_manager.run_with_gpu_guard(
                model_name=MODEL, priority=GPUTaskPriority.BACKGROUND,
                coro=_post(), task_id=f"enrich_{_uuid.uuid4().hex[:8]}")
        except ImportError:
            # Running outside the bot's package (a bare checkout); the guard is
            # not available and there is nothing to yield to.
            data = await _post()
        if data is None:
            return {}

        raw_text = data.get('response', '').strip()

        # Clean accidental markdown fences
        if raw_text.startswith("```"):
            lines = raw_text.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_text = '\n'.join(lines).strip()

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            log_warning(f"Failed to parse LLM JSON: {e}\nRaw: {raw_text[:100]}...")
            return {}

    except asyncio.TimeoutError:
        log_warning(f"Ollama call timed out after {TIMEOUT_SECONDS}s")
        return {}
    except Exception as e:
        log_warning(f"Ollama call failed: {e}")
        return {}

async def process_file(filepath: Path, category: str, session: aiohttp.ClientSession, dry_run: bool) -> str:
    """Process a single file, returning its status.
    Returns: 'skipped', 'enriched', or 'failed'
    """
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        log_error(f"Failed to read {filepath}: {e}")
        return 'failed'
        
    frontmatter, raw_yaml, body = parse_frontmatter(content)
    
    # Check if we should actually process this
    if not is_eligible_for_enrichment(frontmatter, body):
        return 'skipped'
        
    # Delay to avoid hammering GPU if we're actually making calls
    await asyncio.sleep(SLEEP_BETWEEN_CALLS)
    
    # Generate new metadata
    new_metadata = await generate_metadata(session, category, body)
    if not new_metadata:
        return 'failed'
        
    # Merge carefully - don't overwrite existing non-empty values
    merged = frontmatter.copy()
    for key, value in new_metadata.items():
        if key not in merged or not merged[key]:
            merged[key] = value
            
    # Write back
    if not dry_run:
        try:
            new_frontmatter_block = dump_frontmatter(merged)
            new_content = new_frontmatter_block + body
            write_atomic(filepath, new_content)
            log_success(f"Enriched {filepath.name}")
        except Exception as e:
            log_error(f"Failed to write {filepath}: {e}")
            return 'failed'
    else:
        log_info(f"[DRY RUN] Would enrich {filepath.name}")
        
    return 'enriched'

def gather_files(base_dir: str, category_flag: str) -> list[tuple[Path, str]]:
    """Gather files mapping to (Path, Category)."""
    kb_path = Path(base_dir)
    files = []
    
    # knowledge_base/general_knowledge → actual KB subdirs (Fix 6)
    if category_flag in ['all', 'knowledge']:
        knowledge_dirs = [
            "books",
            "documents",      # absorbed blogs/ and deep_dive_reports/, Sept 2026
            "news",
            "transcripts",
            "troubleshooting",
            "wiki",
            "kaia_dreams",
        ]
        for subdir in knowledge_dirs:
            folder = kb_path / subdir
            if folder.exists():
                for p in folder.rglob("*.md"):
                    files.append((p, 'knowledge'))
                
    # knowledge_base/user_logs
    if category_flag in ['all', 'logs']:
        ul_path = kb_path / "user_logs"
        if ul_path.exists():
            for p in ul_path.rglob("interactions_*.md"):
                files.append((p, 'logs'))
                
    return files

async def main_async():
    parser = argparse.ArgumentParser(description="Enrich missing frontmatter metadata.")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without saving.")
    parser.add_argument("--category", choices=['all', 'knowledge', 'logs'], default='all', help="Specific category to enrich.")
    parser.add_argument("--dir", default="./knowledge_base", help="Path to knowledge base root.")
    parser.add_argument("--limit", type=int, default=50, help="Max files to process per run (default 50).")
    args = parser.parse_args()
    
    log_info(f"Scanning knowledge base at: {Path(args.dir).absolute()}")
    log_action(f"Starting Metadata Enrichment (Dry Run: {args.dry_run}, Category: {args.category})")
    
    files = gather_files(args.dir, args.category)
    total_scanned = len(files)

    # Filter to what actually needs work *before* capping.
    #
    # The cap used to be applied to the whole list, which is in directory order:
    # books first, then documents, then news. Those front folders were already
    # enriched, so a nightly `--limit 40` spent its entire budget skipping them
    # and never reached the 369 news files that have no frontmatter at all. The
    # task logged "Metadata enrichment pass complete" every night while
    # enriching nothing, and the backlog never moved.
    eligible = []
    for filepath, category in files:
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frontmatter, _raw, body = parse_frontmatter(content)
        if is_eligible_for_enrichment(frontmatter, body):
            eligible.append((filepath, category))

    log_info(f"Scanned {total_scanned} file(s); {len(eligible)} need metadata.")
    files = eligible
    if len(files) > args.limit:
        log_info(f"Capped to {args.limit} of {len(files)} eligible "
                 f"(use --limit N for more)")
        files = files[:args.limit]
    
    stats = {'skipped': 0, 'enriched': 0, 'failed': 0}
    
    async with aiohttp.ClientSession() as session:
        for idx, (filepath, category) in enumerate(files):
            print(f"[{idx+1}/{len(files)}] Processing {filepath.name}...", end='\r')
            status = await process_file(filepath, category, session, args.dry_run)
            stats[status] += 1
            
    print(" " * 80, end='\r') # clear loading line
    
    # Final Summary (using plain print for reliable Discord handler parsing)
    print("--- ENRICHMENT COMPLETED ---")
    print(f"Enriched: {stats['enriched']}")
    print(f"Skipped:  {stats['skipped']} (already enriched or too short)")
    if stats['failed'] > 0:
        print(f"Failed:   {stats['failed']}")

    log_action("--- ENRICHMENT COMPLETED ---")
    log_success(f"Enriched: {stats['enriched']}")
    log_info(f"Skipped:  {stats['skipped']} (Already enriched or too short)")
    if stats['failed'] > 0:
        log_error(f"Failed:   {stats['failed']} (LLM format or read/write error)")

if __name__ == "__main__":
    asyncio.run(main_async())
