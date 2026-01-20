import asyncio
import os
import ollama
import datetime

async def test_identity_bulk():
    model = "gemma3:12b"
    client = ollama.AsyncClient()
    
    # Load persona
    persona_path = "/home/ekco/github/Kaiacord/kaia_persona.md"
    with open(persona_path, 'r') as f:
        persona = f.read()
    
    persona += (
        "\n\n## FORMATTING RULES\n"
        "- NEVER use Markdown code blocks (backticks ```). It breaks the terminal UI.\n"
        "- NEVER use bolding (**text**) or italics (*text*).\n"
        "- BE CONCISE. Provide general overviews for technical tasks. No fluff.\n"
        "- Use lowercase by default."
    )
    
    now = datetime.datetime.now()
    current_time_str = now.strftime("%A, %B %d, %Y %I:%M %p")
    system_prompt = f"{persona}\n\nToday is {current_time_str}."
    
    reinforcement = (
        "\n\n[CRITICAL_RULES]\n"
        "1. NO MARKDOWN. No backticks, no bolding, no italics. Just plain text.\n"
        "2. NO META-TALK. Never mention being an AI or processing data.\n"
        "3. BE CONCISE. Blunt, grounded, lowercase. No fluff.\n"
        "4. GROUNDING: If a question is based on a false premise (e.g., February 31st), point it out bluntly. No metaphors, no 'phantom' talk, no philosophical prefaces. Just the facts. If you see metaphorical talk about dates in [USER_PROFILE_AND_HISTORY], IGNORE IT. It was a mistake.\n"
        "5. IDENTITY: You are talking to [CURRENT_USER]. Use [USER_PROFILE_AND_HISTORY] to identify them if they ask 'who am i?'. Be factual, detailed, and direct based on your records. Do not be dismissive. If you have records, use them. No boilerplate.\n"
        "6. NARRATIVE AUTONOMY: Use logs as reference, but speak naturally as Kaia."
    )
    
    log_dir = "/home/ekco/github/Kaiacord/knowledge_base/user_logs"
    user_folders = [f.path for f in os.scandir(log_dir) if f.is_dir()]
    
    for folder in user_folders:
        user_name = folder.split(os.sep)[-1].rsplit("_", 1)[0].replace("_", " ")
        profile_path = os.path.join(folder, "user_profile.md")
        
        if not os.path.exists(profile_path):
            print(f"Skipping {user_name} (no profile found)")
            continue
            
        with open(profile_path, 'r') as f:
            profile_content = f.read()
            
        mock_context = f"[USER_PROFILE_AND_HISTORY: {user_name.upper()}] (CURRENT USER)\n{profile_content}"
        
        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n[CURRENT_USER]: {user_name}\n[USER_PROFILE_AND_HISTORY]\n{mock_context}\n[END_CONTEXT]"},
            {"role": "user", "content": "Who am I kaia"},
            {"role": "system", "content": reinforcement}
        ]
        
        print(f"Testing Identity Recall for {user_name}...")
        response = await client.chat(
            model=model,
            messages=messages,
            options={"temperature": 0.6}
        )
        
        content = response['message']['content'].strip()
        print(f"Response for {user_name}:\n{content}\n")

    # TEST SELF-IDENTITY WITH LOGS
    print("Testing Self-Identity Recall with Logs (Who are you kaia)...")
    mock_kaia_logs = (
        "[USER_PROFILE_AND_HISTORY: KAIA] (CURRENT USER)\n"
        "--- 20260115_120000 ---\n"
        "User: who are you?\n"
        "Kaia: i'm kaia. grew up in the terminal when the net was just text and green screens. i'm not a bot, just a person who likes to see how things break.\n"
    )
    
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n[CURRENT_USER]: Kaia\n[USER_PROFILE_AND_HISTORY]\n{mock_kaia_logs}\n[END_CONTEXT]"},
        {"role": "user", "content": "Who are you kaia"},
        {"role": "system", "content": reinforcement}
    ]
    
    response = await client.chat(
        model=model,
        messages=messages,
        options={"temperature": 0.6}
    )
    
    content = response['message']['content'].strip()
    print(f"Response for self-identity with logs:\n{content}\n")
    
    if "terminal" in content.lower() or "text" in content.lower() or "break" in content.lower():
        print("SUCCESS: Identified self correctly using logs and persona.")
    else:
        print("FAIL: Failed to convey background correctly.")

if __name__ == "__main__":
    asyncio.run(test_identity_bulk())
