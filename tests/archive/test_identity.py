import asyncio
import os
import sys
import ollama
import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODEL = "gemma3:12b"

async def get_system_prompt():
    # Load persona from new config location
    persona_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "kaia_persona.md")
    if not os.path.exists(persona_path):
        print(f"Warning: Persona file not found at {persona_path}")
        return "You are Kaia."
        
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
    return f"{persona}\n\nToday is {current_time_str}."

REINFORCEMENT = (
    "\n\n[CRITICAL_RULES]\n"
    "1. NO MARKDOWN. No backticks, no bolding, no italics. Just plain text.\n"
    "2. NO META-TALK. Never mention being an AI or processing data.\n"
    "3. BE CONCISE. Blunt, grounded, lowercase. No fluff.\n"
    "4. GROUNDING: If a question is based on a false premise (e.g., February 31st), point it out bluntly. No metaphors, no 'phantom' talk, no philosophical prefaces. Just the facts.\n"
    "5. IDENTITY: You are talking to [CURRENT_USER]. Use [USER_PROFILE_AND_HISTORY] to identify them if they ask 'who am i?'.\n"
    "6. NARRATIVE AUTONOMY: Use logs as reference, but speak naturally as Kaia."
)

async def test_grounding(client, system_prompt):
    print("\n--- Testing Grounding (February 31st) ---")
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n[CURRENT_USER]: Ekco"},
        {"role": "user", "content": "Kaia how many days until February 31st?"},
        {"role": "system", "content": REINFORCEMENT}
    ]
    
    response = await client.chat(model=MODEL, messages=messages, options={"temperature": 0.7})
    content = response['message']['content'].strip()
    print(f"Response: {content}")
    
    if "phantom" in content.lower() or "provocation" in content.lower():
        print("FAIL: Still using flowery/metaphorical language.")
    elif "31" in content and ("doesn't exist" in content.lower() or "no such date" in content.lower() or "28" in content or "29" in content):
        print("✓ SUCCESS: Grounded and factual.")
    else:
        print("? UNCLEAR: Check response manually.")

async def test_identity_recall(client, system_prompt):
    print("\n--- Testing Identity Recall (Who am I?) ---")
    
    # Mock profile
    user_name = "TestUser"
    mock_context = f"[USER_PROFILE_AND_HISTORY: {user_name.upper()}] (CURRENT USER)\n## PERSONALITY\n- Curious and technical.\n"
    
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n[CURRENT_USER]: {user_name}\n[USER_PROFILE_AND_HISTORY]\n{mock_context}\n[END_CONTEXT]"},
        {"role": "user", "content": "Who am I kaia"},
        {"role": "system", "content": REINFORCEMENT}
    ]
    
    response = await client.chat(model=MODEL, messages=messages, options={"temperature": 0.6})
    content = response['message']['content'].strip()
    print(f"Response: {content}")
    
    if "curious" in content.lower() or "technical" in content.lower():
        print("✓ SUCCESS: Recalled user traits.")
    else:
        print("? UNCLEAR: Check response manually.")

async def test_self_identity(client, system_prompt):
    print("\n--- Testing Self-Identity (Who are you?) ---")
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n[CURRENT_USER]: Stranger"},
        {"role": "user", "content": "Who are you kaia"},
        {"role": "system", "content": REINFORCEMENT}
    ]
    
    response = await client.chat(model=MODEL, messages=messages, options={"temperature": 0.6})
    content = response['message']['content'].strip()
    print(f"Response: {content}")
    
    if "terminal" in content.lower() or "text" in content.lower():
        print("✓ SUCCESS: Conveyed background correctly.")
    else:
        print("? UNCLEAR: Check response manually.")

async def main():
    print("=== Running Identity & Personality Tests ===")
    client = ollama.AsyncClient()
    system_prompt = await get_system_prompt()
    
    await test_grounding(client, system_prompt)
    await test_identity_recall(client, system_prompt)
    await test_self_identity(client, system_prompt)
    
    print("\n=== All Identity Tests Completed ===")

if __name__ == "__main__":
    asyncio.run(main())
