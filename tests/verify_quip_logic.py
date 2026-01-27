import asyncio
import random
from datetime import datetime

# Mocking the environment for verification
class MockRAG:
    async def retrieve(self, query, top_k=3):
        if query == "recent user interaction":
            return ["User1: I love Okta.", "User2: AeroDyn is great.", "User3: Why is the sky blue?"]
        if query == "[IDLE_QUIP]":
            return ["another okta patch? really, still?", "okta patches, huh? still chasing shadows, aren't we?"]
        if "news brief" in query:
            return ["Okta releases new patch.", "AeroDyn breach details."]
        return []

async def verify_quip_logic():
    rag = MockRAG()
    
    for i in range(5):
        print(f"\n--- Run {i+1} ---")
        # Logic from Kaiacord.py
        context_nodes = await rag.retrieve("recent user interaction", top_k=3)
        
        news_nodes = []
        news_chance = random.random()
        if news_chance < 0.20:
            print("News chance hit!")
            news_nodes = await rag.retrieve(f"news brief {datetime.now().strftime('%Y-%m-%d')}", top_k=2)
        else:
            print("News chance missed.")
            
        recent_quips = await rag.retrieve("[IDLE_QUIP]", top_k=5)
        
        context_str = ""
        if context_nodes:
            context_str = "\n\n[LOG_CONTEXT]\n" + "\n---\n".join(context_nodes)
        
        if news_nodes:
            context_str += "\n\n[NEWS_CONTEXT]\n" + "\n---\n".join(news_nodes)
        
        if recent_quips:
            context_str += "\n\n[RECENT_QUIPS_TO_AVOID_REPEATING]\n" + "\n---\n".join(recent_quips)
            
        print("Prompt Context:")
        print(context_str)
        
        messages = [
            {"role": "system", "content": "Persona" + context_str},
            {"role": "user", "content": "Based on the provided log context (if any), generate a short, funny, and slightly mocking question or quip. "
                "Make it a single, sharp sentence. Be blunt and grounded. "
                "If there's log context, make fun of what was said or the user's logic. "
                "If there's news context, you can reference it, but don't obsess over Okta or AeroDyn breaches unless they are actually in the context. "
                "If no context, just ask a dry, cynical question about tech or life. "
                "CRITICAL: Do not repeat or rephrase anything in the [RECENT_QUIPS_TO_AVOID_REPEATING] section. "
                "No fluff. No intro. Just the quip."}
        ]
        print("User Message Content:")
        print(messages[1]['content'])

if __name__ == "__main__":
    asyncio.run(verify_quip_logic())
