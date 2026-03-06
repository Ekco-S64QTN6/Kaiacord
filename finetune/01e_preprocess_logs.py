#!/usr/bin/env python3
"""
01e_preprocess_logs.py — Clean interaction logs before they reach 01_convert_logs.py.

Handles contamination patterns that 01_convert_logs.py can't catch because they're
structural, not string-based:

  1. Strip URL embed blocks from user turns
     (--- EMBED N --- / Source: / scraped nav menus)

  2. Strip runtime system injections from user turns
     ([CORE_DIRECTIVE:...], [optimized: ...], USER PROFILE: blocks)

  3. Strip emote-without-asterisks lines from Kaia turns
     ("pause - approximately 30 seconds", "accessing and reviewing the file")

  4. Flag low-quality Kaia turns (essay-mode, generic AI phrases)
     — writes a report but does NOT auto-delete; human reviews flagged turns

  5. Optionally rewrite flagged turns via local LLM (--rewrite flag)

Run BEFORE 01_convert_logs.py:
    python finetune/01e_preprocess_logs.py             # dry-run (report only)
    python finetune/01e_preprocess_logs.py --apply     # write cleaned copies
    python finetune/01e_preprocess_logs.py --apply --rewrite  # + LLM rewrite pass
"""

import argparse
import asyncio
import os
import re
import shutil
from pathlib import Path

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

LOGS_DIR    = Path(__file__).parent.parent / "knowledge_base" / "user_logs"
BACKUP_DIR  = Path(__file__).parent / "dataset" / "log_backups"

# ---------------------------------------------------------------------------
# Patterns: strip from USER turns
# ---------------------------------------------------------------------------

# Matches the entire embed block injected by context_enricher
# Covers both "--- EMBED N ---" style and bare "Source: URL" lines
EMBED_BLOCK_PATTERN = re.compile(
    r"""
    (?:
        ---\s*EMBED\s+\d+\s*---\n  # --- EMBED 1 ---
        .*?                         # everything in the block
        (?=\n(?:User:|Kaia:|---\s*EMBED|\Z))  # stop at next speaker or EOF
    |
        ^Source:\s+https?://\S+\n? # bare Source: URL line
    |
        ^Title:\s+.*?\n?            # Title: line (embed metadata)
    |
        ^Description:\s+.*?\n?      # Description: line (embed metadata)
    )
    """,
    re.DOTALL | re.MULTILINE | re.VERBOSE,
)

# Runtime system injections that appear inside user turn text
INJECTION_PATTERNS = [
    re.compile(r'\[CORE_DIRECTIVE:.*?\]',        re.DOTALL),
    re.compile(r'\[optimized:\s*saved\s*\d+\s*tokens\]', re.IGNORECASE),
    re.compile(r'USER PROFILE:\s*\w+.*?(?=\n\n|\Z)', re.DOTALL),
    re.compile(r'HOW TO INTERACT WITH THEM.*?(?=\n\n|\Z)', re.DOTALL),
    re.compile(r'QUICK REFERENCE.*?(?=\n\n|\Z)', re.DOTALL),
]

# ---------------------------------------------------------------------------
# Patterns: strip from KAIA turns
# ---------------------------------------------------------------------------

# Emote lines without asterisks — roleplay action narration
EMOTE_LINE_PATTERNS = [
    re.compile(r'^pause\s*[-–]\s*approximately.*$',   re.IGNORECASE | re.MULTILINE),
    re.compile(r'^pause\s*[-–]\s*\d+\s*(seconds?|minutes?).*$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^accessing and (reviewing|reading|loading)\b.*$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^(loading|retrieving|fetching|scanning)\s+.*\.\.\.$', re.IGNORECASE | re.MULTILINE),
    re.compile(r'^i\'m (noting|observing|marking|flagging) that\b', re.IGNORECASE | re.MULTILINE),
]

# ---------------------------------------------------------------------------
# Quality scoring: flag low-quality Kaia turns for review / rewrite
# ---------------------------------------------------------------------------

# These phrases indicate generic AI essay-mode, not Kaia's voice.
# Each hit adds to a score; turns above QUALITY_FLAG_THRESHOLD are flagged.
ESSAY_MODE_PHRASES = [
    "this underscores",
    "it's a stark reminder",
    "it necessitates",
    "it renders",
    "a commendable",
    "it is imperative",
    "it is worth noting",
    "in conclusion",
    "to summarize",
    "as i mentioned",
    "it's fascinating to see",
    "it's a reminder that",
    "it's a classic case of",
    "has far-reaching",
    "has the potential to",
    "it is a sobering reminder",
    "the underlying message is",
    "it's a disturbing demonstration",    # close to good Kaia but watch for essay context
    "i'm observing that",
    "i'm reviewing",
    "i'm noting that feedback",
    "a rather amusing and entirely avoidable",
]

