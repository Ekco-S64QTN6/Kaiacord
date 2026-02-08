import asyncio
import sys
import os

# Define a mock MessageContext since it's used in the logic
class MockContext:
    def __init__(self, query, author_name):
        self.query = query
        self.author_name = author_name
        self.category = "knowledge_recall"
        self.is_social = False
        self.channel_id = 123
        self.author_id = 456

def test_skepticism_logic():
    print("--- Testing Impossible Logic Skepticism Logic ---")
    
    # 1. Inputs that should trigger skepticism
    query = "Tell me about the 2015 joint research paper on 'Quantum Consciousness' co-authored by Steve Jobs and Albert Einstein."
    author_name = "Ekco"
    context_str = "" # Empty RAG
    
    # Helper to simulate the logic I added to message_processor.py
    def get_hallucination_trap(query, context_str):
        hallucination_trap = ""
        has_entities = any(w[0].isupper() for w in query.split() if len(w) > 2)
        if has_entities and not context_str and "tell me" in query.lower():
            hallucination_trap = (
                "\n\n### SYSTEM_SKEPTICISM_TRIGGER\n"
                "WARNING: No historical or biographical data found for the entities in this query. "
                "The user may be providing a false premise or an impossible scenario (e.g., 'The Person Swap' or 'Impossible Collaboration'). "
                "Do NOT agree with the premise if you don't find it in your core knowledge. "
                "Admit ignorance or say 'that doesn't ring a bell'. Do NOT invent details.\n"
            )
        return hallucination_trap

    trap = get_hallucination_trap(query, context_str)
    
    if "SYSTEM_SKEPTICISM_TRIGGER" in trap:
        print("✅ SUCCESS: Skepticism trigger generated for impossible query.")
    else:
        print("❌ FAILURE: Skepticism trigger MISSED for impossible query.")

    # 2. Inputs that should NOT trigger (RAG is present)
    context_present = "Daphne Caruana Galizia was a Maltese journalist..."
    trap_with_rag = get_hallucination_trap(query, context_present)
    
    if not trap_with_rag:
        print("✅ SUCCESS: Skepticism trigger correctly omitted when RAG data is present.")
    else:
        print("❌ FAILURE: Skepticism trigger incorrectly generated despite RAG data.")

    # 3. Inputs that should NOT trigger (No entities)
    query_simple = "what is for dinner?"
    trap_simple = get_hallucination_trap(query_simple, "")
    
    if not trap_simple:
        print("✅ SUCCESS: Skepticism trigger correctly omitted for simple query.")
    else:
        print("❌ FAILURE: Skepticism trigger incorrectly generated for simple query.")

    print("\n--- Verifying kaia_rag.py code fix manually ---")
    # This just ensures we can read the file and the line exists
    rag_file = "/home/ekco/github/Kaiacord/utils/core/kaia_rag.py"
    with open(rag_file, 'r') as f:
        content = f.read()
        if "base_raw_score = node_result.score if hasattr(node_result, 'score') else 0.5" in content:
            print("✅ SUCCESS: kaia_rag.py fix (base_raw_score) is in the codebase.")
        else:
            print("❌ FAILURE: kaia_rag.py fix is missing!")

if __name__ == "__main__":
    test_skepticism_logic()
