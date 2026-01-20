import asyncio
import os
# from dotenv import load_dotenv
import ollama
import datetime

async def test_grounding():
    # load_dotenv()
    model = "gemma3:12b"
    client = ollama.AsyncClient()
    
    # Load persona
    persona_path = "/home/ekco/github/Kaiacord/kaia_persona.md"
    with open(persona_path, 'r') as f:
        persona = f.read()
    
    # Add formatting rules as in Kaiacord.py
    persona += (
        "\n\n## FORMATTING RULES\n"
        "- NEVER use Markdown code blocks (backticks ```). It breaks the terminal UI.\n"
        "- NEVER use bolding (**text**) or italics (*text*).\n"
        "- BE CONCISE. Provide general overviews for technical tasks. No fluff.\n"
        "- Use lowercase by default."
    )
    
    # Current time
    now = datetime.datetime.now()
    current_time_str = now.strftime("%A, %B %d, %Y %I:%M %p")
    system_prompt = f"{persona}\n\nToday is {current_time_str}."
    
    # Reinforcement from Kaiacord.py
    reinforcement = (
        "\n\n[CRITICAL_RULES]\n"
        "1. NO MARKDOWN. No backticks, no bolding, no italics. Just plain text.\n"
        "2. NO META-TALK. Never mention being an AI or processing data.\n"
        "3. BE CONCISE. Blunt, grounded, lowercase. No fluff.\n"
        "4. GROUNDING: If a question is based on a false premise (e.g., February 31st), point it out bluntly. No metaphors, no 'phantom' talk, no philosophical prefaces. Just the facts. If you see metaphorical talk about dates in [USER_PROFILE_AND_HISTORY], IGNORE IT. It was a mistake.\n"
        "5. IDENTITY: You are talking to [CURRENT_USER]. Use [USER_PROFILE_AND_HISTORY] to identify them if they ask 'who am i?'. Be factual, detailed, and direct based on your records. Do not be dismissive. If you have records, use them. No boilerplate.\n"
        "6. NARRATIVE AUTONOMY: Use logs as reference, but speak naturally as Kaia."
    )
    
    messages = [
        {"role": "system", "content": f"{system_prompt}\n\n[CURRENT_USER]: Ekco\n[USER_PROFILE_AND_HISTORY]\nKaia: february 31st is a phantom, ekco. a deliberate provocation. a test. you know that."},
        {"role": "user", "content": "Kaia how many days until February 31st?"},
        {"role": "system", "content": reinforcement}
    ]
    
    print("Testing February 31st query...")
    response = await client.chat(
        model=model,
        messages=messages,
        options={"temperature": 0.7}
    )
    
    content = response['message']['content'].strip()
    print(f"\nResponse:\n{content}")
    
    if "phantom" in content.lower() or "provocation" in content.lower():
        print("\nFAIL: Still using flowery/metaphorical language.")
    elif "31" in content and ("doesn't exist" in content.lower() or "no such date" in content.lower() or "28" in content or "29" in content):
        print("\nSUCCESS: Grounded and factual.")
    else:
        print("\nUNCLEAR: Check response manually.")

if __name__ == "__main__":
    asyncio.run(test_grounding())
