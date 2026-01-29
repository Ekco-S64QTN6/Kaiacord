import sys
import os

# Add project root to path
sys.path.append('/home/ekco/github/Kaiacord')

from utils.knowledge_boundary import KnowledgeBoundary

def test_knowledge_boundary():
    print("Testing KnowledgeBoundary...")
    boundary = KnowledgeBoundary()
    
    print(f"Loaded {len(boundary.known_entities)} known entities.")
    
    # Test cases
    test_queries = [
        "Who is Mark?",
        "Tell me about Kaia.",
        "What do you know about Thorne and Jules?",
        "Who is Ekco?",
        "Explain quantum computing."
    ]
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        entities = boundary.extract_entities(query)
        print(f"Extracted entities: {entities}")
        
        # Simulate check with empty context (worst case)
        check = boundary.check_known_entities(query, "")
        print(f"Check result: {check}")
        
        if check["unknown_in_context"]:
            response = boundary.generate_boundary_response(check["unknown_in_context"], query)
            print(f"Boundary response: {response}")
        else:
            print("Allowed to proceed.")

if __name__ == "__main__":
    test_knowledge_boundary()
