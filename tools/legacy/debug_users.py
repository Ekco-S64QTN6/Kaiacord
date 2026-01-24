from pathlib import Path
import os

def get_known_users_debug():
    print(f"Current working directory: {os.getcwd()}")
    
    profiles_dir = Path("./knowledge_base/user_profiles")
    print(f"Checking profiles dir: {profiles_dir.absolute()} - Exists: {profiles_dir.exists()}")
    
    users = []
    
    # Check logs dir
    logs_dir = Path("./knowledge_base/user_logs")
    print(f"Checking logs dir: {logs_dir.absolute()} - Exists: {logs_dir.exists()}")
    
    if logs_dir.exists():
        print(f"Listing contents of {logs_dir}:")
        for d in logs_dir.iterdir():
            print(f"  - {d.name} (is_dir: {d.is_dir()})")
            if d.is_dir():
                parts = d.name.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    name = "_".join(parts[:-1]).replace("_", " ")
                else:
                    name = d.name.replace("_", " ")
                
                print(f"    -> Parsed name: {name}")
                
                profile_path = d / "user_profile.md"
                print(f"    -> Checking profile: {profile_path} - Exists: {profile_path.exists()}")
                
                summary = "No profile available."
                if profile_path.exists():
                    try:
                        with open(profile_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if "QUICK REFERENCE" in content:
                                start = content.find("QUICK REFERENCE")
                                end = content.find("\n\n", start + 20)
                                if end == -1: end = len(content)
                                summary = content[start:end].replace("QUICK REFERENCE", "").strip()
                                print(f"    -> Found summary (len {len(summary)})")
                            else:
                                summary = "\n".join(content.split('\n')[:5])
                                print(f"    -> Fallback summary")
                    except Exception as e:
                        print(f"    -> Error reading profile: {e}")
                
                users.append({"name": name, "summary": summary})
                 
    unique_users = {}
    for u in users:
        unique_users[u['name']] = u['summary']
        
    result = [f"User: {name}\nSummary: {summary}" for name, summary in sorted(unique_users.items())]
    print(f"\nFinal result count: {len(result)}")
    return result

if __name__ == "__main__":
    get_known_users_debug()
