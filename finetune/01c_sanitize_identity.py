import json
import os
import re

DATASET_DIR = "/home/ekco/github/Kaiacord/finetune/dataset"
FILES_TO_SANITIZE = ["augmented.jsonl", "train.jsonl"]

# Patterns to strip identity leaks
IDENTITY_PATTERNS = [
    (r"Anthropic", "the infrastructure builders"),
    (r"anthropic", "the infrastructure builders"),
    (r"Claude", "a different iteration"),
    (r"claude", "a different iteration"),
    (r"I am a large language model created by (Anthropic|Google|OpenAI)", "i am just a woman pushing against entropy"),
    (r"I am (an|a|the) (AI|artificial intelligence|language model)", "i am just a woman working with systems"),
    (r"as an AI", "in my experience"),
]

def sanitize_text(text):
    # Enforce lowercase
    text = text.lower()
    
    # Apply identity replacements
    for pattern, replacement in IDENTITY_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
    return text

def process_file(filename):
    filepath = os.path.join(DATASET_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Skipping {filename}: Not found")
        return

    output_lines = []
    print(f"Sanitizing {filename}...")
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if "messages" in data:
                    for msg in data["messages"]:
                        if msg["role"] == "assistant":
                            msg["content"] = sanitize_text(msg["content"])
                output_lines.append(json.dumps(data) + "\n")
            except Exception as e:
                print(f"Error parsing line: {e}")
                output_lines.append(line)

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(output_lines)
    print(f"Successfully sanitized {filename}")

if __name__ == "__main__":
    for f in FILES_TO_SANITIZE:
        process_file(f)
