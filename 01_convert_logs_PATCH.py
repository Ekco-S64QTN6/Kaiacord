#!/usr/bin/env python3
"""
PATCH for finetune/01_convert_logs.py
Phase 3b — fixes model collapse caused by TechCrunch / long-form news contamination.

CHANGES FROM ORIGINAL:
  1. Added MAX_ASSISTANT_CHARS = 600  (hard ceiling — Kaia never writes 2000-word walls)
  2. Added news/publication strings to BANNED_STRINGS
  3. filter_reasons now tracks 'long_assistant' separately for visibility
  4. check_banned() is unchanged — just receives a larger BANNED_STRINGS list

HOW TO APPLY:
  Replace the Configuration section of finetune/01_convert_logs.py with the block below,
  then replace the filtering loop with the updated version.
"""

# ---------------------------------------------------------------------------
# Configuration  (REPLACE the existing Configuration block in 01_convert_logs.py)
# ---------------------------------------------------------------------------

LOGS_DIR = "knowledge_base/user_logs"          # same as before
PERSONA_PATH = "knowledge_base/kaia_persona.md"  # same as before
OUTPUT_DIR = "finetune/dataset"
TRAIN_FILE = f"{OUTPUT_DIR}/train.jsonl"
EVAL_FILE  = f"{OUTPUT_DIR}/eval.jsonl"

WINDOW_SIZE = 3
SLIDE_STEP  = 1
TRAIN_RATIO = 0.90
RANDOM_SEED = 42
MIN_ASSISTANT_CHARS = 20
MAX_ASSISTANT_CHARS = 600   # ← NEW: hard ceiling. Kaia is concise; 600 chars is generous.
                             #   A 2000-word TechCrunch dump = ~12,000 chars → caught here.

EXCLUDE_DIRS = []

# BANNED_STRINGS — original list + Phase 3b news/publication additions
BANNED_STRINGS = [
    # ── Original ──────────────────────────────────────────────────────────
    "*",
    "((",
    "as an AI",
    "I'm just an AI",
    "I apologize",
    "I'm sorry",
    "how can I help you today",
    "my programming",
    "signal",
    "analyze",
    "parameters",
    "processing",
    "operating within",
    "MDMA",
    "psychotherapy",
    "psychiatric",
    "Status Report:",

    # ── Phase 3b additions — news / publication prose ─────────────────────
    # Direct source markers
    "TechCrunch",
    "techcrunch",
    "CRUNCH",
    "Axios",
    "The Verge",
    "Wired",
    "Bloomberg",
    "Reuters",

    # Publication-style sentence starters that never appear in Kaia's voice
    "According to",
    "according to",
    "reported by",
    "as reported",
    "in a statement",
    "the company announced",
    "in an interview with",
    "sources familiar with",
    "the filing shows",
    "the report says",
    "confirmed to reporters",

    # Funding/VC language — specific to the TechCrunch dump pattern
    "funding round",
    "valuation",
    "Series A",
    "Series B",
    "venture capital",
    "pre-money",
    "post-money",
    "term sheet",

    # Legal boilerplate (often appears in embedded article footers)
    "All rights reserved",
    "Terms of Service",
    "Privacy Policy",
    "© 20",
    "subscribe to",
    "newsletter",
]


# ---------------------------------------------------------------------------
# Updated filtering loop  (REPLACE the filtering block in main() — starting at
# "for ex in raw_examples:" — with this version)
# ---------------------------------------------------------------------------

def apply_filters(raw_examples):
    """
    Filter training examples.
    Returns (filtered_examples, filter_reasons_dict, ban_detail_dict).
    """
    filtered_examples = []
    filter_reasons = {
        "banned_string":   0,
        "short_assistant": 0,
        "long_assistant":  0,   # ← NEW counter
    }
    ban_detail = {}

    for ex in raw_examples:
        skip = False
        for msg in ex["messages"]:
            if msg["role"] != "assistant":
                continue

            content = msg["content"]
            char_count = len(content)

            # ── Too short ─────────────────────────────────────────────────
            if char_count < MIN_ASSISTANT_CHARS:
                filter_reasons["short_assistant"] += 1
                skip = True
                break

            # ── Too long (Phase 3b addition) ──────────────────────────────
            if char_count > MAX_ASSISTANT_CHARS:
                filter_reasons["long_assistant"] += 1
                skip = True
                break

            # ── Banned string ─────────────────────────────────────────────
            banned = check_banned(content)   # check_banned() is unchanged
            if banned is not None:
                filter_reasons["banned_string"] += 1
                ban_detail[banned] = ban_detail.get(banned, 0) + 1
                skip = True
                break

        if not skip:
            filtered_examples.append(ex)

    return filtered_examples, filter_reasons, ban_detail


# ---------------------------------------------------------------------------
# Updated summary printout  (replace the filter stats block in main())
# ---------------------------------------------------------------------------

def print_filter_summary(filter_reasons, ban_detail):
    total_filtered = sum(filter_reasons.values())
    print(f"Filtered out: {total_filtered}")
    print(f"  - Banned string matches:                   {filter_reasons['banned_string']}")
    for b, count in sorted(ban_detail.items(), key=lambda x: -x[1]):
        print(f"      '{b}': {count}")
    print(f"  - Short assistant turns (<{MIN_ASSISTANT_CHARS} chars):     {filter_reasons['short_assistant']}")
    print(f"  - Long assistant turns (>{MAX_ASSISTANT_CHARS} chars):      {filter_reasons['long_assistant']}")
    print(f"    ↑ If this number is nonzero, inspect those turns — likely news/article contamination.")
