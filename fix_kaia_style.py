#!/usr/bin/env python3
"""
fix_kaia_style.py — One-time batch cleanup of Kaia's style artifacts
=====================================================================

Scans interaction logs and dream files for excessive em dashes, ellipses,
and asterisked emphasis in Kaia's responses. Replaces them with standard
punctuation to prevent the RAG feedback loop from re-contaminating the
pipeline.

Usage:
    python3 fix_kaia_style.py --dry-run     # Preview changes without writing
    python3 fix_kaia_style.py               # Apply changes in-place
    python3 fix_kaia_style.py --dreams-only # Only clean dream files
    python3 fix_kaia_style.py --logs-only   # Only clean interaction logs
"""

import os
import re
import sys
import argparse
from pathlib import Path


# ── Sanitization Logic ────────────────────────────────────────────────────

def sanitize_style_artifacts(text: str) -> str:
    """Strip excessive em dashes, ellipses, and asterisked emphasis."""
    if not text:
        return text

    # 1. Replace em dashes with commas or periods
    result = re.sub(r'(\w)\u2014(\w)', r'\1, \2', text)
    result = re.sub(r'(\w)\u2014\s', r'\1. ', result)
    result = re.sub(r'\s\u2014(\w)', r'. \1', result)
    result = re.sub(r'\u2014', ', ', result)

    # 2. Collapse ellipses (unicode … and triple dots)
    result = result.replace('\u2026', '.')
    result = re.sub(r'\.{2,}', '.', result)

    # 3. Strip single-asterisk emphasis, preserve **bold**
    result = re.sub(r'(?<!\*)\*(?!\*)([^*]+?)(?<!\*)\*(?!\*)', r'\1', result)

    # 4. Clean up resulting double punctuation and spacing
    result = re.sub(r'[,\.]\s*[,\.]', '.', result)
    result = re.sub(r'\s{2,}', ' ', result)

    return result


# ── Interaction Log Cleaning ──────────────────────────────────────────────

def clean_interaction_log(filepath: Path, dry_run: bool = False) -> dict:
    """Clean Kaia's responses in an interaction log file.
    
    Only modifies lines that start with a timestamp + 'Kaia:' prefix.
    User messages are left untouched.
    """
    content = filepath.read_text(encoding='utf-8', errors='ignore')
    
    # Count pre-cleanup artifacts in Kaia lines
    kaia_blocks = re.findall(r'\] Kaia: (.*?)(?=\n\[|\Z)', content, re.DOTALL)
    kaia_text = ' '.join(kaia_blocks)
    
    before_dashes = kaia_text.count('\u2014')
    before_ellipses = len(re.findall(r'\.{3}|\u2026', kaia_text))
    
    if before_dashes == 0 and before_ellipses == 0:
        return {"file": str(filepath), "skipped": True, "reason": "clean"}
    
    # Only sanitize Kaia's response portions
    def replace_kaia_response(match):
        prefix = match.group(1)  # timestamp + "Kaia: "
        response = match.group(2)
        cleaned = sanitize_style_artifacts(response)
        return f"{prefix}{cleaned}"
    
    # Pattern: [timestamp] Kaia: <response text until next [timestamp] or EOF
    cleaned_content = re.sub(
        r'(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Kaia: )(.*?)(?=\n\[\d{4}|\Z)',
        replace_kaia_response,
        content,
        flags=re.DOTALL
    )
    
    if cleaned_content == content:
        return {"file": str(filepath), "skipped": True, "reason": "no changes"}
    
    # Count post-cleanup
    kaia_blocks_after = re.findall(r'\] Kaia: (.*?)(?=\n\[|\Z)', cleaned_content, re.DOTALL)
    kaia_text_after = ' '.join(kaia_blocks_after)
    after_dashes = kaia_text_after.count('\u2014')
    after_ellipses = len(re.findall(r'\.{3}|\u2026', kaia_text_after))
    
    if not dry_run:
        filepath.write_text(cleaned_content, encoding='utf-8')
    
    return {
        "file": str(filepath.name),
        "skipped": False,
        "dashes": f"{before_dashes} → {after_dashes}",
        "ellipses": f"{before_ellipses} → {after_ellipses}",
    }


