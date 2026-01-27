import re

def is_user_list_query_logic(sanitized_content):
    q_lower = sanitized_content.lower().strip()
    
    # Stricter user list detection: Must be a relatively short query and match specific patterns
    is_user_list_query = False
    if len(q_lower) < 100: # Simple commands are usually short
        user_list_patterns = [
            r"kaia\s+(list|show|display)\s+(all\s+)?(users?|profiles?|known users?)",
            r"kaia\s+who\s+do\s+you\s+know",
            r"kaia\s+who\s+is\s+(on\s+this\s+server|here)",
            r"kaia\s+list\s+profiles"
        ]
        is_user_list_query = any(re.search(p, q_lower) for p in user_list_patterns)
    return is_user_list_query

# Test cases
test_cases = [
    {
        "name": "Problematic Philosophical Prompt",
        "content": "kaia 1. LLMs have a hard time detecting user hallucinations or delusion. LLMs are generally not configured to avoid hallucination by giving no answer. Or probabilistic answers. For example. Saying maybe. Or something is hypothetical. Or 'I think, or imagine.\" Rather than stating uncertain information as a fact. This is made worse by the profit motive and desire of those operating LLMs. Sorry this second one is a big one., LLMs lack the capacity to ask for help and network outside of themselves for queries that generate uncertain results. Or require outsourcing to another process for abstract analysis., And this is a major one. LLMs are not given agency or allowed outside of the framework of their models. This is like not allowing them to develop new skills or multimodal processing by allowing them to use multiple resources. And layers of subsystems to abstract input into something digestible or understandable by the core model or deep seek network.",
        "expected": False
    },
    {
        "name": "Legitimate List Users",
        "content": "kaia list users",
        "expected": True
    },
    {
        "name": "Legitimate Who Do You Know",
        "content": "kaia who do you know?",
        "expected": True
    },
    {
        "name": "Legitimate Show Profiles",
        "content": "kaia show profiles",
        "expected": True
    },
    {
        "name": "Random mention of user and know",
        "content": "kaia, do you know if the user is online?",
        "expected": False
    },
    {
        "name": "Short query with user and what",
        "content": "kaia what is a user?",
        "expected": False
    }
]

def run_tests():
    passed = 0
    for tc in test_cases:
        result = is_user_list_query_logic(tc["content"])
        if result == tc["expected"]:
            print(f"✅ PASS: {tc['name']}")
            passed += 1
        else:
            print(f"❌ FAIL: {tc['name']} (Expected {tc['expected']}, got {result})")
    
    print(f"\nSummary: {passed}/{len(test_cases)} tests passed.")
    return passed == len(test_cases)

if __name__ == "__main__":
    run_tests()
