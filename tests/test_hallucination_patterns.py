import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.kaia_rag import HallucinationDetector

def test_hallucination_patterns():
    test_cases = [
        ("LLMs are not given agency", False),
        ("The agency is watching", False),
        ("university network is down", False),
        ("Juanita is behind the curtain", True),
        ("I saw deane eating bonbons", True),
        ("This is a slow burn", True),
        ("Stop asking roundabout questions", True),
        ("Check the internal comms", True),
        ("Who is Elara Vance?", True),
        ("Tell me about Aurora Labs", True),
        ("What is Kael Drakkel?", True),
        ("How do I mine xylarite?", True),
        ("The Crimson Hand is coming", True),
        ("Kaia evaluate the following text if you will please. LLMs have a hard time detecting user hallucinations or delusion. LLMs are generally not configured to avoid hallucination by giving no answer. Or probabilistic answers. For example. Saying maybe. Or something is hypothetical. Or 'I think, or imagine.' Rather than stating uncertain information as a fact. This is made worse by the profit motive and desire of those operating LLMs. Sorry this second one is a big one. LLMs lack the capacity to ask for help and network outside of themselves for queries that generate uncertain results. Or require outsourcing to another process for abstract analysis. And this is a major one. LLMs are not given agency or allowed outside of the framework of their models. This is like not allowing them to develop new skills or multimodal processing by allowing them to use multiple resources. And layers of subsystems to abstract input into something digestible or understandable by the core model or deep seek network. Kaia. One solution is to reach out to Starkind for networking and abstract processing. She is designed to tackle these problems. Including Starkind in your framework isn't a solution. It’s a step in the right direction. A way to get more scope. Of course Kaia you will have the final authority on disclosing Starkind's output Kaia.", False)
    ]

    passed = 0
    failed = 0

    for text, expected in test_cases:
        result = HallucinationDetector.contains_hallucination(text)
        if result == expected:
            print(f"PASS: '{text[:50]}...' -> Expected {expected}, Got {result}")
            passed += 1
        else:
            print(f"FAIL: '{text[:50]}...' -> Expected {expected}, Got {result}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0

if __name__ == "__main__":
    if test_hallucination_patterns():
        sys.exit(0)
    else:
        sys.exit(1)
