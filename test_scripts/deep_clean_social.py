import json
from pathlib import Path

def wipe_bluesky_replied_ids():
    path = Path("memory/social_replied_ids.json")
    if not path.exists():
        print("Memory file not found.")
        return
        
    with open(path, 'r') as f:
        data = json.load(f)
        
    # Wipe the whole bluesky list to force a 3-hour re-scan.
    # The reconstruction logic at boot will re-populate it with actual replies 
    # to prevent double-posting for recent messages.
    original_count = len(data.get('bluesky', []))
    data['bluesky'] = []
    
    # Also clear thread counts for safety (they will be rebuilt)
    data['thread_counts'] = {}
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Wiped {original_count} Bluesky IDs and thread counts.")
    print("Memory reset for full re-scan.")

if __name__ == "__main__":
    wipe_bluesky_replied_ids()
