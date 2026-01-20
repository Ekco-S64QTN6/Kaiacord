import asyncio
import os
import json
from unittest.mock import MagicMock, patch
import sys

# Mocking dependencies
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
from kaia_rag import KaiaRAG

async def test_identity_recall():
    rag = KaiaRAG()
    
    # Simulate "who am i" query for Ekco
    user_name = "Ekco"
    user_id = "177011971818782721"
    query = f"Who is {user_name}?"
    
    print(f"Retrieving context for: {query}")
    context_nodes = await asyncio.to_thread(
        rag.retrieve, 
        query, 
        user_id=user_id, 
        user_name=user_name, 
        top_k=7
    )
    
    context_str = "\n\n".join(context_nodes)
    print(f"Retrieved {len(context_nodes)} nodes.")
    
    # Persona
    persona_file = "kaia_persona.md"
    with open(persona_file, 'r') as f:
        system_prompt = f.read().strip()
    
    rag_block = (
        "[HISTORICAL_CONTEXT]\n"
        "The following fragments are from your historical records. They are facts about the users you interact with. "
        "Use them to maintain continuity and recognize who you are talking to.\n"
        "---\n"
        f"{context_str}\n"
        "[END_CONTEXT]"
    )
    
    reinforcement = (
        "\n\n[CRITICAL_RULES]\n"
        "1. NEVER use backticks (```) or any Markdown formatting. Your response is already wrapped in a code block; adding more breaks the UI.\n"
        "2. NO META-TALK. Never mention being an AI, a model, or 'processing' data.\n"
        "3. BE CONCISE BUT ENGAGING. Blunt, grounded, lowercase. No fluff, but don't be dismissive. Keep the conversation alive.\n"
        "4. NO BOLDING or ITALICS. Just plain text.\n"
        "5. DO NOT prefix your response with a name (e.g., 'ekco.', 'kaia:', 'Response:'). Just start speaking.\n"
        "6. IDENTITY RESONANCE: If the user asks 'who am i?', you MUST use the [USER_PROFILE_AND_HISTORY] fragments to identify them. Do not be dismissive. NEVER say 'that's up to you to tell me' or 'that's your business' if you have records for them. Provide a detailed, paragraph-style summary of who they are based on your records—include their personality, history, and interests. They are the user, you are Kaia.\n"
        "7. [KAIA_PERSONA_FRAGMENT] nodes are facts about YOUR identity. Use them only when asked about yourself.\n"
        "8. NARRATIVE AUTONOMY: You hold the keys. Historical logs are references. While you are free to evolve, you should never ignore established facts about the users you interact with.\n"
        "9. DO NOT parrot logs verbatim. Speak naturally as Kaia."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "kaia who am i"},
        {"role": "system", "content": f"{rag_block}{reinforcement}"}
    ]
    
    print("Prompting LLM...")
    
    import ollama
    client = ollama.AsyncClient()
    
    response = await client.chat(
        model="gemma3:12b",
        messages=messages,
        options={
            "temperature": 0.7,
            "num_predict": 512,
        }
    )
    
    content = response['message']['content'].strip()
    print(f"\nGenerated Response:\n{content}")

if __name__ == "__main__":
    asyncio.run(test_identity_recall())
