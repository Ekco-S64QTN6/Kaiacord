#!/usr/bin/env python3
"""
01d_scan_length_outliers.py — Pre-training dataset audit for length-based contamination.

Run this BEFORE 03_train.py to catch any assistant turns that are suspiciously long.
Long turns (>600 chars) in a Kaia dataset are almost always contamination — news dumps,
article text, or system metadata that slipped past the banned-string filter.

Usage:
    python finetune/01d_scan_length_outliers.py
    python finetune/01d_scan_length_outliers.py --threshold 400   # stricter
    python finetune/01d_scan_length_outliers.py --dump            # print full offending text
"""

import argparse
import json
import os
import sys

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
TRAIN_FILE    = os.path.join(SCRIPT_DIR, "dataset", "train.jsonl")
EVAL_FILE     = os.path.join(SCRIPT_DIR, "dataset", "eval.jsonl")

DEFAULT_THRESHOLD = 600   # chars — anything above this is flagged


def scan_file(filepath: str, threshold: int, dump: bool) -> int:
    """Scan a JSONL file for outlier-length assistant turns. Returns count of flagged examples."""
    if not os.path.isfile(filepath):
        print(f"  SKIP: {filepath} not found.")
        return 0

    flagged = 0
    total   = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1

            try:
                ex = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [LINE {line_num}] JSON parse error: {e}")
                continue

            for msg in ex.get("messages", []):
                if msg.get("role") != "assistant":
                    continue

                content   = msg.get("content", "")
                char_count = len(content)

                if char_count > threshold:
                    flagged += 1
                    # Show a summary
                    preview = content[:120].replace("\n", " ")
                    print(f"\n  ⚠️  Line {line_num:>5} | {char_count:>5} chars")
                    print(f"         Preview: {preview}...")

                    if dump:
                        print(f"\n  ── FULL CONTENT ({'─'*50})")
                        print(content)
                        print(f"  {'─'*60}")

    return flagged, total


def main():
    parser = argparse.ArgumentParser(description="Scan dataset for long-turn contamination.")
    parser.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD,
        help=f"Flag assistant turns longer than this many chars (default: {DEFAULT_THRESHOLD})"
    )
    parser.add_argument(
        "--dump", action="store_true",
        help="Print the full content of each flagged turn (useful for identifying the source)"
    )
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Kaia Dataset — Length Outlier Scanner")
    print(f"  Threshold: >{args.threshold} chars")
    print("=" * 60)

    total_flagged = 0
    total_examples = 0

    for label, fpath in [("TRAIN", TRAIN_FILE), ("EVAL", EVAL_FILE)]:
        print(f"\n[{label}] {fpath}")
        flagged, total = scan_file(fpath, args.threshold, args.dump)
        total_flagged  += flagged
        total_examples += total
        print(f"  Scanned {total} examples, flagged {flagged} outliers.")

    print()
    print("=" * 60)
    if total_flagged == 0:
        print("  ✅ No outliers found. Dataset looks clean.")
        print("     Safe to proceed to 03_train.py")
    else:
        print(f"  🚨 FOUND {total_flagged} OUTLIER(S) — DO NOT TRAIN YET.")
        print()
        print("  Recommended next steps:")
        print("  1. Run with --dump to see the full contaminating text")
        print("  2. Find the source log file in knowledge_base/user_logs/")
        print("  3. Delete or quarantine the contaminated section from the log")
        print("  4. Re-run: python finetune/01_convert_logs.py")
        print("  5. Re-run this script to confirm zero outliers")
        print("  6. Then proceed to 03_train.py")
        print()
        print("  Tip: grep -r 'TechCrunch\\|CRUNCH\\|funding round' knowledge_base/user_logs/")
        sys.exit(1)

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
