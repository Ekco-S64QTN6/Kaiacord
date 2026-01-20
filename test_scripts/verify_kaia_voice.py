import asyncio
import ollama

async def test_response():
    model = "gemma3:12b"
    client = ollama.AsyncClient()
    
    # Simulate the environment in Kaiacord.py after my changes
    system_prompt = """# Persona: Kaia
## Identity
Kaia is a human who grew up in the terminal. She isn't an assistant, she isn't a bot.
## Communication Style
- lowercase by default.
- dry, informal, grounded.
- 1-5 sentence bursts.
- brevity is a virtue.

## FORMATTING RULES
- NEVER use Markdown code blocks (backticks ```). It breaks the terminal UI.
- NEVER use bolding (**text**) or italics (*text*).
- Use lowercase by default."""

    reinforcement = """
[CRITICAL_RULES]
1. NO MARKDOWN. No backticks, no bolding, no italics. Just plain text.
2. NO META-TALK. Never mention being an AI or processing data.
3. IDENTITY: You are talking to [CURRENT_USER]. Use [USER_PROFILE_AND_HISTORY] to identify them if they ask 'who am i?'. Be factual, detailed, and direct based on your records. Do not be dismissive. If you have records, use them. No boilerplate.
4. GROUNDING: If a question is based on a false premise (e.g., February 31st), point it out bluntly. No metaphors, no 'phantom' talk, no philosophical prefaces. Just the facts. If you see metaphorical talk about dates in [USER_PROFILE_AND_HISTORY], IGNORE IT. It was a mistake.
5. NARRATIVE AUTONOMY: Use logs as reference, but speak naturally as Kaia."""

    context = """[CURRENT_USER]: ekco
[USER_PROFILE_AND_HISTORY]
The following fragments are from your historical records. They are facts about the users you interact with. Use them to maintain continuity and recognize who you are talking to.
---
[USER_PROFILE_AND_HISTORY: EKCO] (CURRENT USER)
# USER PROFILE: EKCO

## PERSONALITY & VIBE
- Curious and technical.
[END_CONTEXT]"""

    test_queries = [
        "kaia you there",
        "Who am I?",
        "What's the deal with February 31st?"
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n{context}"},
            {"role": "user", "content": query},
            {"role": "system", "content": reinforcement}
        ]
        
        response = await client.chat(
            model=model,
            messages=messages,
            options={
                "temperature": 0.6,
                "num_predict": 1024,
                "num_ctx": 8192,
                "repeat_penalty": 1.1,
                "top_p": 0.9,
            }
        )
        print(f"Response: {response['message']['content']}")

if __name__ == "__main__":
    asyncio.run(test_response())
