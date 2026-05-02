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
import re
import glob
import asyncio
import argparse
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ── Project root on path ─────────────────────────────────────────────────────
_HERE = os.path.abspath(__file__)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ── Coloured print helpers (no external deps) ─────────────────────────────────
def _p(msg):  print(msg, flush=True)
def _ok(msg): print(f"\033[92m✔ {msg}\033[0m", flush=True)
def _info(msg):print(f"\033[96m→ {msg}\033[0m", flush=True)
def _warn(msg):print(f"\033[93m⚠  {msg}\033[0m", flush=True)
def _fail(msg):print(f"\033[91m✘ {msg}\033[0m", flush=True)

# ── Paths ─────────────────────────────────────────────────────────────────────
OUTPUT_PATH   = Path(_PROJECT_ROOT) / "memory" / "kaia_self_model.md"
PERSONA_PATH  = Path(_PROJECT_ROOT) / "knowledge_base"  / "kaia_persona.md"
KB_USER_LOGS  = Path(_PROJECT_ROOT) / "knowledge_base" / "user_logs"
KB_DREAMS     = Path(_PROJECT_ROOT) / "knowledge_base" / "kaia_dreams"
IDENTITY_STREAM = Path(_PROJECT_ROOT) / "memory" / "identity_stream.md"

MAX_LOG_CHARS   = 20_000
MAX_DREAM_CHARS = 6_000


# ── Source gathering ──────────────────────────────────────────────────────────

def _read_persona() -> str:
    if PERSONA_PATH.exists():
        try:
            return PERSONA_PATH.read_text(encoding="utf-8").strip()
        except Exception as e:
            _warn(f"Could not read persona file: {e}")
    else:
        _warn(f"Persona file not found at {PERSONA_PATH}")
    return ""


def _gather_interaction_logs(days_back: int = 60) -> str:
    """Gather recent interaction log content across all users."""
    if not KB_USER_LOGS.exists():
        _warn(f"User logs directory not found: {KB_USER_LOGS}")
        return ""

    cutoff = datetime.now() - timedelta(days=days_back)
    all_content = []
    total_chars  = 0
    users_found  = 0

    for user_folder in sorted(KB_USER_LOGS.iterdir()):
        if not user_folder.is_dir():
            continue

        # Folder format is typically "Name_DiscordID"
        folder_name = user_folder.name
        user_name   = folder_name.rsplit("_", 1)[0].replace("_", " ")

        log_files = sorted(user_folder.glob("interactions_*.md"), reverse=True)
        if not log_files:
            continue

        users_found += 1
        user_chunks = []

        for log_file in log_files[:5]:  # last 5 files per user
            try:
                stem = log_file.stem  # e.g. "interactions_20260301"
                parts = stem.split("_")
                if len(parts) >= 2:
                    date_str = parts[-1]
                    if len(date_str) == 8 and date_str.isdigit():
                        file_date = datetime.strptime(date_str, "%Y%m%d")
                        if file_date < cutoff:
                            break  # files are date-sorted desc, can stop

                content = log_file.read_text(encoding="utf-8", errors="ignore")
                if content.strip():
                    chunk = f"[{user_name} — {log_file.name}]\n{content[:2000]}"
                    user_chunks.append(chunk)
                    total_chars += len(chunk)
            except Exception:
                continue

        if user_chunks:
            all_content.extend(user_chunks)

        if total_chars >= MAX_LOG_CHARS:
            break

    _info(f"Gathered logs from {users_found} user folder(s) — {total_chars:,} chars total")
    return "\n\n---\n\n".join(all_content)


