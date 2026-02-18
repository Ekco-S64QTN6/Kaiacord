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
    print(f"Entities found: {result['query_entities']}")
    print(f"Unknown entities: {result['unknown_in_context']}")
    
    if "Kaia Kuroshi" in result["known_in_context"] or "Kaia Kuroshi" in result["query_entities"] and result["all_known"]:
        print("✅ SUCCESS: Kaia Kuroshi recognized.")
    else:
        # Check if it was extracted at all
        if "Kaia Kuroshi" not in result["query_entities"]:
            # Maybe it was extracted as Kaia and Kuroshi separately or something else
            print(f"❌ FAILURE: Kaia Kuroshi not extracted as a single entity. Matches: {result['query_entities']}")
        else:
            print("❌ FAILURE: Kaia Kuroshi still unknown.")

def test_quip_filtering():
    print("\nTesting Quip Filtering...")
    
    test_cases = [
        "What are you working on now?",
        "What are you doing today?",
        "So, what are you working on?",
        "what are you doing?",
        "Normal message that should pass."
    ]
    
    for text in test_cases:
        filtered = BotSpeakFilter.strip_bot_speak(text)
        if not filtered and text != "Normal message that should pass.":
            print(f"✅ SUCCESS: Filtered '{text}'")
        elif filtered == text and text == "Normal message that should pass.":
            print(f"✅ SUCCESS: Passed '{text}'")
        else:
            print(f"❌ FAILURE: Result for '{text}' was '{filtered}'")

if __name__ == "__main__":
    test_entity_recognition()
    test_quip_filtering()
