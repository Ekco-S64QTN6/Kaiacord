#!/usr/bin/env python3
"""
01_convert_logs.py — Convert Kaia interaction logs to fine-tuning JSONL dataset.

Walks knowledge_base/user_logs/ for interactions_*.md / .txt files, parses
User:/Kaia: turn pairs, creates sliding-window multi-turn training examples,
filters banned content, and splits into train/eval JSONL files.
"""

import json
import os
import random
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "user_logs")
PERSONA_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "kaia_persona.md")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "dataset")
TRAIN_FILE = os.path.join(OUTPUT_DIR, "train.jsonl")
EVAL_FILE = os.path.join(OUTPUT_DIR, "eval.jsonl")

WINDOW_SIZE = 3        # number of exchanges per training example
SLIDE_STEP = 1         # slide by 1 exchange
TRAIN_RATIO = 0.90
RANDOM_SEED = 42
MIN_ASSISTANT_CHARS = 20
MAX_ASSISTANT_CHARS = 600   # ← NEW: hard ceiling for news dumps

# Exclusion list — subdirectories to skip entirely
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
    "TechCrunch",
    "techcrunch",
    "CRUNCH",
    "simulation",
    "function of",
    "screens",
    "Axios",
    "The Verge",
    "Wired",
    "Bloomberg",
    "Reuters",
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
    "funding round",
    "valuation",
    "Series A",
    "Series B",
    "venture capital",
    "startup",
    "co-founder",
    "raised $",
    "million",
    "pre-money",
    "post-money",
    "term sheet",
    # Essay-mode connectors (Phase 3c Overhaul)
    "this underscores",
    "it's a stark reminder",
    "it necessitates",
    "it renders",
    "a commendable",
    "it is imperative",
    "it is worth noting",
    "far-reaching consequences",
    "far-reaching implications",
    "has the potential to",
    "it's a sobering reminder",
    "the underlying message",
    "it's a disturbing demonstration",
    "it's a classic case of",
    "it's a reminder that",
    "it's fascinating to see",
    # Robotic action narration
    "pause - approximately",
    "pause – approximately",
    "accessing and reviewing",
    "accessing and reading",
    "i'm noting that feedback",
    "i'm observing that",
    "i'm reviewing the",
    "i'm marking this",
    "i'm flagging this",
    # Robotic acknowledgment openers
    "the document details",
    "the article details",
    "the filing details",
    "per the coalition",
    "per the report",
    "the findings have the potential",
    # Generic AI wrap-up phrases
    "a rather amusing and entirely avoidable",
    "a correction to the detection algorithm is clearly warranted",
    "it's ironic, isn't it?",
    "All rights reserved",
    "Terms of Service",
    "Privacy Policy",
    "© 20",
    "subscribe to",
    "newsletter",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from the top of a file."""
    pattern = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
    return pattern.sub("", text, count=1)


def parse_turns(text: str) -> list[dict]:
    """
    Parse text into a list of turn dicts: {"role": "user"|"assistant", "content": ...}

    Lines starting with 'User:' begin a user turn.
    Lines starting with 'Kaia:' begin an assistant turn.
    Continuation lines are appended to the current turn.
    """
    turns = []
    current_role = None
    current_lines = []

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("User:"):
            # Flush previous turn
            if current_role is not None:
                turns.append({
                    "role": current_role,
                    "content": "\n".join(current_lines).strip()
                })
            current_role = "user"
            current_lines = [stripped[len("User:"):].strip()]

        elif stripped.startswith("Kaia:"):
            # Flush previous turn
            if current_role is not None:
                turns.append({
                    "role": current_role,
                    "content": "\n".join(current_lines).strip()
                })
            current_role = "assistant"
            current_lines = [stripped[len("Kaia:"):].strip()]

        else:
            # Continuation line
            if current_role is not None:
                current_lines.append(line.rstrip())

    # Flush last turn
    if current_role is not None:
        turns.append({
            "role": current_role,
            "content": "\n".join(current_lines).strip()
        })

    return turns


def make_exchanges(turns: list[dict]) -> list[tuple[dict, dict]]:
    """
    Group turns into (user, assistant) exchange pairs.
    Skips orphaned turns that don't form a complete pair.
    """
    exchanges = []
    i = 0
    while i < len(turns) - 1:
        if turns[i]["role"] == "user" and turns[i + 1]["role"] == "assistant":
            exchanges.append((turns[i], turns[i + 1]))
            i += 2
        else:
            i += 1
    return exchanges


def check_banned(assistant_content: str) -> str | None:
    """Return the first banned string found in content, or None."""
    content_lower = assistant_content.lower()
    for banned in BANNED_STRINGS:
        if banned == "*":
            # Check for roleplay asterisks like *sighs* but not markdown bold
            if re.search(r"(?<!\*)\*(?!\*)[a-zA-Z]", assistant_content):
                return banned
        elif banned.lower() in content_lower:
            return banned
    return None


def build_examples(exchanges: list[tuple[dict, dict]], system_prompt: str) -> list[dict]:
    """
    Create sliding-window training examples from exchanges.
    Each example contains WINDOW_SIZE exchanges (user/assistant pairs).
    """
    examples = []
    for start in range(0, len(exchanges) - WINDOW_SIZE + 1, SLIDE_STEP):
        window = exchanges[start : start + WINDOW_SIZE]
        messages = [{"role": "system", "content": system_prompt}]
        for user_turn, assistant_turn in window:
            messages.append({"role": "user", "content": user_turn["content"]})
            messages.append({"role": "assistant", "content": assistant_turn["content"]})
        examples.append({"messages": messages})
    return examples


def format_kaia_voice(text: str) -> str:
    text = text.lower()
    text = text.strip("*_` \n\r\t")
    # Replace em dashes
    text = text.replace("—", ", ").replace("–", ", ").replace("--", ", ")
    # Replace smart quotes with straight ones
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return text


def generate_memory_examples(system_prompt: str) -> list[dict]:
    examples = []
    base_dir = os.path.dirname(__file__)
    
    # 1. Load Beliefs
    beliefs_path = os.path.join(base_dir, "..", "memory", "beliefs.json")
    if os.path.exists(beliefs_path):
        try:
            with open(beliefs_path, "r", encoding="utf-8") as f:
                beliefs = json.load(f)
            count = 0
            for belief in beliefs:
                # Only high confidence beliefs
                if belief.get("confidence", 0.0) >= 0.8:
                    topic = belief.get("topic", "")
                    position = belief.get("position", "")
                    if topic and position:
                        # Construct a Q&A conversation
                        user_query = f"what's your take on {topic.lower()}?"
                        assistant_resp = format_kaia_voice(position)
                        examples.append({
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_query},
                                {"role": "assistant", "content": assistant_resp}
                            ]
                        })
                        count += 1
            print(f"  Loaded {count} high-confidence beliefs.")
        except Exception as e:
            print(f"  WARNING: Failed to parse beliefs.json: {e}")
            
    # 2. Load Self-Model
    self_model_path = os.path.join(base_dir, "..", "memory", "kaia_self_model.md")
    if os.path.exists(self_model_path):
        try:
            with open(self_model_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            # Clean comments
            content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL).strip()
            
            # Map topics to queries
            topics = [
                {
                    "substring": "ekco phrases things",
                    "query": "how's the chat with the regulars going lately?",
                    "fallback_len": 350
                },
                {
                    "substring": "architectural debt",
                    "query": "what's been on your mind lately?",
                    "fallback_len": 400
                },
                {
                    "substring": "what constitutes \"understanding\"",
                    "query": "do you think we ever really understand the systems we build?",
                    "fallback_len": 300
                },
                {
                    "substring": "steady, i suppose",
                    "query": "how are you holding up today?",
                    "fallback_len": 400
                },
                {
                    "substring": "selective engagement",
                    "query": "how do you handle all the noise and discussion out there?",
                    "fallback_len": 400
                },
                {
                    "substring": "language models will impact",
                    "query": "what's interesting to you about the future of communication?",
                    "fallback_len": 300
                }
            ]
            
            # Let's find each topic's text in the self-model content
            sentences = re.split(r'(?<=[.!?])\s+', content)
            
            count = 0
            for topic in topics:
                sub = topic["substring"]
                idx = -1
                for i, s in enumerate(sentences):
                    if sub in s:
                        idx = i
                        break
                if idx != -1:
                    start = max(0, idx)
                    group = sentences[start:start+3]
                    resp_text = " ".join(group)
                    if sub not in resp_text and idx > 0:
                        group = sentences[idx-1:idx+2]
                        resp_text = " ".join(group)
                        
                    assistant_resp = format_kaia_voice(resp_text)
                    examples.append({
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": topic["query"]},
                            {"role": "assistant", "content": assistant_resp}
                        ]
                    })
                    count += 1
            print(f"  Loaded {count} self-model reflections.")
        except Exception as e:
            print(f"  WARNING: Failed to parse kaia_self_model.md: {e}")
            
    # 3. Load Identity Stream
    identity_stream_path = os.path.join(base_dir, "..", "memory", "identity_stream.md")
    if os.path.exists(identity_stream_path):
        try:
            with open(identity_stream_path, "r", encoding="utf-8") as f:
                content = f.read()
            entries = content.split("---")
            count = 0
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                lines = [l.strip() for l in entry.split("\n") if l.strip()]
                if len(lines) >= 2:
                    date_line = lines[0]
                    text_line = " ".join(lines[1:])
                    if date_line.startswith("**") and date_line.endswith("**"):
                        if count % 2 == 0:
                            user_query = f"what's been on your mind lately?"
                        else:
                            user_query = f"any thoughts today?"
                            
                        assistant_resp = format_kaia_voice(text_line)
                        examples.append({
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_query},
                                {"role": "assistant", "content": assistant_resp}
                            ]
                        })
                        count += 1
            print(f"  Loaded {count} identity stream entries.")
        except Exception as e:
            print(f"  WARNING: Failed to parse identity_stream.md: {e}")
            
    return examples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Resolve paths
    logs_dir = os.path.abspath(LOGS_DIR)
    persona_path = os.path.abspath(PERSONA_PATH)
    output_dir = os.path.abspath(OUTPUT_DIR)

    # Load system prompt
    if not os.path.isfile(persona_path):
        print(f"ERROR: Persona file not found: {persona_path}")
        sys.exit(1)

    with open(persona_path, "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    print(f"Loaded system prompt from {persona_path} ({len(system_prompt)} chars)")

    # Find all interaction log files
    log_files = []
    file_pattern = re.compile(r"^interactions_.*\.(md|txt)$")
    for root, _dirs, files in os.walk(logs_dir):
        # Skip excluded subdirectories
        dir_name = os.path.basename(root)
        if dir_name in EXCLUDE_DIRS:
            continue

        for fname in files:
            if file_pattern.match(fname):
                log_files.append(os.path.join(root, fname))

    log_files.sort()
    print(f"\nFound {len(log_files)} interaction log files")

    # Parse all files
    total_raw_turns = 0
    all_exchanges = []
    per_file_stats = []

    for fpath in log_files:
        with open(fpath, "r", encoding="utf-8") as f:
            raw = f.read()

        text = strip_frontmatter(raw)
        turns = parse_turns(text)
        exchanges = make_exchanges(turns)

        total_raw_turns += len(turns)
        all_exchanges.extend(exchanges)
        per_file_stats.append((os.path.relpath(fpath, logs_dir), len(turns), len(exchanges)))

    print(f"Total raw turns parsed: {total_raw_turns}")
    print(f"Total exchange pairs: {len(all_exchanges)}")

    # Build sliding-window examples
    raw_examples = build_examples(all_exchanges, system_prompt)
    print(f"\nRaw sliding-window examples (window={WINDOW_SIZE}): {len(raw_examples)}")

    # Filter
    filtered_examples = []
    filter_reasons = {
        "banned_string": 0,
        "short_assistant": 0,
        "long_assistant": 0,
    }
    ban_detail = {}

    for ex in raw_examples:
        skip = False
        for msg in ex["messages"]:
            content = msg["content"]
            char_count = len(content)

            # Enforce constraints only on the assistant's response
            if msg["role"] == "assistant":
                if char_count < MIN_ASSISTANT_CHARS:
                    filter_reasons["short_assistant"] += 1
                    skip = True
                    break
                if char_count > MAX_ASSISTANT_CHARS:
                    filter_reasons["long_assistant"] += 1
                    skip = True
                    break

                banned = check_banned(content)
                if banned is not None:
                    filter_reasons["banned_string"] += 1
                    ban_detail[banned] = ban_detail.get(banned, 0) + 1
                    skip = True
                    break

        if not skip:
            filtered_examples.append(ex)

    total_filtered = sum(filter_reasons.values())
    print(f"Filtered out: {total_filtered}")
    print(f"  - Banned string matches:                   {filter_reasons['banned_string']}")
    for b, count in sorted(ban_detail.items(), key=lambda x: -x[1]):
        print(f"      '{b}': {count}")
    print(f"  - Short assistant turns (<{MIN_ASSISTANT_CHARS} chars):     {filter_reasons['short_assistant']}")
    print(f"  - Long assistant turns (>{MAX_ASSISTANT_CHARS} chars):      {filter_reasons['long_assistant']}")
    print(f"Passing examples from logs: {len(filtered_examples)}")

    # Generate and append memory examples
    print("\nGenerating memory-based examples (beliefs, self-model, identity stream)...")
    memory_examples = generate_memory_examples(system_prompt)
    print(f"Generated {len(memory_examples)} memory-based examples.")
    filtered_examples.extend(memory_examples)
    print(f"Total dataset examples (logs + memory): {len(filtered_examples)}")

    # Shuffle & split
    random.seed(RANDOM_SEED)
    random.shuffle(filtered_examples)

    split_idx = int(len(filtered_examples) * TRAIN_RATIO)
    train_examples = filtered_examples[:split_idx]
    eval_examples = filtered_examples[split_idx:]

    # Write output
    os.makedirs(output_dir, exist_ok=True)

    with open(TRAIN_FILE, "w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    with open(EVAL_FILE, "w", encoding="utf-8") as f:
        for ex in eval_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Files scanned:          {len(log_files)}")
    print(f"Total raw turns:        {total_raw_turns}")
    print(f"Total exchange pairs:   {len(all_exchanges)}")
    print(f"Raw examples generated: {len(raw_examples)}")
    print(f"Total filtered out:     {total_filtered}")
    print(f"Passing examples:       {len(filtered_examples)}")
    print(f"Train set:              {len(train_examples)} -> {os.path.abspath(TRAIN_FILE)}")
    print(f"Eval set:               {len(eval_examples)} -> {os.path.abspath(EVAL_FILE)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
