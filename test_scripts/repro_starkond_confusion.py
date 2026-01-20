import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies
sys.modules['pypdf'] = MagicMock()
sys.modules['docx2txt'] = MagicMock()
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()

from kaia_rag import KaiaRAG

async def repro_confusion():
    print("--- Reproducing Starkond Identity Confusion ---")
    
    rag = KaiaRAG()
    
    # User: Starkond the Prion
    user_name = "Starkond the Prion"
    user_id = "519557167779676160"
    
    # Query that mentions Ekco
    query = "Kaia who am i? Ekco says you have a good memory."
    
    print(f"User: {user_name}")
    print(f"Query: {query}")
    
    # Populate index with test data
    print("Populating index...")
    rag.log_user_interaction("177011971818782721", "Ekco", "kaia who are you", "i'm the cartographer. i map the gaps.")
    rag.log_user_interaction("519557167779676160", "Starkond the Prion", "kaia tell me about yourself", "i'm a blunt instrument. i process and relay.")
    
    print("\nRetrieving context...")
    context_nodes = await asyncio.to_thread(
        rag.retrieve, 
        query, 
        user_id=user_id, 
        user_name=user_name, 
        top_k=5
    )
    
    print(f"Retrieved {len(context_nodes)} nodes.")
    for i, node in enumerate(context_nodes):
        print(f"\nNode {i} Label: {node.splitlines()[0]}")
        print(f"Content snippet: {node.splitlines()[1][:100]}...")

    # Check if Ekco's context is present
    has_ekco_context = any("EKCO" in node.splitlines()[0] for node in context_nodes)
    print(f"\nHas Ekco context: {has_ekco_context}")
    
    # Simulate the prompt construction
    context_str = "\n\n".join(context_nodes)
    
    # Load persona
    with open("kaia_persona.md", 'r') as f:
        system_prompt = f.read().strip()
    
    rag_block = (
        f"[CURRENT_USER]: {user_name}\n"
        "[HISTORICAL_CONTEXT]\n"
        "The following fragments are from your historical records. They are facts about the users you interact with. "
        "Use them to maintain continuity and recognize who you are talking to.\n"
        "---\n"
        f"{context_str}\n"
        "[END_CONTEXT]"
    )
    
    reinforcement = (
        "\n\n[CRITICAL_RULES]\n"
        "5. DO NOT prefix your response with a name (e.g., 'ekco.', 'kaia:', 'Response:'). Just start speaking.\n"
        "6. IDENTITY RESONANCE: You are currently talking to [CURRENT_USER]. If they ask 'who am i?', you MUST use the [USER_PROFILE_AND_HISTORY] fragments labeled with their name (and '(CURRENT USER)') to identify them. Do not be dismissive. NEVER say 'that's up to you to tell me' or 'that's your business' if you have records for them. Provide a detailed, paragraph-style summary of who they are based on your records—include their personality, history, and interests. They are the user, you are Kaia.\n"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
        {"role": "system", "content": f"{rag_block}{reinforcement}"}
    ]
    
    print("\nPrompting LLM (Gemma 3)...")
    import ollama
    client = ollama.AsyncClient()
    
    response = await client.chat(
        model="gemma3:12b",
        messages=messages,
        options={"temperature": 0.0} # Deterministic for testing
    )
    
    content = response['message']['content'].strip()
    print(f"\nKaia's Response:\n{content}")
    
    if "ekco" in content.lower() and "starkond" not in content.lower():
        print("\nCONFIRMED: Kaia addressed Starkond as 'ekco'.")
    elif "ekco" in content.lower():
        print("\nWARNING: Kaia mentioned 'ekco', possibly addressing the user.")
    else:
        print("\nNOT REPRODUCED: Kaia did not mention 'ekco'.")

if __name__ == "__main__":
    asyncio.run(repro_confusion())
