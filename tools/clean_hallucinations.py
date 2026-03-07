import os
from pathlib import Path
import re

logs_dir = Path("./knowledge_base/user_logs")
hallucination_keywords = [
    r"(?i)\bEurasia(n)?\b",
    r"(?i)\bPan-Pacific\b",
]

def clean_logs():
    cleaned_count = 0
    for root, _, files in os.walk(logs_dir):
        for file in files:
            if file.endswith(".md"):
                filepath = Path(root) / file
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                original_content = content
                for keyword in hallucination_keywords:
                    # Remove lines containing the keywords
                    # A more complex regex might block out the whole turn
                    content = re.sub(rf"^.*{keyword}.*$\n", "", content, flags=re.MULTILINE)

                if content != original_content:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"Cleaned {filepath}")
                    cleaned_count += 1
    print(f"Total files cleaned: {cleaned_count}")

if __name__ == "__main__":
    clean_logs()
