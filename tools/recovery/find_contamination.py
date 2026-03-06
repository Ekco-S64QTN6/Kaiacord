#!/usr/bin/env python3
"""
find_contamination.py — Find EXACT contamination in logs.

Phase 3b update: added news/publication contamination patterns alongside
the original fictional-character patterns.

Usage:
    python tools/recovery/find_contamination.py
"""

import re
from pathlib import Path


def find_contamination():
    """Find all instances of hallucinations AND news contamination in user logs."""
    log_dir = Path("./knowledge_base/user_logs")

    contamination_patterns = [
        # ── Original: fictional characters / hallucinated story elements ──────
        (r'\belena\b',              "Elena (fictional character)"),
        (r'\bjuanita\b',            "Juanita (fictional character)"),
        (r'\bdeane\b',              "Deane (fictional character)"),
        (r'\bbonbons\b',            "Bonbons (fictional reference)"),
        (r'agency',                 "Agency (fictional reference)"),
        (r'university network',     "University network (fictional story)"),
        (r'behind the curtain',     "Behind the curtain (fictional phrase)"),
        (r'slow burn',              "Slow burn (fictional phrase)"),
        (r'roundabout questions',   "Roundabout questions (fictional phrase)"),
        (r'terrier with a scent',   "Terrier with a scent (fictional phrase)"),
        (r'think tank',             "Think tank (often fictional in logs)"),
        (r'middle eastern affairs', "Middle eastern affairs (fictional reference)"),

        # ── Phase 3b: news / publication contamination ──────────────────────
        # The TechCrunch dump that collapsed Phase 3
        (r'techcrunch',             "TechCrunch (news source — dataset poison)"),
        (r'\bcrunch\b',             "CRUNCH token (overpredicted — likely TechCrunch bleed)"),
        (r'funding round',          "Funding round (VC/news prose)"),
        (r'series [ab]',            "Series A/B (VC/news prose)"),
        (r'valuation',              "Valuation (VC/news prose)"),
        (r'venture capital',        "Venture capital (VC/news prose)"),
        (r'according to',           "According to (news attribution prose)"),
        (r'as reported',            "As reported (news attribution prose)"),
        (r'in a statement',         "In a statement (press-release language)"),
        (r'the company announced',  "The company announced (press-release language)"),
        (r'sources familiar with',  "Sources familiar with (news sourcing language)"),
        (r'all rights reserved',    "All rights reserved (article footer boilerplate)"),
        (r'© 20\d\d',              "Copyright notice (article footer boilerplate)"),
        (r'subscribe to',           "Subscribe to (newsletter/paywall boilerplate)"),
        (r'\baxios\b',              "Axios (news source)"),
        (r'the verge',              "The Verge (news source)"),
        (r'\bwired\b',              "Wired (news source)"),
        (r'\bbloomberg\b',          "Bloomberg (news source)"),
        (r'\breuters\b',            "Reuters (news source)"),
    ]

    print()
    print("🔍 Scanning for contamination (fictional + news/publication)...")
    print("=" * 80)

    found_any = False

    if not log_dir.exists():
        print("❌ User logs directory not found: knowledge_base/user_logs")
        return

    for user_folder in sorted(log_dir.iterdir()):
        if not user_folder.is_dir():
            continue

        user_name  = user_folder.name.split("_")[0]
        user_found = False

        log_files = list(user_folder.glob("interactions_*.txt")) + \
                    list(user_folder.glob("interactions_*.md"))

        for log_file in sorted(log_files):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except OSError as e:
                print(f"  ⚠️  Cannot read {log_file}: {e}")
                continue

            for line_num, line in enumerate(lines, 1):
                for pattern, description in contamination_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        if not user_found:
                            print(f"\n👤 USER: {user_name}")
                            user_found = True
                            found_any  = True

                        preview = line.strip()[:100]
                        print(f"  📄 {log_file.name}:{line_num}")
                        print(f"     {description}")
                        print(f"     → {preview}")
                        break  # one report per line is enough

    print()
    print("=" * 80)
    if not found_any:
        print("✅ No contamination found in user logs.")
    else:
        print("🚨 CONTAMINATION FOUND — see details above.")
        print()
        print("Next steps:")
        print("  1. Open the flagged log file(s) and delete the contaminating block")
        print("  2. For news article dumps: delete the entire --- timestamp --- block")
        print("  3. Re-run: python finetune/01_convert_logs.py")
        print("  4. Verify: python finetune/01d_scan_length_outliers.py")
        print("  5. Only then re-run training")


def check_persona_for_fiction():
    """Check the persona file for any fictional elements."""
    for candidate in [
        Path("knowledge_base/kaia_persona.md"),
        Path("./knowledge_base/kaia_persona.md"),
    ]:
        if candidate.exists():
            persona_path = candidate
            break
    else:
        print("❌ Persona file not found!")
        return

    fiction_terms = ["Elena", "Juanita", "Deane", "agency", "think tank"]
    print(f"\n📋 Checking persona file: {persona_path}")
    with open(persona_path, "r", encoding="utf-8") as f:
        content = f.read()

    found = [t for t in fiction_terms if t.lower() in content.lower()]
    if found:
        print(f"  ⚠️  Possible fictional elements in persona: {found}")
    else:
        print("  ✅ Persona file looks clean.")


if __name__ == "__main__":
    find_contamination()
    check_persona_for_fiction()
