import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from utils.core.knowledge_boundary import KnowledgeBoundary

def test_whitelist():
    kb = KnowledgeBoundary()
    
    test_cases = [
        "Henceforth the Empire shall rise.",
        "The Soldiers of the Saint are coming.",
        "Welcome to Tomainia, a Tomainian friend.",
        "The Dictator lives in the Palace.",
        "The Fermi Paradox suggests Liu Cixin might be right.",
        "BotSpeakFilter is working correctly.",
        "Highlighting and Stunting are common terms.",
        "OriginalContentGuy has a new Thesis.",
        "Moreso, the Jew and Gentile live in peace.",
        "Machinery and Greed are themes."
    ]
    
    all_passed = True
    for text in test_cases:
        result = kb.check_known_entities(text, "This is context.")
        print(f"Text: {text}")
        print(f"Unknown: {result['unknown_in_context']}")
        if result['unknown_in_context']:
            all_passed = False
            print("FAILED")
        else:
            print("PASSED")
        print("-" * 20)
    
    if all_passed:
        print("\nALL WHITELIST TESTS PASSED")
        sys.exit(0)
    else:
        print("\nSOME TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    test_whitelist()
