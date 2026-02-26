import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock discord and other modules to avoid import errors
class MockIntents:
    def __init__(self):
        self.message_content = False
    @staticmethod
    def default():
        return MockIntents()

sys.modules['discord'] = type('module', (), {'Client': object, 'Intents': MockIntents, 'abc': type('module', (), {'Messageable': object})})
sys.modules['discord.ext'] = type('module', (), {'commands': type('module', (), {'Bot': lambda **kwargs: None}), 'tasks': type('module', (), {'loop': lambda **kwargs: lambda x: x})})
sys.modules['watchdog.observers'] = type('module', (), {'Observer': object})
sys.modules['watchdog.events'] = type('module', (), {'FileSystemEventHandler': object})
sys.modules['utils.core.kaia_intelligence'] = type('module', (), {
    'SemanticCache': object, 'ModelWarmPool': object, 'QueryClassifier': object, 
    'ContextOptimizer': object, 'RelevanceFeedback': object, 'PerformanceMonitor': object, 
    'PersonalizationEngine': object, 'PersistentStateManager': object, 'IntelligentCacheInvalidator': object
})
sys.modules['utils.infrastructure.gpu.clear_gpu_memory'] = type('module', (), {'clear_gpu_memory': lambda: None})
sys.modules['utils.infrastructure.logging.kaia_logger'] = type('module', (), {
    'log_info': print, 'log_success': print, 'log_warning': print, 'log_error': print, 
    'log_action': print, 'log_critical': print, 'log_separator': print, 'log_message_received': print,
    'log_model_action': print, 'log_context_retrieval': print, 'log_response': print, 'log_file': print
})

# Extract EmergencyContaminationFilter from Kaiacord.py
try:
    with open('Kaiacord.py', 'r') as f:
        code = f.read()
    
    # Use regex to find the class definition
    import re
    match = re.search(r'class EmergencyContaminationFilter:.*?(?=\n\n#|\n\nclass|\n\nif __name__)', code, re.DOTALL)
    if match:
        class_code = match.group(0)
        # We need to mock List and datetime for the exec
        from typing import List
        from datetime import datetime
        # Mock log_warning
        def log_warning(msg): print(f"LOG: {msg}")
        
        local_ns = {'List': List, 'datetime': datetime, 'log_warning': log_warning}
        exec(class_code, {}, local_ns)
        EmergencyContaminationFilter = local_ns['EmergencyContaminationFilter']
    else:
        print("❌ Could not find EmergencyContaminationFilter in Kaiacord.py")
        sys.exit(1)
except Exception as e:
    print(f"❌ Error extracting class: {e}")
    sys.exit(1)

def test_filtering():
    test_cases = [
        {
            "name": "Metadata Leak",
            "input": "yeah. what's up?\n\n[optimized: saved 4802 tokens]",
            "expected": "yeah. what's up?"
        },
        {
            "name": "User Profile Header",
            "input": "USER PROFILE: EKCO\nQUICK REFERENCE\n- Likes coffee\n- Blunt\n\nyeah. what's up?",
            "expected": "yeah. what's up?"
        },
        {
            "name": "Mixed Dialogue and Profile",
            "input": "i remember you. you like coffee.\nHOW TO INTERACT WITH THEM\n- Be blunt.\n\nanyway, what do you need?",
            "expected": "i remember you. you like coffee.\nanyway, what do you need?"
        },
        {
            "name": "Alan Turing Contamination",
            "input": "Alan Turing was a mathematician.\nyeah. what's up?",
            "expected": "yeah. what's up?"
        },
        {
            "name": "Empty Fallback",
            "input": "USER PROFILE: EKCO\n[optimized: saved 100 tokens]",
            "expected": "" # Should be empty or handled by the caller
        }
    ]

    passed = 0
    for case in test_cases:
        result = EmergencyContaminationFilter.clean_response_for_discord(case["input"])
        if result == case["expected"]:
            print(f"✅ PASSED: {case['name']}")
            passed += 1
        else:
            print(f"❌ FAILED: {case['name']}")
            print(f"   Input: {repr(case['input'])}")
            print(f"   Expected: {repr(case['expected'])}")
            print(f"   Got: {repr(result)}")

    print(f"\n📊 Results: {passed}/{len(test_cases)} passed.")
    return passed == len(test_cases)

if __name__ == "__main__":
    test_filtering()
