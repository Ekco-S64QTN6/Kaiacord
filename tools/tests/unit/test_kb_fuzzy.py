from utils.core.knowledge_boundary import KnowledgeBoundary

def test_fuzzy_matching():
    kb = KnowledgeBoundary()
    
    # Simulate a query and a context with a typo
    query = "Kaia did you hear about Trindad Chambliss?"
    context = "The news report mentions Trinidad Chambliss is suing to be held back a grade."
    
    # 1. Test extraction
    entities = kb.extract_entities(query)
    print(f"Extracted entities: {entities}")
    
    # 2. Test boundary check
    results = kb.check_known_entities(query, context)
    print(f"Boundary check results: {results}")
    
    # Verification
    is_fuzzy_working = "Trindad" in results["known_in_context"]
    print(f"\nFuzzy matching 'Trindad' -> 'Trinidad' worked: {is_fuzzy_working}")
    
    # Test another case (substring)
    query2 = "Tell me about Chamblis."
    results2 = kb.check_known_entities(query2, context)
    print(f"Fuzzy matching 'Chamblis' -> 'Chambliss' worked: {'Chamblis' in results2['known_in_context']}")

if __name__ == "__main__":
    test_fuzzy_matching()
