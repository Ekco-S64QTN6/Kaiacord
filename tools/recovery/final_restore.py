import os
import shutil
import re

kb_root = "/home/ekco/github/Kaiacord/knowledge_base"
doc_dir = os.path.join(kb_root, "documents")

# Target folders
BOOKS = os.path.join(kb_root, "Books")
NEWS = os.path.join(kb_root, "news")
USER_LOGS = os.path.join(kb_root, "user_logs")
REPORTS = os.path.join(kb_root, "deep_dive_reports")
DREAMS_INTERACTIONS = os.path.join(kb_root, "kaia_dreams", "interactions")
DREAMS_INJECTED = os.path.join(kb_root, "kaia_dreams", "injected")

os.makedirs(BOOKS, exist_ok=True)
os.makedirs(NEWS, exist_ok=True)
os.makedirs(USER_LOGS, exist_ok=True)
os.makedirs(REPORTS, exist_ok=True)
os.makedirs(DREAMS_INTERACTIONS, exist_ok=True)
os.makedirs(DREAMS_INJECTED, exist_ok=True)

# Book/Literature authors and titles
literary_cues = [
    "Aldous Huxley", "William Gibson", "Neal Stephenson", "Marcus Aurelius",
    "Phillip K. Dick", "Hitchhikers Guide", "Hagakure", "Johnny Mnemonic",
    "Deus Ex", "Ghost in the Shell", "Cyberpunk 2077", "Victor Wilfred",
    "Man a Machine", "Three-Body Problem"
]

# Report cues
report_cues = [
    "Report", "Research", "Specification", "Migration", "Deep Dive", "TL;DR",
    "Case Studies", "Safety Report", "Stock Market Shocks", "Design Report",
    "Technical Cheat Sheet"
]

files = [f for f in os.listdir(doc_dir) if os.path.isfile(os.path.join(doc_dir, f))]

count = 0
for filename in files:
    src = os.path.join(doc_dir, filename)
    dest_dir = None
    
    # 1. Dreams
    if filename.startswith("injected_"):
        dest_dir = DREAMS_INJECTED
    elif filename.startswith("interactions_") and "_" in filename:
        # Check if it's a date-based log
        if re.search(r"interactions_\d{8}", filename):
            dest_dir = USER_LOGS
        else:
            dest_dir = DREAMS_INTERACTIONS
    
    # 2. News (dates or brief/summary)
    elif re.match(r"^\d{4}-\d{2}-\d{2}", filename) or "news_brief" in filename or "news_summary" in filename:
        dest_dir = NEWS
        
    # 3. Books
    elif any(cue.lower() in filename.lower() for cue in literary_cues):
        dest_dir = BOOKS
        
    # 4. Reports
    elif any(cue.lower() in filename.lower() for cue in report_cues):
        dest_dir = REPORTS
        
    # Default to documents if unknown (already there, but for completeness)
    else:
        continue
        
    if dest_dir:
        dest_path = os.path.join(dest_dir, filename)
        print(f"Moving {filename} -> {os.path.relpath(dest_dir, kb_root)}")
        shutil.move(src, dest_path)
        count += 1

print(f"Total files restored: {count}")
