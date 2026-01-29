import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.kaia_intelligence import QueryClassifier

def test_classifier():
    # Mock the sync client to avoid connection attempts during regex testing
    from unittest.mock import MagicMock
    
    classifier = QueryClassifier()
    classifier.sync_client = MagicMock() # Don't actually connect
    
    test_cases = [
        ("status kaia", "COMMAND"),
        ("stats", "COMMAND"),
        ("list users", "COMMAND"),
        ("who are you", "IDENTITY"),
        ("tell me about yourself", "IDENTITY"),
        ("what's the news", "NEWS"),
        ("hi kaia", "GREETING"),
        ("how are you", "PERSONAL"),
        ("just a general question", "GENERAL")
    ]
    
    print("\n--- Testing Classifier Regex Patterns ---")
    all_passed = True
    for query, expected in test_cases:
        # We use _classify_rules directly to test the regex without model calls
        result = classifier._classify_rules(query)
        status = "✅" if result == expected else "❌"
        print(f"{status} Query: '{query}' | Expected: {expected} | Got: {result}")
        if result != expected:
            all_passed = False
            
    if all_passed:
        print("\n✨ All regex tests passed!")
    else:
        print("\n⚠️ Some regex tests failed.")
    
    return all_passed

if __name__ == "__main__":
    test_classifier()
