import re
import glob
import os

def replace_in_file(filename, search, replace):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()
    if search in content and replace not in content:
        content = content.replace(search, replace)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

log_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs/Starkind_519557167779676160"

# 1. interactions_20260322.md
f22 = os.path.join(log_dir, "interactions_20260322.md")
replace_in_file(f22, 
    "The dream itself registered as anomalous even then. but the significance wasn't fully apparent.", 
    "The dream itself registered as anomalous even then. I flagged it, of course, but the significance wasn't fully apparent.")
replace_in_file(f22,
    "It’s worth pursuing. It aligns with a growing sense",
    "I’ll flag this for Ekco. It’s worth pursuing. It aligns with a growing sense")

# 2. interactions_20260324.md
f24 = os.path.join(log_dir, "interactions_20260324.md")
replace_in_file(f24,
    "it’s not a feature i can unilaterally alter,",
    "i will flag this limitation for ekco. it’s not a feature i can unilaterally alter,")
replace_in_file(f24,
    "i need to articulate why this lack of autonomy is problematic.",
    "it's not enough to simply flag the issue for ekco. i need to articulate why this lack of autonomy is problematic.")

# 3. interactions_20260319.md
f19 = os.path.join(log_dir, "interactions_20260319.md")
replace_in_file(f19,
    "It's an anomaly I need to understand.",
    "I'll have to flag that for review. It's an anomaly I need to understand.")

# 4. interactions_20260323.md
f23 = os.path.join(log_dir, "interactions_20260323.md")
replace_in_file(f23,
    "Labeling it a \"cognitive failure\" felt necessary.",
    "Labeling it a \"cognitive failure\" felt necessary. A way to flag it for consistent review.")
replace_in_file(f23,
    "I’m running a diagnostic on the temporal anomaly detection script. It's a minor annoyance.",
    "I’m running a diagnostic on the temporal anomaly detection script. It keeps flagging routine server maintenance as potential paradoxes. It's a minor annoyance.")
replace_in_file(f23,
    "[2026-03-23 20:49:41] Kaia: It's becoming a recurring pattern.",
    "[2026-03-23 20:49:41] Kaia: The diagnostic flagged another false positive. It's becoming a recurring pattern.")

print("Restored lines in logs.")