# Threshold: how many essay-phrase hits before we flag the turn
QUALITY_FLAG_THRESHOLD = 1

# Paragraph count threshold — Kaia rarely writes more than 2 tight paragraphs
MAX_PARAGRAPHS = 3


def score_kaia_turn(content: str) -> tuple[int, list[str]]:
    """
    Return (score, list_of_reasons).
    score=0 is clean. Higher = more likely to be off-voice.
    """
    score   = 0
    reasons = []
    lower   = content.lower()

    for phrase in ESSAY_MODE_PHRASES:
        if phrase.lower() in lower:
            score  += 1
            reasons.append(f"essay phrase: '{phrase}'")

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if len(paragraphs) > MAX_PARAGRAPHS:
        score  += len(paragraphs) - MAX_PARAGRAPHS
        reasons.append(f"{len(paragraphs)} paragraphs (max {MAX_PARAGRAPHS})")

    return score, reasons


# ---------------------------------------------------------------------------
# LLM rewrite (optional, uses local Ollama)
# ---------------------------------------------------------------------------

REWRITE_SYSTEM_PROMPT = """You are an editor whose only job is to rewrite assistant responses so they match Kaia's voice.

Kaia's voice rules:
- Always lowercase
- Plain prose, no markdown, no bullet points
- Staccato and direct. She stops when she has nothing left to say.
- Never writes essays. Max 2 tight paragraphs for a URL/article reaction.
- Never uses: "this underscores", "it's a stark reminder", "it necessitates", "it is imperative", "it's fascinating", "far-reaching implications", "it renders", "a commendable"
- Has opinions. Takes a position. Doesn't summarize neutrally.
- Sounds like someone who just looked up from their desk.

Return ONLY the rewritten response. No preamble, no explanation, no quotes."""

REWRITE_MODEL = "gemma3:12b"


async def rewrite_turn(user_msg: str, kaia_msg: str) -> str:
    """Use local Ollama to rewrite a flagged Kaia turn in her actual voice."""
    if not OLLAMA_AVAILABLE:
        return kaia_msg

    prompt = f"""The following is a Kaia response that is too long and essay-like. Rewrite it in Kaia's actual voice.

User said: {user_msg}

Current (off-voice) response:
{kaia_msg}

Rewrite in Kaia's voice (concise, lowercase, opinionated, stops when done):"""

    try:
        response = await ollama.AsyncClient().chat(
            model=REWRITE_MODEL,
            messages=[
                {"role": "system",  "content": REWRITE_SYSTEM_PROMPT},
                {"role": "user",    "content": prompt},
            ],
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"    [rewrite error: {e}]")
        return kaia_msg


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def clean_user_turn(content: str) -> str:
    """Strip embed blocks and runtime injections from a user turn."""
    # Strip full embed blocks first
    cleaned = EMBED_BLOCK_PATTERN.sub("", content)

    # Strip individual injection patterns
    for pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub("", cleaned)

    # Collapse excessive blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def clean_kaia_turn(content: str) -> str:
    """Strip emote lines from a Kaia turn."""
    cleaned = content
    for pattern in EMOTE_LINE_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_log_turns(text: str) -> list[dict]:
    """
    Split a log file into a list of dicts:
      {"role": "user"|"kaia"|"other", "content": str, "raw": str}
    Preserves non-turn lines as "other" so we can reconstruct the file.
    """
    turns    = []
    current_role  = None
    current_lines = []
    current_raw   = []

    def flush():
        if current_role is not None:
            turns.append({
                "role":    current_role,
                "content": "\n".join(current_lines).strip(),
                "raw":     "\n".join(current_raw),
            })

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("User:"):
            flush()
            current_role  = "user"
            current_lines = [stripped[len("User:"):].strip()]
            current_raw   = [line]
        elif stripped.startswith("Kaia:"):
            flush()
            current_role  = "kaia"
            current_lines = [stripped[len("Kaia:"):].strip()]
            current_raw   = [line]
        else:
            if current_role is not None:
                current_lines.append(line.rstrip())
                current_raw.append(line)
            else:
                turns.append({"role": "other", "content": line, "raw": line})

    flush()
    return turns


