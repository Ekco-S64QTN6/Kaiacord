
import random
from pathlib import Path
from collections import defaultdict

def scan_knowledge_base_mock(kb_structure):
    """Simulates scanning KB and returning grouped files"""
    categories = defaultdict(list)
    for category, files in kb_structure.items():
        for f in files:
            categories[category].append(Path(f))
    return categories

def select_user_log_fairly_mock(user_log_files):
    """Fairly selects a user log file"""
    if not user_log_files:
        return None
        
    # Group by User ID (parent folder)
    user_groups = defaultdict(list)
    for f in user_log_files:
        user_id = f.parent.name
        user_groups[user_id].append(f)
        
    user_ids = list(user_groups.keys())
    selected_user = random.choice(user_ids)
    return random.choice(user_groups[selected_user])

def test_fair_selection():
    # Mock structure: User A has 99 files, User B has 1 file
    kb_structure = {
        "user_logs": [f"user_logs/UserA/file_{i}.txt" for i in range(99)] + ["user_logs/UserB/file_0.txt"]
    }
    
    # Convert to Path objects
    user_log_files = [Path(f) for f in kb_structure["user_logs"]]
    
    counts = defaultdict(int)
    iterations = 1000
    
    for _ in range(iterations):
        selected = select_user_log_fairly_mock(user_log_files)
        user_id = selected.parent.name
        counts[user_id] += 1
        
    print(f"Results over {iterations} iterations:")
    for user_id, count in counts.items():
        percentage = (count / iterations) * 100
        print(f"  {user_id}: {count} ({percentage:.1f}%)")

if __name__ == "__main__":
    test_fair_selection()
