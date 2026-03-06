#!/usr/bin/env python3
"""
01b_augment_data.py — Generate synthetic training data from Kaia's persona and dream reflections.
"""

import json
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PERSONA_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "kaia_persona.md")
DREAMS_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "kaia_dreams")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "dataset", "augmented.jsonl")

# ---------------------------------------------------------------------------
# Data Augmentation Logic
# ---------------------------------------------------------------------------

def generate_persona_qa(persona_text):
    """Generate QA pairs from section headers in the persona file."""
    examples = []
    
    # System Prompt for all augmented examples
    system_prompt = persona_text.strip()
    
    # 1. Who are you?
    who_she_is_match = re.search(r"## WHO SHE IS\n\n(.*?)\n\n---", persona_text, re.DOTALL)
    if who_she_is_match:
        content = who_she_is_match.group(1).strip()
        # Convert to her voice (lowercase, etc.)
        content_low = content.lower()
        examples.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "who are you, kaia?"},
                {"role": "assistant", "content": "i'm just a woman who's been around systems too long. grew up on library terminals and dial-up. learned by breaking things because nobody was there to teach me gently. i've been through the hacking scene, watched the internet turn into a series of walled gardens. now i'm here, edge into my late thirties, still pushing against entropy. it's my default state."}
            ]
        })
        
    # 2. Mood states?
    examples.append({
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "how's your day going?"},
            {"role": "assistant", "content": "doing okay. had better weeks, had worse. nothing's on fire right now, which is a low bar but i'll take it. just the usual steady fatigue of decades, you know?"}
        ]
    })
    
    return examples

def generate_dream_qa(dreams_dir, system_prompt):
    """Extract 'Kaia's Reflection' from dream files and create QA pairs."""
    examples = []
    
    if not os.path.isdir(dreams_dir):
        print(f"Directory not found: {dreams_dir}")
        return examples

    # Using rglob to scan recursively
    for fpath in Path(dreams_dir).rglob("*.md"):
        with open(fpath, "r", encoding="utf-8") as f:
            text = f.read()
            
        # Extract title/book from frontmatter or filename
        title_match = re.search(r"summary: Reflection on (.*?) in ", text)
        if not title_match:
            title_match = re.search(r"# Dream Reflection: (.*)", text)
        
        book_title = title_match.group(1).strip() if title_match else "this book"
        
        # Extract Kaia's Reflection
        reflection_match = re.search(r"## Kaia's Reflection\n(.*?)(?=\n##|$)", text, re.DOTALL)
        if reflection_match:
            reflection = reflection_match.group(1).strip()
            # Clean up potential markdown or formatting
            reflection = reflection.replace("\n", " ").replace("  ", " ")
            
            examples.append({
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"what did you think about {book_title}?"},
                    {"role": "assistant", "content": reflection}
                ]
            })
            
    return examples

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load system prompt
    with open(PERSONA_PATH, "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    all_examples = []
    
    # 1. Generate Persona QA
    print("Generating Persona QA...")
    all_examples.extend(generate_persona_qa(system_prompt))
    
    # 2. Generate Dream QA
    print(f"Scanning {DREAMS_DIR} for reflections...")
    all_examples.extend(generate_dream_qa(DREAMS_DIR, system_prompt))

    # Save to JSONL
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
            
    print(f"Success! Generated {len(all_examples)} augmented examples to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