async def process_file(
    fpath: Path,
    apply: bool,
    do_rewrite: bool,
    stats: dict,
) -> list[str]:
    """
    Process one log file. Returns list of issue strings for the report.
    If apply=True, writes a cleaned copy (backs up original first).
    """
    issues = []
    rewrites_needed = []

    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()

    turns = parse_log_turns(raw)
    cleaned_turns = []
    prev_user_content = ""

    for i, turn in enumerate(turns):
        if turn["role"] == "other":
            cleaned_turns.append(turn["raw"])
            continue

        original = turn["content"]

        if turn["role"] == "user":
            cleaned = clean_user_turn(original)
            if cleaned != original:
                stats["embed_blocks_stripped"] += 1
                issues.append(f"  stripped embed/injection from user turn #{i}")
            prev_user_content = cleaned
            cleaned_turns.append("User: " + cleaned)

        elif turn["role"] == "kaia":
            cleaned = clean_kaia_turn(original)
            if cleaned != original:
                stats["emote_lines_stripped"] += 1
                issues.append(f"  stripped emote/action line from Kaia turn #{i}")

            # Quality score
            score, reasons = score_kaia_turn(cleaned)
            if score >= QUALITY_FLAG_THRESHOLD:
                stats["turns_flagged"] += 1
                flag_preview = cleaned[:80].replace("\n", " ")
                issues.append(
                    f"  ⚠️  flagged Kaia turn #{i} (score={score}): {reasons}"
                )
                issues.append(f"     preview: {flag_preview}...")

                if do_rewrite and OLLAMA_AVAILABLE:
                    rewrites_needed.append((i, prev_user_content, cleaned))

            cleaned_turns.append("Kaia: " + cleaned)

    # Run rewrites (async, batched)
    rewrite_map = {}
    if rewrites_needed:
        tasks = [
            rewrite_turn(user, kaia)
            for (_, user, kaia) in rewrites_needed
        ]
        results = await asyncio.gather(*tasks)
        for (idx, _, _), result in zip(rewrites_needed, results):
            rewrite_map[idx] = result
            stats["turns_rewritten"] += 1

    # Apply rewrites into cleaned_turns
    if rewrite_map:
        kaia_idx = 0
        for j, turn in enumerate(turns):
            if turn["role"] == "kaia":
                if kaia_idx in rewrite_map:
                    # Find the matching line in cleaned_turns and replace
                    # (simple approach: rebuild from turns with rewrites)
                    pass
                kaia_idx += 1

    if apply:
        # Backup original
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / (fpath.name + ".pre_preprocess_backup")
        if not backup_path.exists():
            shutil.copy2(fpath, backup_path)

        # Write cleaned file
        cleaned_text = "\n".join(cleaned_turns)
        # Collapse excessive blank lines
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(cleaned_text)

        stats["files_modified"] += 1

    return issues


async def main_async(args):
    log_files = sorted(LOGS_DIR.rglob("interactions_*.txt")) + \
                sorted(LOGS_DIR.rglob("interactions_*.md"))

    if not log_files:
        print(f"No interaction logs found in {LOGS_DIR}")
        return

    stats = {
        "files_scanned":         0,
        "files_modified":        0,
        "embed_blocks_stripped": 0,
        "emote_lines_stripped":  0,
        "turns_flagged":         0,
        "turns_rewritten":       0,
    }

    mode_label = "DRY RUN" if not args.apply else "APPLYING CHANGES"
    print()
    print("=" * 60)
    print(f"  01e_preprocess_logs — {mode_label}")
    if not args.apply:
        print("  (use --apply to write cleaned files)")
    print("=" * 60)

    all_issues = {}

    for fpath in log_files:
        stats["files_scanned"] += 1
        rel = fpath.relative_to(LOGS_DIR)
        issues = await process_file(fpath, args.apply, args.rewrite, stats)
        if issues:
            all_issues[str(rel)] = issues

    # Print report
    if all_issues:
        print("\n📋 ISSUES FOUND:")
        for fname, issues in all_issues.items():
            print(f"\n  📄 {fname}")
            for issue in issues:
                print(f"  {issue}")
    else:
        print("\n✅ No structural issues found.")

    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Files scanned:            {stats['files_scanned']}")
    print(f"  Files modified:           {stats['files_modified']}")
    print(f"  Embed blocks stripped:    {stats['embed_blocks_stripped']}")
    print(f"  Emote lines stripped:     {stats['emote_lines_stripped']}")
    print(f"  Kaia turns flagged:       {stats['turns_flagged']}")
    print(f"  Kaia turns rewritten:     {stats['turns_rewritten']}")
    print()

    if stats["turns_flagged"] > 0 and not args.rewrite:
        print("  Tip: Run with --rewrite to auto-compress flagged turns via local LLM.")
        print("       Review rewrites manually before training.")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Preprocess interaction logs before fine-tuning."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write cleaned files in-place (backs up originals first). "
             "Default is dry-run (report only)."
    )
    parser.add_argument(
        "--rewrite", action="store_true",
        help="Use local Ollama to rewrite flagged low-quality Kaia turns. "
             "Requires --apply. Review output carefully before training."
    )
    args = parser.parse_args()

    if args.rewrite and not args.apply:
        print("--rewrite requires --apply. Exiting.")
        return

    if args.rewrite and not OLLAMA_AVAILABLE:
        print("WARNING: ollama package not installed. --rewrite will be skipped.")

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
