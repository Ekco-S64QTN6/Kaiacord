import asyncio
import sys
import os
import re
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from utils.core.kaia_rag import HallucinationDetector

def test_nuanced_detection():
    print("\n--- Testing Nuanced Hallucination Detection ---")
    
    # These SHOULD be detected (Identity claims)
    problematic_phrases = [
        "I helped design the automated irrigation systems for the hydroponics lab",
        "It reminds me of the early days of the hydroponics lab",
        "My work at the hydroponics lab was intense",
        "I was the engineer for the hydroponics project"
    ]
    
    # These SHOULD NOT be detected (Technical context)
    feature_phrases = [
        "tell me about the hydroponics in the book Snow Crash",
        "how does a nutrient balance work in hydroponics?",
        "we need to fix the irrigation system in our garden",
        "is there a fungal infestation in the hydroponics bay?",
        "I'm reading about hydroponics"
    ]
    
    all_passed = True
    
    print("\nEXPECTED TO BE DETECTED:")
    for phrase in problematic_phrases:
        detected = HallucinationDetector.contains_hallucination(phrase)
        status = "✅" if detected else "❌"
        print(f"{status} Phrase: '{phrase}' -> Detected: {detected}")
        if not detected: all_passed = False
        
    print("\nEXPECTED NOT TO BE DETECTED:")
    for phrase in feature_phrases:
        detected = HallucinationDetector.contains_hallucination(phrase)
        status = "✅" if not detected else "❌"
        print(f"{status} Phrase: '{phrase}' -> Detected: {detected}")
        if detected: all_passed = False
        
    if all_passed:
        print("\n✅ ALL NUANCED TESTS PASSED.")
    else:
        print("\n❌ SOME NUANCED TESTS FAILED.")

if __name__ == "__main__":
    test_nuanced_detection()
