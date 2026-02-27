import os
import sys
from utils.core.kaia_rag import KaiaRAG
from utils.core.hallucination_detector import HallucinationDetector

def test_hallucination_detector():
    print("Testing HallucinationDetector...")
    hallucinated_text = "I am talking to Juanita about the agency's university network."
    clean_text = "I am talking about coffee and servers."
    
    assert HallucinationDetector.contains_hallucination(hallucinated_text) == True
    assert HallucinationDetector.contains_hallucination(clean_text) == False
    
    cleaned = HallucinationDetector.clean_response(hallucinated_text)
    print(f"Original: {hallucinated_text}")
    print(f"Cleaned: {cleaned}")
    assert "Juanita" not in cleaned
    print("✓ HallucinationDetector test passed")

def test_rag_logging():
    print("\nTesting RAG logging (UnboundLocalError fix)...")
    rag = KaiaRAG()
    try:
        success = rag.log_user_interaction(12345, "TestUser", "Hello", "I am a bot.")
        if success:
            print("✓ log_user_interaction test passed")
        else:
            print("✗ log_user_interaction test failed")
    except Exception as e:
        print(f"✗ log_user_interaction raised exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_hallucination_detector()
    test_rag_logging()
