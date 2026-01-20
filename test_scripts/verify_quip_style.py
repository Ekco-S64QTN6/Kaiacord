import asyncio
import os
import json
from unittest.mock import MagicMock, patch
import sys

# Mocking dependencies
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
from kaia_rag import KaiaRAG

# Mocking ollama
class MockOllama:
    async def chat(self, model, messages, options):
        # This will be patched in the test
        pass

async def test_quip_generation():
    rag = KaiaRAG()
    
    # Simulate RAG retrieval
    query = "Ekco"
    context_nodes = rag.retrieve(query, top_k=3)
    
    context_str = ""
    if context_nodes:
        context_str = "\n\n[LOG_CONTEXT]\n" + "\n---\n".join(context_nodes)
    
    print(f"Retrieved Context:\n{context_str}\n")
    
    # Persona
    persona_file = "kaia_persona.md"
    with open(persona_file, 'r') as f:
        system_prompt = f.read().strip()
    
    messages = [
        {"role": "system", "content": system_prompt + context_str},
        {"role": "user", "content": "Based on the provided log context (if any), generate a short, funny, and slightly mocking question or quip. "
            "Make it a single, sharp sentence. Be blunt and grounded. "
            "If there's log context, make fun of what was said or the user's logic. "
            "If no context, just ask a dry, cynical question about tech or life. "
            "No fluff. No intro. Just the quip."}
    ]
    
    print("Prompting LLM...")
    
    import ollama
    client = ollama.AsyncClient()
    
    response = await client.chat(
        model="gemma3:12b",
        messages=messages,
        options={
            "temperature": 1.0,
            "num_predict": 128,
            "repeat_penalty": 1.3,
        }
    )
    
    content = response['message']['content'].strip()
    print(f"\nGenerated Quip:\n{content}")

if __name__ == "__main__":
    asyncio.run(test_quip_generation())
