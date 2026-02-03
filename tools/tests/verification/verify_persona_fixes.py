import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from utils.boilerplate_detector import BoilerplateDetector
from Kaiacord import EmergencyContaminationFilter

def test_boilerplate_detector():
    print("Testing BoilerplateDetector...")
    test_cases = [
        ("here is your code. what are you building, really?", "here is your code."),
        ("i'm not sure. what’s it supposed to *do*?", "i'm not sure."),
        ("that sounds complex. what’s the problem, really?", "that sounds complex."),
        ("yeah. what's up?", ""),
        ("normal response without boilerplate.", "normal response without boilerplate.")
    ]
    
    for input_text, expected in test_cases:
        result = BoilerplateDetector.clean_response(input_text)
        if result == expected:
            print(f"✅ PASS: '{input_text}' -> '{result}'")
        else:
            print(f"❌ FAIL: '{input_text}' -> '{result}' (expected '{expected}')")

def test_contamination_filter():
    print("\nTesting EmergencyContaminationFilter...")
    test_cases = [
        ("i remember a guy named mark back at xerox in the 90s.", ""),
        ("mark was a great engineer.", ""),
        ("xerox had some interesting tech.", ""),
        ("i remember the guy who worked on this.", ""),
        ("this is a clean response about linux.", "this is a clean response about linux.")
    ]
    
    for input_text, expected in test_cases:
        result = EmergencyContaminationFilter.filter_response(input_text)
        if result == expected:
            print(f"✅ PASS: '{input_text}' -> '{result}'")
        else:
            print(f"❌ FAIL: '{input_text}' -> '{result}' (expected '{expected}')")

if __name__ == "__main__":
    test_boilerplate_detector()
    test_contamination_filter()
