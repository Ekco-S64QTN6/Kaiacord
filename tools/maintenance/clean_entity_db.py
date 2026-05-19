#!/usr/bin/env python3
import json
import os
from pathlib import Path

# Common junk words found in extracted entity logs
COMMON_JUNK = {
    "According", "Accumulated", "Accused", "Acknowledge", "Acknowledged", 
    "make", "draw", "analyze", "check", "run", "start", "stop", "open", "close",
    "get", "set", "put", "call", "ask", "say", "see", "look", "wait", "hold",
    "keep", "go", "come", "back", "right", "left", "also", "then", "now", "still",
    "Be", "Behavioral", "Build", "Compare", "Communication", "Consistency",
    "Constraint", "Constraints", "Foundation", "Logic", "Theory", "Knowledge",
    "Actions", "Active", "Actively", "Ada", "Add", "Adding", "Adiabatic", 
    "Adjust", "Admit", "Admitted", "Aesthetic", "Action", "Appendix",
    "Approach", "Area", "Areas", "Art", "Article", "Articles", "Aspect",
    "Aspects", "Assume", "Assumed", "Assumption", "Assumptions", "Author",
}

def clean_db(db_path, kb_path):
    print(f"🧹 Deep Cleaning {db_path}...")
    
    if not os.path.exists(db_path):
        print("❌ Error: Database not found.")
        return

    with open(db_path, 'r') as f:
        data = json.load(f)

    # 1. Build a set of "Valid" entities from the current KB structure
    valid_entities = set()
    
    # User Logs (Directories)
    user_logs = Path(kb_path) / "user_logs"
    if user_logs.exists():
        for d in user_logs.iterdir():
            if d.is_dir() and "_" in d.name:
                valid_entities.add(d.name.rsplit("_", 1)[0].replace("_", " ").lower())

    # Other Folders (Filenames)
    for subdir in ["Books", "news", "deep_dive_reports", "blogs", "forum_posts"]:
        folder = Path(kb_path) / subdir
        if folder.exists():
            for f in folder.rglob("*"):
                if f.is_file() and not f.name.startswith("."):
                    clean_name = f.stem.replace("_", " ").replace("-", " ")
                    valid_entities.add(clean_name.lower())

    # 2. Filter the existing database
    cleaned_entities = {}
    total_removed = 0
    total_kept = 0
    
    # Load common_entities.json for additional filtering
    common_entities_path = "config/common_entities.json"
    common_words = set()
    if os.path.exists(common_entities_path):
        with open(common_entities_path, 'r') as f:
            cf_data = json.load(f)
            common_words = {w.lower() for w in cf_data.get("common_words", [])}

    for category, items in data['entities'].items():
        new_items = []
        for item in items:
            item_low = item.lower()
            
            # REMOVAL RULES:
            # - Is it in our JUNK list?
            # - Is it a common word in the config?
            # - Is it NOT in the current KB and NOT a multi-word phrase (high signal)?
            
            # NEW RULES:
            # - No newlines (it's a mangled sentence fragment)
            # - No trailing common stop-words
            if '\n' in item:
                total_removed += 1
                continue
                
            if item.split()[-1].lower() in {'the', 'a', 'an', 'for', 'with', 'in', 'on', 'at', 'to', 'is', 'are'}:
                total_removed += 1
                continue

            if item in COMMON_JUNK or item_low in common_words:
                total_removed += 1
                continue
                
            if len(item) < 3:
                total_removed += 1
                continue
            
            # If it's single-word and doesn't exist in the current KB structure, it's likely junk
            if ' ' not in item and item_low not in valid_entities:
                # Keep only very high signal single words if you want, 
                # but for an aggressive purge, we drop orphans.
                total_removed += 1
                continue
                
            new_items.append(item)
            total_kept += 1
        
        cleaned_entities[category] = sorted(list(set(new_items)))
    
    data['entities'] = cleaned_entities
    data['timestamp'] = f"PURGED-{os.popen('date +%Y%m%d').read().strip()}"
    
    with open(db_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✨ Cleanup complete.")
    print(f"   - Removed: {total_removed} orphans/junk")
    print(f"   - Kept: {total_kept} legitimate entities")

if __name__ == "__main__":
    clean_db("memory/entity_database.json", "knowledge_base")
