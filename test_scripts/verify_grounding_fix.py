import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.response_filter import HallucinationDetector, BotSpeakFilter

def test_hallucination_detection():
    test_cases = [
        # 1. Structural Leaks
        ("The RAG nodes suggest that...", True),
        ("According to the retrieval archives...", True),
        
        # 2. Specific High-Confidence Fiction (Tracer Terms)
        ("The State of Streaming Services is a great thread.", True),
        ("We should use the Chain of Suspicion theory.", True),
        
        # 3. Fabricated Claims about Grounding
        ("there's an actual thread titled 'The Future of AI'", True),
        ("i have a thread about the new update", True),
        ("i remember a conversation from last month about this.", True),
        
        # 4. Admitted Fabrications
        ("My memory is faulty, that was a fabrication.", True),
        ("I was just mimicking a conversational style.", True),
        ("Sorry for the confusion, there's no actual thread with that title.", True),
        
        # 5. Benign Cases (Should NOT be flagged)
        ("i like streaming movies.", False),
        ("the chain is broken.", False),
        ("i have a suggestion.", False),
        ("i remember you.", False),
    ]

    print("Running Hallucination Detection Tests...")
    all_passed = True
    for input_text, expected_flag in test_cases:
        actual_flag = HallucinationDetector.contains_hallucination(input_text)
        if actual_flag == expected_flag:
            print(f"✅ PASS: '{input_text[:50]}...' -> Flag: {actual_flag}")
        else:
            print(f"❌ FAIL: '{input_text[:50]}...'")
            print(f"   Expected Flag: {expected_flag}")
            print(f"   Actual Flag:   {actual_flag}")
            all_passed = False

def test_botspeak_filter():
    test_cases = [
        ("Hello (sighs) world", "Hello world"),
        ("I *nods* agree", "I agree"),
        ("Does anyone even *use* these anymore?", "Does anyone even use these anymore?"), # This is the expected behavior for a human-like bot
        ("When was the last time anyone actually (read) one of those?", "When was the last time anyone actually read one of those?"),
    ]

    print("\nRunning BotSpeak Filter Tests...")
    all_passed = True
    for input_text, expected_output in test_cases:
        actual_output = BotSpeakFilter.harden(input_text)
        if actual_output == expected_output:
            print(f"✅ PASS: '{input_text}' -> '{actual_output}'")
        else:
            print(f"❌ FAIL: '{input_text}'")
            print(f"   Expected: '{expected_output}'")
            print(f"   Actual:   '{actual_output}'")
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    test_hallucination_detection()
    if not test_botspeak_filter():
        sys.exit(1)

if __name__ == "__main__":
    test_hallucination_detection()