# ── Dream File Cleaning ──────────────────────────────────────────────────

def clean_dream_file(filepath: Path, dry_run: bool = False) -> dict:
    """Clean Kaia's Reflection section in a dream file.
    
    Only modifies the '## Kaia's Reflection' section. Metadata and
    source material sections are left untouched.
    """
    content = filepath.read_text(encoding='utf-8', errors='ignore')
    
    # Find reflection section
    match = re.search(r"(## Kaia'?s Reflection\n)(.*?)(\n## |\Z)", content, re.DOTALL)
    if not match:
        return {"file": str(filepath.name), "skipped": True, "reason": "no reflection section"}
    
    reflection = match.group(2)
    before_dashes = reflection.count('\u2014')
    before_ellipses = len(re.findall(r'\.{3}|\u2026', reflection))
    
    if before_dashes == 0 and before_ellipses == 0:
        return {"file": str(filepath.name), "skipped": True, "reason": "clean"}
    
    cleaned_reflection = sanitize_style_artifacts(reflection)
    cleaned_content = content[:match.start(2)] + cleaned_reflection + content[match.end(2):]
    
    if not dry_run:
        filepath.write_text(cleaned_content, encoding='utf-8')
    
    return {
        "file": str(filepath.name),
        "skipped": False,
        "dashes": f"{before_dashes} → 0",
        "ellipses": f"{before_ellipses} → 0",
    }


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Clean Kaia style artifacts from logs and dreams")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--logs-only", action="store_true", help="Only clean interaction logs")
    parser.add_argument("--dreams-only", action="store_true", help="Only clean dream files")
    parser.add_argument("--since", default="20260526", help="Only clean logs from this date onward (YYYYMMDD)")
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent
    user_logs_dir = base_dir / "knowledge_base" / "user_logs"
    dreams_dir = base_dir / "knowledge_base" / "kaia_dreams"
    
    if args.dry_run:
        print("=" * 60)
        print("  DRY RUN — no files will be modified")
        print("=" * 60)
    
    total_logs_cleaned = 0
    total_dreams_cleaned = 0
    
    # ── Clean Interaction Logs ──
    if not args.dreams_only:
        print(f"\n{'='*60}")
        print(f"  INTERACTION LOGS (since {args.since})")
        print(f"{'='*60}")
        
        for user_dir in sorted(user_logs_dir.iterdir()):
            if not user_dir.is_dir():
                continue
            
            log_files = sorted(user_dir.glob("interactions_*.md"))
            for log_file in log_files:
                # Extract date from filename
                date_match = re.search(r'interactions_(\d{8})', log_file.name)
                if date_match and date_match.group(1) < args.since:
                    continue
                
                result = clean_interaction_log(log_file, dry_run=args.dry_run)
                if not result.get("skipped"):
                    total_logs_cleaned += 1
                    action = "[DRY]" if args.dry_run else "[FIXED]"
                    print(f"  {action} {user_dir.name}/{result['file']}: "
                          f"dashes={result['dashes']}, ellipses={result['ellipses']}")
        
        print(f"\n  Logs cleaned: {total_logs_cleaned}")
    
    # ── Clean Dream Files ──
    if not args.logs_only:
        print(f"\n{'='*60}")
        print(f"  DREAM FILES")
        print(f"{'='*60}")
        
        for dream_file in sorted(dreams_dir.rglob("*.md")):
            result = clean_dream_file(dream_file, dry_run=args.dry_run)
            if not result.get("skipped"):
                total_dreams_cleaned += 1
                action = "[DRY]" if args.dry_run else "[FIXED]"
                print(f"  {action} {result['file']}: "
                      f"dashes={result['dashes']}, ellipses={result['ellipses']}")
        
        print(f"\n  Dreams cleaned: {total_dreams_cleaned}")
    
    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Interaction logs cleaned: {total_logs_cleaned}")
    print(f"  Dream files cleaned:      {total_dreams_cleaned}")
    print(f"  Total files modified:     {total_logs_cleaned + total_dreams_cleaned}")
    if args.dry_run:
        print(f"\n  Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
