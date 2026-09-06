import sys
import os
sys.path.append(os.getcwd())

from utils.core.knowledge_boundary import KnowledgeBoundary

def test_hardened_boundary():
    kb = KnowledgeBoundary()
    
    test_cases = [
        ("NASA is planning a mission.", "Acronym support test (NASA)."),
        ("The RTX 5090 is fast.", "Acronym support test (RTX)."),
        ("Goose is chirping.", "Common noun sentence starter check."),
        ("Starkind is a mystery.", "Lore-specific word check (should be in DB)."),
        ("I met John Doe.", "Multi-word phrase check."),
        ("This is some context with a typo: Starkibd.", "Fuzzy match check (Starkibd vs Starkind)."),
    ]
    
    print("--- Testing Hardened Boundary ---")
    context = "We are researching the Starkind and its origins. This is a long context to test performance guards if needed, but here it is short."
    
    for text, desc in test_cases:
        entities = kb.extract_entities(text)
        print(f"Text: '{text}'")
        print(f"Desc: {desc}")
        print(f"Extracted: {entities}")
        
        check = kb.check_known_entities(text, context)
        print(f"Unknown: {check['unknown_in_context']}")
        print("-" * 20)

    # Test performance guard
    print("--- Testing Fuzzy Match Performance Guard ---")
    long_context = "word " * 600 + " Starkind"
    # Perfect match should still work as it doesn't need fuzzy
    check_perfect = kb.check_known_entities("Tell me about Starkind.", long_context)
    print(f"Perfect match in long context: {check_perfect['all_known']}")
    
    # Fuzzy match should be skipped due to context size
    check_fuzzy = kb.check_known_entities("Tell me about Starkibd.", long_context)
    print(f"Fuzzy match (typo) in long context: {check_fuzzy['all_known']}")
    print(f"Unknown in long context: {check_fuzzy['unknown_in_context']}")

if __name__ == "__main__":
    test_hardened_boundary()
