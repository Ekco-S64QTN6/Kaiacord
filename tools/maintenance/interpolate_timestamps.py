import re
import datetime
from pathlib import Path

user_logs_dir = "knowledge_base/user_logs"

def parse_time_from_line(line):
    # Matches [YYYY-MM-DD HH:MM:SS] Prefix:
    match = re.match(r'^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (\w+):', line)
    if match:
        dt = datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        speaker = match.group(2)
        return dt, speaker
    return None, None

for user_dir in Path(user_logs_dir).iterdir():
    if not user_dir.is_dir():
        continue
        
    username = user_dir.name.split('_')[0]
    
    # Process files sequentially so we could theoretically carry over time,
    # but let's just do it file by file.
    for log_file in sorted(user_dir.glob("interactions_202603*.md")):
        date_match = re.search(r'interactions_(\d{4})(\d{2})(\d{2})\.md', log_file.name)
        if not date_match:
            continue
            
        year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
        file_dt = datetime.datetime(year, month, day, 12, 0, 0) # default noon
        
        with open(log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
            
        lines = log_content.split('\n')
        
        # Determine anchors
        anchors = [] # list of (line_idx, dt)
        
        for i, line in enumerate(lines):
            dt, _ = parse_time_from_line(line)
            if dt:
                anchors.append((i, dt))
                
        # If no anchors, generate a fake anchor at the start
        if not anchors:
            # Maybe use os.path.getmtime?
            import os
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(log_file))
            # Just create a fake anchor at the end of the file based on mtime or just noon
            file_dt = datetime.datetime(year, month, day, 12, 0, 0)
        
        # We will parse the conversation into blocks
        blocks = [] 
        # block = {'start_idx', 'end_idx', 'speaker', 'text', 'dt': None}
        i = 0
        in_header = False
        
        new_lines = []
        
        # We'll just do a simple pass:
        # Keep track of last known time.
        # If we see a timestamp, update last known time.
        # If we see an un-timestamped "User:" or "Kaia:", use (last_known_time + 1 min), update last known time.
        # But wait, what if there's an anchor later? We don't want to overshoot.
        # A simpler way: forward fill from 12:00:00 for the file if no anchors.
        # If there are anchors, any unknown before the first anchor is (anchor - N mins).
        # Any unknown after an anchor is (anchor + 1 min).
        
        # Parse into turns
        turns = []
        while i < len(lines):
            line = lines[i]
            if line == "---":
                in_header = not in_header
                turns.append({'type': 'raw', 'lines': [line]})
                i += 1
                continue
            if in_header:
                turns.append({'type': 'raw', 'lines': [line]})
                i += 1
                continue
                
            # Is it a turn?
            dt, speaker = parse_time_from_line(line)
            if dt:
                # gather rest of turn
                buffer = [line]
                j = i + 1
                while j < len(lines) and not re.match(r'^(User|Kaia|\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]):', lines[j]) and not lines[j].startswith("---"):
                    buffer.append(lines[j])
                    j += 1
                turns.append({'type': 'turn', 'dt': dt, 'speaker': speaker, 'lines': buffer, 'original': True})
                i = j
                continue
                
            speaker_match = re.match(r'^(User|Kaia):\s*(.*)', line)
            if speaker_match:
                speaker_raw = speaker_match.group(1)
                actual_speaker = username if speaker_raw == "User" else "Kaia"
                buffer = [line]
                j = i + 1
                while j < len(lines) and not re.match(r'^(User|Kaia|\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]):', lines[j]) and not lines[j].startswith("---"):
                    buffer.append(lines[j])
                    j += 1
                turns.append({'type': 'turn', 'dt': None, 'speaker': actual_speaker, 'lines': buffer, 'original': False})
                i = j
                continue
                
            # raw text
            turns.append({'type': 'raw', 'lines': [line]})
            i += 1
            
        # Now interpolate dates for turns where dt is None
        # Find all turn indices
        turn_indices = [idx for idx, t in enumerate(turns) if t['type'] == 'turn']
        
        # If there are no anchors at all, set the first turn to 12:00:00
        has_anchor = any(t['dt'] is not None for t in turns if t['type'] == 'turn')
        if not has_anchor and turn_indices:
            turns[turn_indices[0]]['dt'] = datetime.datetime(year, month, day, 12, 0, 0)
            
        for idx in range(len(turns)):
            if turns[idx]['type'] == 'turn' and turns[idx]['dt'] is None:
                # Find nearest previous anchor
                prev_dt = None
                for p in range(idx - 1, -1, -1):
                    if turns[p]['type'] == 'turn' and turns[p]['dt'] is not None:
                        prev_dt = turns[p]['dt']
                        break
                
                # Find nearest next anchor
                next_dt = None
                for n in range(idx + 1, len(turns)):
                    if turns[n]['type'] == 'turn' and turns[n]['dt'] is not None:
                        next_dt = turns[n]['dt']
                        break
                        
                if prev_dt:
                    turns[idx]['dt'] = prev_dt + datetime.timedelta(minutes=1)
                elif next_dt:
                    # count how many missing between here and next
                    count = 0
                    for n in range(idx, len(turns)):
                        if turns[n]['type'] == 'turn':
                            if turns[n]['dt'] is not None:
                                break
                            count += 1
                    turns[idx]['dt'] = next_dt - datetime.timedelta(minutes=count)
                else:
                    # Should not reach here because we seeded the first one
                    turns[idx]['dt'] = datetime.datetime(year, month, day, 12, 0, 0)
                    
        # Now rewrite
        for idx in range(len(turns)):
            if turns[idx]['type'] == 'turn' and not turns[idx]['original']:
                dt = turns[idx]['dt']
                speaker = turns[idx]['speaker']
                
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                
                first_line = turns[idx]['lines'][0]
                speaker_match = re.match(r'^(User|Kaia):\s*(.*)', first_line)
                
                if speaker_match:
                    text = speaker_match.group(2)
                    if text:
                        turns[idx]['lines'][0] = f"[{dt_str}] {speaker}: {text}"
                    else:
                        turns[idx]['lines'][0] = f"[{dt_str}] {speaker}:"
                        
        # Reconstruct content
        final_lines = []
        for t in turns:
            final_lines.extend(t['lines'])
            
        new_content = '\n'.join(final_lines)
        if new_content != log_content:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Interpolated timestamps in {log_file}")
            
print("Interpolation Done.")
