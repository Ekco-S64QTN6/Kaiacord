import os
import re
import datetime
from pathlib import Path
from difflib import SequenceMatcher

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()

discord_file = "discord_logs.md"
user_logs_dir = "knowledge_base/user_logs"
current_date = datetime.date(2026, 3, 13)

# Parse discord logs
discord_entries = []
try:
    with open(discord_file, 'r', encoding='utf-8') as f:
        discord_lines = f.readlines()
        
    current_time_str = None
    current_speaker = None
    current_content = []
    
    date_tracker = current_date # Assume mostly today
    
    # We need to detect time wraps (e.g., [11:59 PM] -> [12:01 AM])
    # to increment date if we parse backwards, but discord logs are usually chronological.
    
    last_dt = None
    
    for line in discord_lines:
        match = re.search(r'^\[(\d{1,2}:\d{2} [AP]M)\] \*\*([^:]+):\*\*(.*)', line)
        if match:
            if current_speaker:
                discord_entries.append({
                    'time_str': current_time_str,
                    'speaker': current_speaker,
                    'content': '\n'.join(current_content).strip()
                })
            
            time_str = match.group(1)
            speaker = match.group(2).replace("APP Kaia", "Kaia").strip()
            content = match.group(3).strip()
            
            current_time_str = time_str
            current_speaker = speaker
            current_content = [content] if content else []
        else:
            if current_speaker:
                current_content.append(line.strip('\n'))
                
    if current_speaker:
        discord_entries.append({
            'time_str': current_time_str,
            'speaker': current_speaker,
            'content': '\n'.join(current_content).strip()
        })
except Exception as e:
    print(f"Error parsing discord logs: {e}")

print(f"Parsed {len(discord_entries)} Discord entries.")

# Now parse the user logs
# We will focus on files modified recently or just read all interactions_*.md
for user_dir in Path(user_logs_dir).iterdir():
    if not user_dir.is_dir():
        continue
        
    username = user_dir.name.split('_')[0]
    
    for log_file in user_dir.glob("interactions_202603*.md"):
        # We will extract date from filename
        date_match = re.search(r'interactions_(\d{4})(\d{2})(\d{2})\.md', log_file.name)
        if not date_match:
            continue
            
        year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        file_date_str = f"{year:04d}-{month:02d}-{day:02d}"
        
        with open(log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
            
        # Split into User/Kaia turns
        # We will split by lines starting with "User: " or "Kaia: " or "[YYYY-MM-DD HH:MM:SS]"
        
        if "User: " not in log_content and "Kaia: " not in log_content:
            continue
            
        print(f"Processing {log_file}...")
        
        # We need a robust parser for the existing log format
        lines = log_content.split('\n')
        
        new_lines = []
        i = 0
        in_header = False
        
        while i < len(lines):
            line = lines[i]
            
            if line == "---":
                in_header = not in_header
                new_lines.append(line)
                i += 1
                continue
                
            if in_header:
                new_lines.append(line)
                i += 1
                continue
                
            # Detect existing un-timestamped turns
            speaker_match = re.match(r'^(User|Kaia):\s*(.*)', line)
            
            if speaker_match:
                speaker_raw = speaker_match.group(1)
                text = speaker_match.group(2).strip()
                
                # Gather full text until next speaker
                buffer_text = [text] if text else []
                j = i + 1
                while j < len(lines):
                    if re.match(r'^(User|Kaia|\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]):', lines[j]) or lines[j].startswith("---"):
                        break
                    buffer_text.append(lines[j])
                    j += 1
                    
                full_text = '\n'.join(buffer_text).strip()
                
                # Try to find a match in discord logs
                best_match = None
                best_ratio = 0
                best_index = -1
                
                speaker_to_match = username if speaker_raw == "User" else "Kaia"
                
                for idx, entry in enumerate(discord_entries):
                    if entry['speaker'] == speaker_to_match:
                        # Clean up some common differences
                        clean_entry = re.sub(r'\[Thread \d+/\d+\]', '', entry['content']).strip()
                        ratio = similar(full_text[:200], clean_entry[:200]) # optimize slightly
                        if ratio > 0.8 and ratio > best_ratio:
                            best_ratio = ratio
                            best_match = entry
                            best_index = idx
                            
                if best_match:
                    # Parse time
                    time_dt = datetime.datetime.strptime(best_match['time_str'], "%I:%M %p")
                    timestamp_str = f"[{file_date_str} {time_dt.strftime('%H:%M:%S')}]"
                    actual_speaker = username if speaker_raw == "User" else "Kaia"
                    
                    # Formatting check: replace "User: " with "[timestamp] Username: "
                    if text:
                        new_lines.append(f"{timestamp_str} {actual_speaker}: {text}")
                    else:
                        new_lines.append(f"{timestamp_str} {actual_speaker}:")
                        
                    for bline in buffer_text[1:]:
                        new_lines.append(bline)
                        
                else:
                    # Guesstimate timestamp based on previous/next matches?
                    # For now just append as is or give a default timestamp
                    new_lines.append(line)
                    for bline in buffer_text[1:]:
                        new_lines.append(bline)
                
                i = j
            else:
                new_lines.append(line)
                i += 1
                
        # Write back changes if different
        new_content = '\n'.join(new_lines)
        if new_content != log_content:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated timestamps in {log_file.name}")

print("Done.")
