import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from utils.core.knowledge_boundary import KnowledgeBoundary
from utils.core.response_filter import BotSpeakFilter
from utils.infrastructure.system.yaml_config import config

def test_entity_recognition():
    print("Testing Entity Recognition...")
    kb = KnowledgeBoundary(config.knowledge_base_dir)
    
    test_query = "What do you know about Kaia Kuroshi?"
    context = ""
    whitelist = {"Kaia"}
    
    result = kb.check_known_entities(test_query, context, whitelist=whitelist)
    print(f"Entities found (should be empty or known): {result['query_entities']}")
    print(f"Unknown entities (should be empty): {result['unknown_in_context']}")
    
    if result["all_known"]:
        print("✅ SUCCESS: All entities recognized or whitelisted.")
    else:
        print(f"❌ FAILURE: Unknown entities found: {result['unknown_in_context']}")

def test_quip_filtering():
    print("\nTesting Quip Filtering...")
    
    test_cases = [
        ("What are you working on now?", ""), # Should be empty
        ("What are you doing today?", ""),    # Should be empty
        ("So, what are you working on?", "So,"),
        ("what are you doing?", ""),
        ("System is humming. What's on your mind?", "System is humming."),
        ("Normal message that should pass.", "Normal message that should pass.")
    ]
    
    for text, expected in test_cases:
        filtered = BotSpeakFilter.strip_bot_speak(text)
        if filtered == expected:
            print(f"✅ SUCCESS: Result for '{text}' was '{filtered}'")
        else:
            print(f"❌ FAILURE: Result for '{text}' was '{filtered}', expected '{expected}'")

if __name__ == "__main__":
    test_entity_recognition()
    test_quip_filtering()
