import os
import re
import shutil
import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Restore mismanaged logs to correct folders.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without moving files.")
    args = parser.parse_args()

    base_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs"
    
    # Get all subdirectories (excluding root)
    subdirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    
    # Map name prefix to subdirectory
    # e.g., "Ekco" -> "Ekco_177011971818782721"
    name_to_subdir = {}
    for d in subdirs:
        # Extract name part before the ID (assuming ID is the last part after underscore)
        match = re.search(r'^(.*)_\d{15,20}$', d)
        if match:
            full_name = match.group(1).lower().replace("_", " ")
            name_to_subdir[full_name] = d
            # Also map the first word if it's unique enough or just to be helpful
            first_word = full_name.split()[0]
            if first_word not in name_to_subdir:
                name_to_subdir[first_word] = d
        else:
            # Fallback for bluesky ones or others
            name_to_subdir[d.lower()] = d

    # Explicit Overrides / Special mappings
    name_to_subdir["autonomous broadcast"] = "Kaia-Autonomous_channel_1462239450691145924"
    name_to_subdir["ekco"] = "Ekco_177011971818782721"
    name_to_subdir["starkind"] = "Starkind_519557167779676160"
    name_to_subdir["lune"] = "Lune_795189031674970132"
    name_to_subdir["jimjam"] = "Jimjam_the_Absent_103939159357399040"

    files_moved = 0
    files_skipped = 0

    # Iterate through files in the root of user_logs
    for f in os.listdir(base_dir):
        file_path = os.path.join(base_dir, f)
        if os.path.isfile(file_path) and (f.endswith(".md") or f.endswith(".txt")) and f.startswith("interactions_"):
            print(f"Analyzing {f}...")
            
            target_subdir = None
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as file:
                    content = file.read(5000) # Read more to be sure
                    
                    # Pattern 1: # Interactions YYYYMMDD: Name OR # Interactions YYYY-MM-DD: Name
                    match = re.search(r'# Interactions [\d-]+: (.*)', content)
                    if match:
                        name = match.group(1).strip().lower().rstrip('?')
                        if name in name_to_subdir:
                            target_subdir = name_to_subdir[name]
                        elif name.split()[0] in name_to_subdir:
                             target_subdir = name_to_subdir[name.split()[0]]
                    
                    # Pattern 2: summary/keywords metadata
                    if not target_subdir:
                        # Scan keywords list
                        keywords_match = re.search(r'keywords: (.*?)(\n\w+:|\n---)', content, re.DOTALL)
                        if keywords_match:
                            keywords_text = keywords_match.group(1).lower()
                            for name in name_to_subdir:
                                if name in keywords_text:
                                    target_subdir = name_to_subdir[name]
                                    break
                        
                        # Scan summary
                        if not target_subdir:
                            summary_match = re.search(r'summary: (.*?)(\n\w+:|\n---)', content, re.DOTALL)
                            if summary_match:
                                summary_text = summary_match.group(1).lower()
                                # Check for "user 'Name'" pattern
                                user_match = re.search(r"user '([^']+)'", summary_text)
                                if user_match and user_match.group(1).lower() in name_to_subdir:
                                    target_subdir = name_to_subdir[user_match.group(1).lower()]
                                else:
                                    for name in name_to_subdir:
                                        if f" {name} " in f" {summary_text} " or f"'{name}'" in summary_text:
                                            target_subdir = name_to_subdir[name]
                                            break

                    # Pattern 3: User: (autonomous broadcast)
                    if not target_subdir and "User: (autonomous broadcast)" in content:
                        target_subdir = name_to_subdir["autonomous broadcast"]
                        
                    # Pattern 4: User: Name
                    if not target_subdir:
                        match = re.search(r'^User: ([\w ]+)', content, re.MULTILINE)
                        if match:
                            name = match.group(1).strip().lower()
                            if name in name_to_subdir:
                                target_subdir = name_to_subdir[name]
                            elif name.split()[0] in name_to_subdir:
                                target_subdir = name_to_subdir[name.split()[0]]

                    # Pattern 5: Mention of user ID
                    if not target_subdir:
                        for name, subdir in name_to_subdir.items():
                            if "_" in subdir:
                                user_id = subdir.split("_")[-1]
                                if user_id in content:
                                    target_subdir = subdir
                                    break

            except Exception as e:
                print(f"  Error reading {f}: {e}")
                files_skipped += 1
                continue

            # Final fallback for generic ones that are likely autonomous broadcasts
            if not target_subdir:
                 # If no user identified, assume it's the autonomous channel (common for generic topics)
                 target_subdir = "Kaia-Autonomous_channel_1462239450691145924"
                 print(f"  [FALLBACK] Mapping {f} to autonomous channel")

            if target_subdir:
                dest_dir = os.path.join(base_dir, target_subdir)
                dest_path = os.path.join(dest_dir, f)
                
                if args.dry_run:
                    print(f"  [DRY RUN] Would move {f} to {target_subdir}")
                else:
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)
                    shutil.move(file_path, dest_path)
                    print(f"  Moved {f} to {target_subdir}")
                files_moved += 1
            else:
                print(f"  Could not identify target for {f}")
                files_skipped += 1

    print(f"\nSummary: {files_moved} files processed, {files_skipped} skipped.")

if __name__ == "__main__":
    main()
