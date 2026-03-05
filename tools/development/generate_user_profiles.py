import os
import glob
import asyncio
import ollama
from datetime import datetime

# Configuration
LOG_DIR = "knowledge_base/user_logs"
MODEL = "gemma3:12b"
PERSONA_PATH = "knowledge_base/kaia_persona.md"

async def generate_profile(user_folder):
    """Generate a first-person inner monologue 'cheat sheet' for a user."""
    # Handle folder name correctly (Name_ID)
    folder_name = os.path.basename(user_folder)
    if "_" in folder_name:
        user_name = folder_name.rsplit("_", 1)[0].replace("_", " ")
    else:
        user_name = folder_name
        
    log_files = sorted(glob.glob(os.path.join(user_folder, "interactions_*.txt")))
    
    if not log_files:
        print(f"  No logs for {user_name}, skipping.")
        return
    
    print(f"Generating cheat sheet for {user_name}...")
    
    # Load recent history (last 24k chars to stay within context but get enough vibe)
    all_content = ""
    for log_file in log_files:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            all_content += f.read() + "\n"
            
    if not all_content.strip():
        return

    # Load persona
    with open(PERSONA_PATH, "r") as f:
        persona_content = f.read()

    prompt = f"""
{persona_content}

[INTERNAL DATA: USER LOGS FOR {user_name}]
{all_content[-24000:]}

[TASK: INTERNAL CHEAT SHEET]
You are Kaia. Write your internal, first-person "cheat sheet" for {user_name} based on the logs above.
This is for your eyes only. It should help you understand:
1. **The Identity**: Who is this person in your world? (A trusted collaborator, a technical equal, a curious stranger, or a repetitive nuisance?)
2. **The Vibe & Relationship**: How do they treat you, and how do you feel about them? Are they respectful of your dry tone, or do they push for corporate fluff?
3. **Key Intel**: What projects, technical interests, or personal milestones did they mention that you *must* remember to stay grounded?
4. **Significant History**: Summarize the most important architectural discussions or personal turning points from past conversations.
5. **Inner Monologue**: What is your honest, unfiltered take on them?
6. **Actionable Strategy**: How should you handle them moving forward? (e.g., "be blunt but helpful", "keep them at arm's length", "nerd out on RAG with them").

STRICT RULES:
- lowercase only.
- blunt, tired, grounded (your signature voice).
- no corporate fluff or "personality metrics."
- do NOT mention "logs," "data," or "extraction."
- speak about {user_name} directly in the first person ("i think...", "they said...").

OUTPUT ONLY your inner monologue. No titles, no headings, no lists. Just raw, honest thoughts.
"""

    try:
        response = await ollama.AsyncClient().chat(
            model=MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            options={
                "temperature": 0.8
            }
        )
        
        profile_content = response['message']['content'].strip()
        profile_path = os.path.join(user_folder, "user_profile.md")
        
        # Save the profile
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(f"# INTERNAL MEMORY: {user_name}\n\n{profile_content}")
            
        print(f"✓ Cheat sheet generated: {profile_path}")
        
    except Exception as e:
        print(f"Error generating cheat sheet for {user_name}: {e}")

async def main():
    import sys
    if not os.path.exists(LOG_DIR):
        print(f"Log directory {LOG_DIR} not found")
        return

    user_folders = [f.path for f in os.scandir(LOG_DIR) if f.is_dir()]
    
    if len(sys.argv) > 1:
        target = sys.argv[1]
        user_folders = [f for f in user_folders if target.lower() in f.lower()]
        
    for folder in user_folders:
        await generate_profile(folder)

if __name__ == "__main__":
    asyncio.run(main())
