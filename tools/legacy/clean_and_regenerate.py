#!/usr/bin/env python3
"""
Clean user logs of hallucinations and regenerate user profiles.
"""
import os
import sys
import re
import glob
import asyncio
import ollama
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Hallucinated patterns to remove
HALLUCINATED_PATTERNS = [
    r"i remember you working on the data pipeline",
    r"back in '21.*?(?:you were|memory leak|server farm)",
    r"you were chasing a memory leak for days",
    r"almost burned out the whole server farm",
    r"good work.*?you're good at digging",
    r"the apartment’s quiet",
    r"the neon's flickering again",
    r"it’s always something with you",
    r"you know the user listing thing",
    r"it’s clipped",
    r"like someone’s deliberately hiding parts",
    r"what are you working on\?",
    r"yeah\. what's on your mind\?",
    r"coffee's cold",
    r"not much to say about that",
    r"anything else on your mind",
    r"what's your take on that",
    r"seen anything interesting on your end",
    r"got any thoughts about this",
    r"anything specific you're curious about",
    r"i'm here\. what's on your mind",
    r"listening\. go ahead",
]

MODEL_NAME = "gemma3:12b"  # Use the active model

async def clean_logs(user_log_dir):
    """Clean interaction logs in the directory."""
    log_files = glob.glob(os.path.join(user_log_dir, "interactions_*.txt"))
    cleaned_count = 0
    
    full_history = ""

    for log_file in log_files:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            should_remove = False
            for pattern in HALLUCINATED_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    should_remove = True
                    break
            
            if should_remove:
                cleaned_count += 1
                # Replace with empty line to preserve structure if needed, or just skip
                # Skipping is better for RAG context
                continue
            
            cleaned_lines.append(line)
        
        new_content = '\n'.join(cleaned_lines)
        if new_content != original_content:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"    Cleaned {log_file}")
        
        full_history += new_content + "\n"
        
    return cleaned_count, full_history

async def regenerate_profile(user_name, user_id, history, user_log_dir):
    """Regenerate user profile using LLM."""
    print(f"    Regenerating profile for {user_name}...")
    
    prompt = f"""
    Analyze the following interaction history for user '{user_name}' (ID: {user_id}) and generate a comprehensive user profile.
    
    HISTORY:
    {history[-10000:]}  # Limit context to last 10k chars to avoid overflow
    
    Generate a Markdown profile with the following sections:
    
    USER PROFILE: {user_name.upper()}
    
    QUICK REFERENCE
    * User Name: {user_name}
    * Total Interactions: [Estimate based on history]
    * Last Seen: [Extract date from last log]
    * Primary Interests: [List 3-5 key interests]
    * Communication Style: [Brief description]
    
    HOW TO INTERACT WITH THEM
    * [Bullet points on how Kaia should adapt]
    
    SHARED HISTORY & CONTEXT
    * [Key shared memories or projects]
    
    THEIR INTERESTS & EXPERTISE
    * [Detailed list of interests]
    
    CONVERSATION STYLE NOTES
    * [Observations on tone, length, vocabulary]
    
    RELATIONSHIP STATUS WITH KAIA
    * [Current trust level and dynamic]
    
    POTENTIAL TRIGGERS & SENSITIVITIES
    * [What to avoid]
    
    GROWTH OPPORTUNITIES
    * [How to deepen the connection]
    
    IMPORTANT: Be objective, psychological, and analytical. Do NOT hallucinate details not present in the history. If history is sparse, note that.
    """
    
    try:
        client = ollama.AsyncClient()
        response = await client.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}]
        )
        
        profile_content = response['message']['content']
        
        profile_path = os.path.join(user_log_dir, "user_profile.md")
        with open(profile_path, 'w', encoding='utf-8') as f:
            f.write(profile_content)
            
        print(f"    ✅ Profile saved to {profile_path}")
        return True
    except Exception as e:
        print(f"    ❌ Error generating profile: {e}")
        return False

async def main():
    print("🚀 STARTING LOG CLEANUP AND PROFILE REGENERATION")
    print("="*60)
    
    logs_root = "knowledge_base/user_logs"
    if not os.path.exists(logs_root):
        print(f"❌ Logs directory not found: {logs_root}")
        return

    users = [d for d in os.listdir(logs_root) if os.path.isdir(os.path.join(logs_root, d))]
    
    for user_dir in users:
        print(f"\nProcessing user: {user_dir}")
        user_log_dir = os.path.join(logs_root, user_dir)
        
        # Parse user info from dir name (Name_ID)
        try:
            user_name, user_id = user_dir.rsplit('_', 1)
        except ValueError:
            print(f"    ⚠️ Skipping invalid directory format: {user_dir}")
            continue
            
        # 1. Clean Logs
        cleaned, history = await clean_logs(user_log_dir)
        if cleaned > 0:
            print(f"    🧹 Removed {cleaned} hallucinated lines")
        else:
            print("    ✨ Logs appear clean")
            
        # 2. Regenerate Profile
        # Delete old profile first
        profile_path = os.path.join(user_log_dir, "user_profile.md")
        if os.path.exists(profile_path):
            os.remove(profile_path)
            print("    🗑️  Deleted old profile")
            
        if history.strip():
            await regenerate_profile(user_name, user_id, history, user_log_dir)
        else:
            print("    ⚠️  No history found, skipping profile generation")

    print("\n" + "="*60)
    print("✅ DONE! All logs cleaned and profiles regenerated.")

if __name__ == "__main__":
    asyncio.run(main())
