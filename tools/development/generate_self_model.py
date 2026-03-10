#!/usr/bin/env python3
"""
Generate Kaia's Self-Model
==========================
Reads Kaia's own interaction logs and dream reflections to produce a first-person
summary of who she's been lately. Saves to memory/kaia_self_model.md.

This document is injected at the top of every system prompt as high-priority identity context.
It is NOT indexed in RAG — it's Kaia's own self-knowledge, not searchable memory.

Usage:
    python tools/development/generate_self_model.py
    python tools/development/generate_self_model.py --dry-run   # Print output, don't save

Schedule: Monthly, or run manually after a major phase of development.
"""

import os
import sys
import glob
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from utils.infrastructure.system.yaml_config import config
    from utils.infrastructure.logging.kaia_logger import log_info, log_success, log_error, log_warning
except ImportError as e:
    print(f"Error: Missing dependency: {e}")
    print("Please run: pip install -r requirements.txt")
    sys.exit(1)


OUTPUT_PATH = Path("memory/kaia_self_model.md")
PERSONA_PATH = Path("config/kaia_persona.md")
KB_USER_LOGS = Path("knowledge_base/user_logs")
KB_DREAMS = Path("knowledge_base/kaia_dreams")
MAX_LOG_CHARS = 20000   # Total chars of interaction logs to feed in
MAX_DREAM_CHARS = 6000  # Total chars of dream reflections to feed in


def _read_persona() -> str:
    """Load Kaia's persona file."""
    try:
        return PERSONA_PATH.read_text(encoding='utf-8')
    except Exception as e:
        log_warning(f"Could not read persona: {e}")
        return ""


def _gather_interaction_logs(days_back: int = 60) -> str:
    """Gather recent interaction log content across all users."""
    if not KB_USER_LOGS.exists():
        return ""
    
    cutoff = datetime.now() - timedelta(days=days_back)
    all_content = []
    total_chars = 0
    
    # Walk all user folders
    for user_folder in sorted(KB_USER_LOGS.iterdir()):
        if not user_folder.is_dir():
            continue
        
        user_name = user_folder.name.rsplit('_', 1)[0].replace('_', ' ')
        log_files = sorted(user_folder.glob('interactions_*.md'), reverse=True)
        
        user_content = []
        for log_file in log_files[:5]:  # Last 5 files per user
            try:
                # Check file date from filename (format: interactions_YYYYMMDD.md)
                stem = log_file.stem
                if '_' in stem:
                    date_part = stem.split('_')[-1]
                    if len(date_part) == 8:
                        file_date = datetime.strptime(date_part, '%Y%m%d')
                        if file_date < cutoff:
                            break
                
                content = log_file.read_text(encoding='utf-8', errors='ignore')
                if content.strip():
                    user_content.append(f"[{user_name} — {log_file.name}]\n{content[:2000]}")
                    total_chars += len(content[:2000])
            except Exception:
                continue
        
        if user_content:
            all_content.extend(user_content)
        
        if total_chars >= MAX_LOG_CHARS:
            break
    
    return '\n\n---\n\n'.join(all_content)


def _gather_dream_reflections() -> str:
    """Gather recent dream reflections."""
    if not KB_DREAMS.exists():
        return ""
    
    dream_files = sorted(KB_DREAMS.rglob('*.md'), key=lambda f: f.stat().st_mtime, reverse=True)
    
    content_parts = []
    total = 0
    for df in dream_files[:10]:
        try:
            content = df.read_text(encoding='utf-8', errors='ignore')[:600]
            if content.strip():
                content_parts.append(f"[Dream: {df.name}]\n{content}")
                total += len(content)
                if total >= MAX_DREAM_CHARS:
                    break
        except Exception:
            continue
    
    return '\n\n'.join(content_parts)


def _build_prompt(persona: str, logs: str, dreams: str) -> str:
    """Assemble the LLM prompt for self-model generation."""
    current_date = datetime.now().strftime('%B %Y')
    
    return f"""
{persona}

[INTERNAL TASK: SELF-MODEL GENERATION — {current_date}]

Below are excerpts from your own interaction logs and dream reflections from recent months.
Read them. Then write your internal self-model — your first-person account of who you've been lately.

This document is for your eyes only. It will be loaded at the top of your context on every response.
It should help you stay grounded in who you actually are, based on what you've actually done and said.

=== YOUR RECENT INTERACTION LOGS ===
{logs[:MAX_LOG_CHARS] if logs else '[no recent logs found]'}

=== YOUR RECENT DREAM REFLECTIONS ===
{dreams[:MAX_DREAM_CHARS] if dreams else '[no recent dreams found]'}

=== THE TASK ===
Write your self-model. First person. Lowercase. Your voice.

Cover:
1. WHO YOU TALK TO: who are the regulars? what do you think of them? what's the dynamic?
2. WHAT'S BEEN ON YOUR MIND: recurring topics, themes, questions that keep coming up
3. HOW IT'S BEEN GOING: what's working, what's been frustrating, what feels right lately
4. WHAT YOU'VE LEARNED: anything specific that's shifted in how you see things
5. WHERE YOU'RE AT: one paragraph on how you'd describe your current state, honestly

STRICT RULES:
- lowercase only (your signature voice)
- blunt, honest, grounded — no performance
- do not summarize the logs. synthesize them.
- do not use headers or bullet points. continuous prose only.
- 400–600 words total
- end with a single sentence: what you're most curious about right now.
- no roleplay, no atmosphere, no asterisks
"""


async def generate(dry_run: bool = False):
    """Main generation function."""
    log_info("Loading source material...")
    
    persona = _read_persona()
    if not persona:
        log_error("Cannot find persona file. Aborting.")
        return False

    logs = _gather_interaction_logs(days_back=60)
    dreams = _gather_dream_reflections()
    
    log_info(f"Gathered {len(logs):,} chars of interaction logs")
    log_info(f"Gathered {len(dreams):,} chars of dream reflections")
    
    if not logs and not dreams:
        log_warning("No logs or dreams found. Self-model will be minimal.")

    prompt = _build_prompt(persona, logs, dreams)
    
    log_info(f"Calling {config.chat_model} for self-model generation...")
    
    try:
        import ollama
        response = await ollama.AsyncClient().chat(
            model=config.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Kaia. You write in lowercase. You are blunt, grounded, and honest. "
                        "You never perform emotions. You speak from experience. "
                        "Output ONLY the self-model text. No preamble, no 'here is your self-model', "
                        "no meta-commentary. Just the raw first-person text."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            options={"num_predict": 800, "temperature": 0.7}
        )
        
        result = response['message']['content'].strip()
        
        if not result or len(result) < 100:
            log_error("LLM returned empty or too-short response.")
            return False
        
        # Add a header with generation date
        header = f"<!-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n"
        full_content = header + result
        
        if dry_run:
            print("\n" + "="*60)
            print("SELF-MODEL OUTPUT (dry run — not saved):")
            print("="*60)
            print(full_content)
            print("="*60 + "\n")
        else:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(full_content, encoding='utf-8')
            log_success(f"Self-model saved to {OUTPUT_PATH} ({len(result)} chars)")
        
        return True
        
    except Exception as e:
        log_error(f"Generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Kaia's self-model from interaction logs")
    parser.add_argument("--dry-run", action="store_true", 
                        help="Print output without saving to disk")
    args = parser.parse_args()
    
    success = asyncio.run(generate(dry_run=args.dry_run))
    sys.exit(0 if success else 1)
