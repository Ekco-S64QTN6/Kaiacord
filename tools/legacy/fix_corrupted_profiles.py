import os
import re
from pathlib import Path

USER_LOGS_DIR = Path("/home/ekco/github/Kaiacord/knowledge_base/user_logs")

def fix_profile(user_dir):
    profile_path = user_dir / "user_profile.md"
    history_path = user_dir / "post_history.md"
    
    if not profile_path.exists():
        return

    print(f"Checking {user_dir.name}...")
    
    # Try to get correct metadata from history
    metadata = {
        'username': '?',
        'user_id': '?',
        'total_posts': '?',
        'join_date': '?',
        'rank': 'forum user'
    }
    
    if history_path.exists():
        content = history_path.read_text(encoding='utf-8', errors='replace')
        m_un = re.search(r'username: "([^"]+)"', content)
        m_uid = re.search(r'user_id: (\d+)', content)
        m_tp = re.search(r'total_posts: (\d+)', content)
        m_jd = re.search(r'join_date: "([^"]+)"', content)
        
        if m_un: metadata['username'] = m_un.group(1)
        if m_uid: metadata['user_id'] = m_uid.group(1)
        if m_tp: metadata['total_posts'] = m_tp.group(1)
        if m_jd: metadata['join_date'] = m_jd.group(1)

    # Read profile
    p_content = profile_path.read_text(encoding='utf-8', errors='replace')
    
    # Reconstruct the file
    # We want to restore the YAML summary and fix the narrative
    
    header = "---\n"
    header += f'summary: "Forum user from Project 1999 Off Topic."\n'
    
    # Extract keywords from old content if possible, or use default
    keywords = '[forum, Off Topic, Project 1999, "forum user"]'
    if 'keywords:' in p_content:
        m_kw = re.search(r'keywords: (\[.*?\])', p_content)
        if m_kw:
            keywords = m_kw.group(1)
    
    header += f'keywords: {keywords}\n'
    header += 'document_type: Narrative/Log\n'
    header += 'platform: vbulletin\n'
    header += "---\n\n"
    
    # Body
    title = f"# INTERNAL MEMORY: {metadata['username']} (Forum)"
    if f"# INTERNAL MEMORY:" in p_content:
        m_title = re.search(r'# INTERNAL MEMORY: (.*?) \(Forum\)', p_content)
        if m_title:
            title = f"# INTERNAL MEMORY: {m_title.group(1)} (Forum)"

    narrative = (
        f"a forum user with the rank of '{metadata['rank']}'. they've posted {metadata['total_posts']} times "
        f"since joining Norrath's digital extension in {metadata['join_date']}. "
    )
    
    # Keep the rest of the personality notes
    rest = "haven't formed a strong opinion yet — need to see more of their posts."
    if "# INTERNAL MEMORY:" in p_content:
        parts = p_content.split("# INTERNAL MEMORY:", 1)
        body_part = parts[1]
        # The body starts after the first newline of parts[1]
        if '\n' in body_part:
            body_part = body_part.split('\n', 1)[1]
        else:
            body_part = ""
            
        lines = body_part.split('\n')
        captured_lines = []
        for line in lines:
            # Skip any line that looks like our narrative pattern
            if "a forum user with the rank of" in line:
                continue
            # Skip redundant title lines left from previous failed cleanup runs
            if metadata['username'] in line and "(Forum)" in line:
                continue
            captured_lines.append(line)
        
        if captured_lines:
            rest = '\n'.join(captured_lines).strip()

    new_p_content = header + title + "\n\n" + narrative + "\n" + rest + "\n"
    
    profile_path.write_text(new_p_content, encoding='utf-8', errors='replace')
    print(f"  Fixed {user_dir.name}")

def main():
    for user_dir in USER_LOGS_DIR.iterdir():
        if user_dir.is_dir() and user_dir.name.startswith("forum_"):
            fix_profile(user_dir)

if __name__ == "__main__":
    main()
