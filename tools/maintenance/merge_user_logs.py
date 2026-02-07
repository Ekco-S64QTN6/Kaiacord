import os
import shutil

USER_LOGS_DIR = "/home/ekco/github/Kaiacord/knowledge_base/user_logs"

def merge_folders(src_name, dst_name):
    src_path = os.path.join(USER_LOGS_DIR, src_name)
    dst_path = os.path.join(USER_LOGS_DIR, dst_name)
    
    if not os.path.exists(src_path):
        print(f"Source folder not found: {src_name}")
        return
    
    if not os.path.exists(dst_path):
        print(f"Destination folder not found: {dst_name}. Renaming source.")
        os.rename(src_path, dst_path)
        return

    print(f"Merging {src_name} into {dst_name}...")
    for item in os.listdir(src_path):
        s = os.path.join(src_path, item)
        d = os.path.join(dst_path, item)
        if os.path.isdir(s):
            # Not expecting nested dirs in user_logs, but handle just in case
            if os.path.exists(d):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.move(s, d)
        else:
            # Handle filename collision (e.g. interactions_YYYYMMDD.txt)
            if os.path.exists(d):
                print(f"  Appending {item} content...")
                with open(s, 'r') as f_src:
                    content = f_src.read()
                with open(d, 'a') as f_dst:
                    f_dst.write("\n--- MERGED CONTENT ---\n")
                    f_dst.write(content)
                os.remove(s)
            else:
                shutil.move(s, d)
    
    # Remove empty src dir
    try:
        os.rmdir(src_path)
        print(f"  Successfully removed {src_name}")
    except OSError:
        print(f"  Warning: Could not remove {src_name} (not empty?)")

# Define merges
merges = [
    ("ekco_177011971818782721", "Ekco_177011971818782721"),
    ("gnowm_579396554536910859", "MetroGnowmOSexual_579396554536910859"),
    ("manstache_919782120308752425", "Tennō_Heika_919782120308752425"),
    ("starkind_519557167779676160", "Starkind_519557167779676160"),
    ("social_bluesky_michaelschellhorn.link", "Ekco_177011971818782721")
]

if __name__ == "__main__":
    for src, dst in merges:
        merge_folders(src, dst)
    print("Merge operations complete.")
