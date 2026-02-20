import sys
from datetime import datetime

# Mimic the logic added to MessageProcessor._construct_messages
def mimic_construct_messages(ctx_parent_context, ctx_root_context):
    full_system_prompt = "You are Kaia."
    
    if ctx_parent_context:
        label = "[REPLYING_TO_CONTEXT]"
        if ctx_root_context == ctx_parent_context:
            label = "[THREAD_ROOT_AND_PARENT]"
        full_system_prompt += f"\n\n{label}\n{ctx_parent_context}"
        
    if ctx_root_context and ctx_root_context != ctx_parent_context:
        full_system_prompt += f"\n\n[THREAD_START]\nThis conversation originated from:\n{ctx_root_context}"
    
    return full_system_prompt

def test_logic():
    # Case 1: Distinct root and parent
    p1 = "Exactly."
    r1 = "the echo chamber design is always the first casualty."
    result1 = mimic_construct_messages(p1, r1)
    print("Test Case 1: Distinct root and parent")
    print(result1)
    assert "[REPLYING_TO_CONTEXT]" in result1
    assert p1 in result1
    assert "[THREAD_START]" in result1
    assert r1 in result1
    print("Passed.")

    # Case 2: Same root and parent
    p2 = "echo chamber design"
    r2 = "echo chamber design"
    result2 = mimic_construct_messages(p2, r2)
    print("\nTest Case 2: Same root and parent")
    print(result2)
    assert "[THREAD_ROOT_AND_PARENT]" in result2
    assert p2 in result2
    assert "[THREAD_START]" not in result2
    print("Passed.")

    # Case 3: Only parent (old threads or direct replies)
    p3 = "I'm not catching the reference."
    r3 = None
    result3 = mimic_construct_messages(p3, r3)
    print("\nTest Case 3: Only parent")
    print(result3)
    assert "[REPLYING_TO_CONTEXT]" in result3
    assert p3 in result3
    assert "[THREAD_START]" not in result3
    print("Passed.")

if __name__ == "__main__":
    try:
        test_logic()
        print("\nLOGIC VERIFICATION SUCCESSFUL.")
    except Exception as e:
        print(f"\nLOGIC VERIFICATION FAILED: {e}")
        sys.exit(1)
