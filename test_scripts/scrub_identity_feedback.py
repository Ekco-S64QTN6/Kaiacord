import os
import glob
import re

log_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs"

# Phrases that indicate the "privacy-focused" bad responses
BAD_PHRASES = [
    r"i'm not going to ask for your name or your backstory",
    r"that's your business",
    r"who are \*you\?\* that’s up to you to tell me",
    r"who are \*you\?\* that's up to you to tell me",
    r"who am i\? that's up to you to tell me"
]

def scrub_logs():
    user_dirs = [d for d in os.scandir(log_dir) if d.is_dir()]
    
    for d in user_dirs:
        print(f"Checking logs in {d.path}...")
        log_files = glob.glob(os.path.join(d.path, "interactions_*.txt"))
        
        for log_file in log_files:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split by interaction separator
            interactions = content.split("--- 202") # Use date prefix as anchor
            
            new_interactions = []
            scrubbed_count = 0
            
            # The first element might be empty or header
            if interactions[0].strip():
                new_interactions.append(interactions[0])
            
            for i in range(1, len(interactions)):
                interaction_text = "--- 202" + interactions[i]
                
                is_bad = False
                for phrase in BAD_PHRASES:
                    if re.search(phrase, interaction_text, re.IGNORECASE):
                        is_bad = True
                        break
                
                if is_bad:
                    scrubbed_count += 1
                    print(f"  [SCRUBBED] Bad interaction found in {os.path.basename(log_file)}")
                else:
                    new_interactions.append(interaction_text)
            
            if scrubbed_count > 0:
                new_content = "".join(new_interactions)
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"  ✓ Scrubbed {scrubbed_count} interactions from {os.path.basename(log_file)}")

if __name__ == "__main__":
    scrub_logs()
