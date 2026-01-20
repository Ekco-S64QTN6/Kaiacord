import os
import glob
import re

log_dir = "knowledge_base/user_logs"

def clean_logs():
    patterns_to_remove = [
        r"\[IDLE_QUIP:.*?\]",
        r"\[REMEMBER_COMMAND\]:.*",
        r"- IDENTITY RESONANCE:.*",
        r"- \[KAIA_PERSONA_FRAGMENT\].*",
        r"IDENTITY RESONANCE:.*",
        r"\[KAIA_PERSONA_FRAGMENT\].*",
        r"NARRATIVE AUTONOMY:.*",
        r"\[HISTORICAL_CONTEXT\].*",
        r"\[CRITICAL_RULES\].*",
        r"\[END_CONTEXT\].*",
        r"\[USER_PROFILE_AND_HISTORY:.*?\]"
    ]
    
    log_files = glob.glob(os.path.join(log_dir, "**", "interactions_*.txt"), recursive=True)
    
    for log_file in log_files:
        print(f"Cleaning {log_file}...")
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_lines = []
        removed_count = 0
        for line in lines:
            should_remove = False
            for pattern in patterns_to_remove:
                if re.search(pattern, line):
                    should_remove = True
                    break
            
            if not should_remove:
                new_lines.append(line)
            else:
                removed_count += 1
        
        if removed_count > 0:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"✓ Removed {removed_count} noisy lines from {log_file}")

if __name__ == "__main__":
    clean_logs()