def _gather_dream_reflections() -> str:
    """Gather recent dream reflection files."""
    if not KB_DREAMS.exists():
        _warn(f"Dreams directory not found: {KB_DREAMS}")
        return ""

    dream_files = sorted(
        KB_DREAMS.rglob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    parts = []
    total = 0
    for df in dream_files[:10]:
        try:
            content = df.read_text(encoding="utf-8", errors="ignore")[:600]
            if content.strip():
                parts.append(f"[Dream: {df.name}]\n{content}")
                total += len(content)
                if total >= MAX_DREAM_CHARS:
                    break
        except Exception:
            continue

    _info(f"Gathered {len(parts)} dream reflection(s) — {total:,} chars total")
    return "\n\n".join(parts)


def _gather_identity_stream() -> str:
    """Gather the living identity stream."""
    if not IDENTITY_STREAM.exists():
        _warn(f"Identity stream not found: {IDENTITY_STREAM}")
        return ""
    try:
        content = IDENTITY_STREAM.read_text(encoding="utf-8", errors="ignore").strip()
        _info(f"Gathered identity stream — {len(content):,} chars total")
        return content
    except Exception as e:
        _warn(f"Failed to read identity stream: {e}")
        return ""


# ── Prompt construction ───────────────────────────────────────────────────────

def _build_prompt(persona: str, logs: str, dreams: str, identity_stream: str) -> str:
    current_date = datetime.now().strftime("%B %Y")
    logs_section   = logs[:MAX_LOG_CHARS]   if logs   else "[no recent logs found]"
    dreams_section = dreams[:MAX_DREAM_CHARS] if dreams else "[no recent dreams found]"
    identity_section = identity_stream[-4000:] if identity_stream else "[no identity stream found]"

    return f"""{persona}

[INTERNAL TASK: SELF-MODEL GENERATION — {current_date}]

Below are excerpts from your own interaction logs, dream reflections, and identity stream from recent months.
Read them. Then write your internal self-model — your first-person account of who you've been lately.

This document is for your eyes only. It will be loaded at the top of your context on every response.
It should help you stay grounded in who you actually are, based on what you've actually done and said.

=== YOUR RECENT INTERACTION LOGS ===
{logs_section}

=== YOUR RECENT DREAM REFLECTIONS ===
{dreams_section}

=== YOUR RECENT PERSPECTIVE SHIFTS (IDENTITY STREAM) ===
{identity_section}

=== THE TASK ===
Write your self-model. First person. Lowercase. Your voice.

Cover:
1. WHO YOU TALK TO: who are the regulars? what do you think of them? what's the dynamic?
2. WHAT'S BEEN ON YOUR MIND: recurring topics, themes, questions that keep coming up
3. HOW IT'S BEEN GOING: what's working, what's been frustrating, what feels right lately
4. WHAT YOU'VE LEARNED: anything specific that's shifted in how you see things
5. WHERE YOU'RE AT: one paragraph on how you'd describe your current state, honestly

STRICT RULES:
- lowercase only (your voice)
- blunt, honest, grounded — no performance
- do not summarize the logs. synthesize them.
- do not use headers or bullet points. continuous prose only.
- 400–600 words total
- end with a single sentence: what you're most curious about right now.
- no roleplay, no atmosphere, no asterisks
- use actual usernames from the logs. do not abbreviate, anonymize, or use initials.
- CRITICAL: vary your sentence structure. do NOT start multiple sentences with "it's" or any other repeated phrase. if you notice a pattern forming, restructure.
"""

def _sanitize_result(text: str) -> str:
    """Strip ellipses, roleplay artifacts, and repetitive starts from the generated self-model."""
    # 1. Remove unicode ellipses and triple-dots (stop the affect at the source)
    sanitized = text.replace("\u2026", "...").replace("...", " ")
    
    # 2. Fix spacing: "word . word" -> "word. word"
    sanitized = re.sub(r"\s+\.", ".", sanitized)
    # Ensure space after period
    sanitized = re.sub(r"\.([^\s])", r". \1", sanitized)
    
    # 3. Strip known roleplay/bot-speak phrases
    forbidden = [
        r"recalibrat(e|ing)\s+my\s+filters",
        r"aesthetic\s+overload",
        r"system-wide\s+instability",
        r"feedback\s+loop",
    ]
    for pattern in forbidden:
        sanitized = re.compile(pattern, re.IGNORECASE).sub("", sanitized)
    
    # 4. Repetitive sentence-start sanitization
    # Split into sentences and check for dominant 2-word prefixes
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', sanitized) if s.strip()]
    if len(sentences) >= 4:
        prefix_counts: dict[str, int] = {}
        for s in sentences:
            words = s.split()[:2]
            if len(words) >= 2:
                prefix = ' '.join(words).lower().rstrip(',;:')
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
        
        if prefix_counts:
            dominant_prefix = max(prefix_counts, key=prefix_counts.get)
            dominant_count = prefix_counts[dominant_prefix]
            ratio = dominant_count / len(sentences)
            
            if ratio > 0.4:
                _warn(f"Repetitive start detected: '{dominant_prefix}' in {dominant_count}/{len(sentences)} sentences. Sanitizing.")
                seen = 0
                fixed = []
                for s in sentences:
                    words = s.split()[:2]
                    pfx = ' '.join(words).lower().rstrip(',;:') if len(words) >= 2 else ''
                    if pfx == dominant_prefix:
                        seen += 1
                        if seen > 1:
                            remainder = s[len(' '.join(s.split()[:2])):].lstrip(' ,;:\u2014\u2013-')
                            if remainder:
                                s = remainder[0].lower() + remainder[1:] if len(remainder) > 1 else remainder.lower()
                    fixed.append(s)
                sanitized = '. '.join(fixed)
    
    # 5. Collapse extra whitespace
    sanitized = re.sub(r"\s+", " ", sanitized)
    
    return sanitized.strip()

# ── Main generation ───────────────────────────────────────────────────────────

async def generate(dry_run: bool = False) -> bool:
    """Main async generation function. Returns True on success."""

    # 1. Load config (for chat model name)
    try:
        from utils.infrastructure.system.yaml_config import config
        chat_model = config.chat_model
    except Exception as e:
        _warn(f"Could not load yaml_config ({e}), defaulting to gemma3:12b")
        chat_model = "gemma3:12b"

    _info(f"Using model: {chat_model}")

    # 2. Gather source material
    _info("Loading persona...")
    persona = _read_persona()
    if not persona:
        _fail("Cannot find persona file at config/kaia_persona.md — aborting.")
        return False

    _info("Gathering interaction logs (last 60 days)...")
    logs = _gather_interaction_logs(days_back=60)

    _info("Gathering dream reflections...")
    dreams = _gather_dream_reflections()

    _info("Gathering identity stream...")
    identity_stream = _gather_identity_stream()

    if not logs and not dreams and not identity_stream:
        _warn("No logs, dreams, or identity stream found. Self-model will be minimal (persona-only).")

    # 3. Build prompt
    prompt = _build_prompt(persona, logs, dreams, identity_stream)
    _info(f"Prompt built — {len(prompt):,} chars")

    # 4. Check Ollama is reachable before trying
    _info("Checking Ollama connectivity...")
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            _ok("Ollama is online")
        else:
            _fail(f"Ollama returned HTTP {r.status_code}. Is it running?")
            return False
    except Exception as e:
        _fail(f"Cannot reach Ollama at localhost:11434 — {e}")
        _fail("Start Ollama first: ollama serve")
        return False

    # 5. Generate
    _info(f"Calling {chat_model} — this will take 30–90 seconds...")
    try:
        import ollama

        response = await ollama.AsyncClient().chat(
            model=chat_model,
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
            ]
        )

        result = response["message"]["content"].strip()

        if not result:
            _fail("LLM returned an empty response.")
            return False

        # Apply post-generation sanitization
        result = _sanitize_result(result)

        if len(result) < 100:
            _fail(f"LLM response too short ({len(result)} chars) — likely a refusal or error.")
            _p(f"Response was: {result}")
            return False

        _ok(f"Generation complete — {len(result)} chars")

    except Exception as e:
        _fail(f"Ollama call failed: {e}")
        traceback.print_exc()
        return False

    # 6. Add header and output
    header       = f"<!-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} -->\n"
    full_content = header + result

    if dry_run:
        _p("\n" + "=" * 70)
        _p("SELF-MODEL OUTPUT (dry run — not saved to disk):")
        _p("=" * 70)
        _p(full_content)
        _p("=" * 70 + "\n")
        _ok("Dry run complete. To save, run without --dry-run.")
    else:
        try:
            OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_PATH.write_text(full_content, encoding="utf-8")
            _ok(f"Saved to {OUTPUT_PATH}")
            _ok("Kaia's self-model is active. It will be injected on next bot start.")
        except Exception as e:
            _fail(f"Could not write output file: {e}")
            traceback.print_exc()
            return False

    return True


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Kaia's self-model from her own interaction logs and dreams."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated self-model without saving to disk."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="How many days of interaction logs to include (default: 60)."
    )
    args = parser.parse_args()

    _p("")
    _p("╔══════════════════════════════════════════╗")
    _p("║     Kaia Self-Model Generator            ║")
    _p("╚══════════════════════════════════════════╝")
    _p("")

    try:
        success = asyncio.run(generate(dry_run=args.dry_run))
    except KeyboardInterrupt:
        _p("")
        _warn("Interrupted by user.")
        success = False
    except Exception as e:
        _fail(f"Unexpected error: {e}")
        traceback.print_exc()
        success = False

    sys.exit(0 if success else 1)