import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.core.response_filter import EmergencyContaminationFilter

def test_filter():
    test_cases = [
        ("I remember back in '98, when the dot-com boom was in full swing.", True),
        ("Look, I remember a project back in '05. We were building a routing infrastructure.", True),
        ("Remember that server migration we did in '21? The one with the legacy storage?", True),
        ("There’s a bar down the street. The bartender, Leo, makes a decent Old Fashioned.", True),
        ("yeah, memory limits are more of a suggestion to docker.", False),
        ("coffee's cold, server's humming. what's up?", False)
    ]
    
    for response, should_filter in test_cases:
        filtered = EmergencyContaminationFilter.filter_response(response)
        is_filtered = filtered != response
        
        print(f"Input: {response[:50]}...")
        print(f"Filtered: {is_filtered}")
        
        if is_filtered != should_filter:
            print(f"❌ FAILED: Expected filtered={should_filter}, got {is_filtered}")
            # print(f"Result: {filtered}")
        else:
            print(f"✅ PASSED")
        print("-" * 20)

if __name__ == "__main__":
    test_filter()
