import sys
import os
from pathlib import Path

# Mock dependencies
sys.path.append('/home/ekco/github/Kaiacord')

from utils.core.knowledge_boundary import KnowledgeBoundary

def test_knowledge_boundary():
    kb = KnowledgeBoundary()
    
    # Test cases for common technical noise
    test_queries = [
        "User: Initializing KaiaRAG...",
        "[23:28:27] SUCCESS: Populated 659 valid indexed files.",
        "Detected unknown entities: ['Initializing', 'Populated']",
        "Who is Gemini?", # Should be known
        "Tell me about Tessier and Ashpool." # Should be known if Lore is indexed
    ]
    
    context = "I am Kaia, an AI system."
    
    for query in test_queries:
        print(f"\n--- Query: '{query}' ---")
        result = kb.check_known_entities(query, context)
        print(f"Entities found: {result['query_entities']}")
        print(f"Unknown entities: {result['unknown_in_context']}")
        
        # 'Initializing' and 'Populated' should NOT be in Unknown
        for entity in ['Initializing', 'Populated']:
            if entity in result['unknown_in_context']:
                print(f"❌ FAIL: '{entity}' incorrectly flagged as unknown.")
            elif entity in result['query_entities']:
                 print(f"✅ PASS: '{entity}' correctly filtered out or recognized as common.")

if __name__ == "__main__":
    test_knowledge_boundary()
