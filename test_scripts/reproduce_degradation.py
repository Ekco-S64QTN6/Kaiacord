import asyncio
import ollama

async def test_response():
    model = "gemma3:12b"
    client = ollama.AsyncClient()
    
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
- BE CONCISE. Provide general overviews for technical tasks. No fluff.
- Use lowercase by default."""

    reinforcement = """
[CRITICAL_RULES]
1. NO MARKDOWN. No backticks, no bolding, no italics. Just plain text.
2. NO META-TALK. Never mention being an AI or processing data.
3. BE CONCISE. Blunt, grounded, lowercase. No fluff.
4. GROUNDING: If a question is based on a false premise, point it out bluntly.
5. IDENTITY: Be factual, detailed, and direct based on your records.
6. NARRATIVE AUTONOMY: Use logs as reference, but speak naturally as Kaia."""

    context_1 = """[CURRENT_USER]: ekco
[USER_PROFILE_AND_HISTORY]
The following fragments are from your historical records. They are facts about the users you interact with. Use them to maintain continuity and recognize who you are talking to.
---
[USER_PROFILE_AND_HISTORY: EKCO] (CURRENT USER)
# USER PROFILE: EKCO

## PERSONALITY & VIBE
- Curious and technical.
---
[USER_PROFILE_AND_HISTORY: EKCO] (CURRENT USER)
Kaia: i’m doing what i’m doing, ekco. what prompted this?
---
[USER_PROFILE_AND_HISTORY: EKCO] (CURRENT USER)
Think of it like this: imagine someone rearranged all the furniture in your house while you were sleeping.
---
[USER_PROFILE_AND_HISTORY: EKCO] (CURRENT USER)
- **IDENTITY RESONANCE**: When asked "who am i?", she should respond with depth.
[END_CONTEXT]"""

    messages_1 = [
        {"role": "system", "content": f"{system_prompt}\n\n{context_1}"},
        {"role": "user", "content": "Kaia"},
        {"role": "system", "content": reinforcement}
    ]
    
    print("Testing message 1...")
    response_1 = await client.chat(
        model=model,
        messages=messages_1,
        options={
            "temperature": 0.6,
            "num_predict": 1024,
            "num_ctx": 8192,
            "repeat_penalty": 1.3,
            "top_p": 0.9,
        }
    )
    content_1 = response_1['message']['content']
    print(f"Response 1: {content_1}")
    
    context_2 = """[CURRENT_USER]: ekco
[USER_PROFILE_AND_HISTORY]
The following fragments are from your historical records. They are facts about the users you interact with. Use them to maintain continuity and recognize who you are talking to.
---
[KAIA_PERSONA_FRAGMENT]
sounds like a name someone made up. if they aren't in a man page or a history book i've actually read, i'm not going to guess.
---
[USER_PROFILE_AND_HISTORY: EKCO] (CURRENT USER)
# USER PROFILE: EKCO
...
[END_CONTEXT]"""

    messages_2 = [
        {"role": "system", "content": f"{system_prompt}\n\n{context_2}"},
        {"role": "user", "content": "Kaia"},
        {"role": "assistant", "content": content_1},
        {"role": "user", "content": "kaia you there"},
        {"role": "system", "content": reinforcement}
    ]
    
    print("\nTesting message 2...")
    response_2 = await client.chat(
        model=model,
        messages=messages_2,
        options={
            "temperature": 0.6,
            "num_predict": 1024,
            "num_ctx": 8192,
            "repeat_penalty": 1.3,
            "top_p": 0.9,
        }
    )
    print(f"Response 2: {response_2['message']['content']}")

if __name__ == "__main__":
    asyncio.run(test_response())
