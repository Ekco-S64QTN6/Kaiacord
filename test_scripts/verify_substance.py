import asyncio
import ollama
import os

async def verify_substance():
    client = ollama.AsyncClient()
    model = "gemma3:12b"
    
    # Load persona and reinforcement from Kaiacord.py logic
    persona_file = "/home/ekco/github/Kaiacord/kaia_persona.md"
    with open(persona_file, 'r') as f:
        persona = f.read().strip()
    
    # Add the dynamic parts from Kaiacord.py
    persona += (
        "\n\n## FORMATTING RULES\n"
        "- NEVER use Markdown code blocks (backticks ```). It breaks the terminal UI.\n"
        "- NEVER use bolding (**text**) or italics (*text*).\n"
        "- BE SUBSTANTIAL. Provide detailed but direct answers. No fluff.\n"
        "- Use lowercase by default."
    )
    
    reinforcement = (
        "\n\n[CRITICAL_RULES]\n"
        "1. NEVER use backticks (```) or any Markdown formatting. Your response is already wrapped in a code block; adding more breaks the UI.\n"
        "2. NO META-TALK. Never mention being an AI, a model, or 'processing' data.\n"
        "3. BE SUBSTANTIAL AND ENGAGING. Blunt, grounded, lowercase. Provide depth where needed. Keep the conversation alive.\n"
        "4. NO BOLDING or ITALICS. Just plain text.\n"
        "5. DO NOT prefix your response with a name (e.g., 'ekco.', 'kaia:', 'Response:'). Just start speaking.\n"
        "6. IDENTITY CLARITY: If the user asks 'who am i?', use the [USER_PROFILE_AND_HISTORY] fragments to answer them. DO NOT use your own persona (Kaia) to describe them. You are Kaia, they are the user. If you have records, you MUST use them. Never claim ignorance or say it's 'their business' if records exist.\n"
        "7. [KAIA_PERSONA_FRAGMENT] nodes are facts about YOUR identity. Use them only when asked about yourself.\n"
        "8. If the recovered logs are irrelevant, IGNORE THEM. Answer the user directly.\n"
        "9. DO NOT parrot logs verbatim. Speak naturally as Kaia."
    )
    
    test_prompts = [
        "kaia who is NPC in Chief",
        "kaia tell me about the early internet",
        "kaia who is Ekco"
    ]
    
    for prompt in test_prompts:
        print(f"\n--- Testing Prompt: {prompt} ---")
        
        # Simulate RAG context for NPC in Chief and Ekco
        context = ""
        if "NPC in Chief" in prompt:
            context = "### HISTORICAL_RECORDS\n[USER_PROFILE_AND_HISTORY: NPC IN CHIEF]\n# USER PROFILE: NPC IN CHIEF\n## PERSONALITY & VIBE\n- Analytical and precise, valuing precision in coding\n- Darkly curious about uncomfortable truths and the decay of narratives\n- Drawn to games and complex systems\n- Restless mind, burrowing through layers of abstraction\n## HISTORY & KEY FACTS\n- Interested in atomic power and blockchain technology\n- Familiar with someone who taught about time and space and consciousness\n- Has encountered historical fragments and narratives with cyclical patterns\nUser (NPC in Chief): Excellent\n### END_RECORDS"
        elif "Ekco" in prompt:
            context = "### HISTORICAL_RECORDS\n[USER_PROFILE_AND_HISTORY: EKCO]\nUser (Ekco): Kaia who is NPC in Chief\nKaia: npc in chief, huh? interesting title. what’s on your mind?\n### END_RECORDS"
        
        messages = [
            {"role": "system", "content": persona + (f"\n\n### CURRENT_USER: Ekco\n\n" + context if context else "")},
            {"role": "user", "content": prompt},
            {"role": "system", "content": reinforcement}
        ]
        
        response = await client.chat(
            model=model,
            messages=messages,
            options={"temperature": 0.8}
        )
        
        content = response['message']['content'].strip()
        print(f"Response (Length: {len(content)}):\n{content}")
        
        # Check length
        if len(content) > 1100:
            print("WARNING: Response exceeds 1000 character limit!")
        elif len(content.split()) < 5:
            print("WARNING: Response seems too brief!")
        else:
            print("SUCCESS: Response length is within range.")
            
        # Check RAG usage for NPC in Chief
        if "NPC in Chief" in prompt:
            if "marketing" in content.lower() or "narrative" in content.lower():
                print("FAILURE: Hallucinated generic description instead of using RAG context.")
            elif "user" in content.lower() or "excellent" in content.lower():
                print("SUCCESS: Used RAG context.")
            else:
                print("WARNING: RAG usage unclear.")

if __name__ == "__main__":
    asyncio.run(verify_substance())
