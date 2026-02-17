import json
import os
from pathlib import Path

def clear_user_memory(did):
    path = Path("memory/social_replied_ids.json")
    if not path.exists():
        print("Memory file not found.")
        return
        
    with open(path, 'r') as f:
        data = json.load(f)
        
    original_count = len(data.get('bluesky', []))
    prefix = f"bsky:at://{did}"
    
    # Remove mentions from this DID
    data['bluesky'] = [uri for uri in data.get('bluesky', []) if not uri.startswith(prefix)]
    
    # Also clear thread counts for any thread this DID touched (conservative)
    new_thread_counts = {}
    for root_uri, users in data.get('thread_counts', {}).items():
        if isinstance(users, dict):
             # New format (per-user)
             if "lilyevesinclair.bsky.social" in users:
                 del users["lilyevesinclair.bsky.social"]
             new_thread_counts[root_uri] = users
        else:
             # Old format (total count) - we'll just keep it or clear it if the root matches her DID
             if did not in root_uri:
                 new_thread_counts[root_uri] = users
                 
    data['thread_counts'] = new_thread_counts
    
    removed_count = original_count - len(data['bluesky'])
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        
    print(f"Removed {removed_count} mentions for DID {did}.")
    print("Memory updated successfully.")

if __name__ == "__main__":
    # DID from user logs: did:plc:a5h6rrzdiowrdfxmsbe3isqi
    clear_user_memory("did:plc:a5h6rrzdiowrdfxmsbe3isqi")
