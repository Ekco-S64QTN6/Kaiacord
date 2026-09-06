import sys
import os

# Add the project root to sys.path
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.knowledge_boundary import KnowledgeBoundary
from utils.core.response_filter import HallucinationDetector

def test_whitelist():
    kb = KnowledgeBoundary()
    # These terms should NOT be flagged as unknown entities.
    # They are either in common_words (filtered out) or in lore_keywords (marked as known).
    test_terms = [
        'Luo', 'Trisolaris', 'Trisolarans', 'Wallfacer', 'Research', 'Audit', 
        'Stabilization', 'Quote', 'Unread', 'Posts', 'Mechanism'
    ]
    
    print("--- Testing Whitelist (False Positive Prevention) ---")
    for term in test_terms:
        query = f"Tell me about {term}"
        context = ""
        result = kb.check_known_entities(query, context)
        
        # In check_known_entities, 'unknown_in_context' contains entities that 
        # WERE extracted but NOT found in known_entities/whitelist/context.
        # If a term is in common_words, it isn't even extracted.
        # If it is in lore_keywords, it is extracted but marked as known.
        # Either way, it should NOT be in 'unknown_in_context'.
        
        is_flagged = term in result['unknown_in_context']
        status = "❌ FLAGGED AS UNKNOWN" if is_flagged else "✅ NOT FLAGGED (PASSED)"
        print(f"{term}: {status}")

def test_hallucination_detection():
    print("\n--- Testing Hallucination Detection ---")
    hallucinations = [
        "Tenno Heika was a fascinating figure.",
        "Di Shang performed the Cosmic Sociology spell.",
        "The Cosmic Sociology spell explains the universe."
    ]
    
    for h in hallucinations:
        is_hallucination = HallucinationDetector.contains_hallucination(h)
        status = "✅ DETECTED" if is_hallucination else "❌ MISSED"
        print(f"'{h}': {status}")

if __name__ == "__main__":
    test_whitelist()
    test_hallucination_detection()
