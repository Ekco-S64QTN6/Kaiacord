import os
import re
import sys
from pathlib import Path

# Add project root to path to import utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from utils.kaia_rag import HallucinationDetector
except ImportError:
    # Fallback if import fails
    class HallucinationDetector:
        HALLUCINATION_PATTERNS = [
            r"juanita", r"deane", r"bonbons",
            r"behind the curtain",
            r"slow burn", r"roundabout questions",
            r"terrier with a scent", r"internal comms",
            r"elara vance", r"aurora labs", r"aurora project",
            r"kael drakkel", r"xylarite", r"stonecutters",
            r"crimson hand",
            r"elias thorne", r"maya thorne", r"aurora's team",
            r"aurora's people", r"water reclamation fiasco",
            r"routing protocols", r"car accident", r"daughter, maya"
        ]
        @classmethod
        def contains_hallucination(cls, text):
            text_lower = text.lower()
            for pattern in cls.HALLUCINATION_PATTERNS:
                if re.search(pattern, text_lower):
                    return True
            return False
        @classmethod
        def clean_response(cls, response):
            lines = response.split('\n')
            clean_lines = [line if not cls.contains_hallucination(line) else "..." for line in lines]
            return '\n'.join(clean_lines).strip()

def clean_file(file_path):
    print(f"Checking {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if HallucinationDetector.contains_hallucination(content):
        print(f"Found hallucinations in {file_path}. Cleaning...")
        # Backup
        with open(str(file_path) + ".hallucination_backup", 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Clean
        cleaned_content = HallucinationDetector.clean_response(content)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_content)
        return True
    return False

def main():
    base_dir = Path("/home/ekco/github/Kaiacord/knowledge_base/user_logs")
    cleaned_count = 0
    
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith((".txt", ".md")):
                file_path = Path(root) / file
                if clean_file(file_path):
                    cleaned_count += 1
    
    print(f"\nFinished. Cleaned {cleaned_count} files.")

if __name__ == "__main__":
    main()
