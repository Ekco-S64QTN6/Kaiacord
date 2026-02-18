import sys
import os

# Add project root to path
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.knowledge_boundary import KnowledgeBoundary

def test_military_terms_whitelist():
    print("Testing Military Terms Whitelist in KnowledgeBoundary...")
    boundary = KnowledgeBoundary()
    
    test_queries = [
        "Affirmative, I understand.",
        "Roger that, Kaia.",
        "Wilco on the task.",
        "Copy that.",
        "Over and out.",
        "Acknowledged.",
        "Hi Kaia",
        "Kek",
        "Total Recall",
        "Cyber Truck"
    ]
    
    all_passed = True
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        check = boundary.check_known_entities(query, "")
        if check["unknown_in_context"]:
            print(f"✗ FAILED: Found unknown entities: {check['unknown_in_context']}")
            all_passed = False
        else:
            print("✓ PASSED: No unknown entities flagged.")
            
    if all_passed:
        print("\n=== ALL MILITARY TERM TESTS PASSED ===")
    else:
        print("\n=== SOME TESTS FAILED ===")

if __name__ == "__main__":
    test_military_terms_whitelist()
