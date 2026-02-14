import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from utils.core.response_filter import BotSpeakFilter

def test_filtering():
    test_cases = [
        ("Kaia: hello there", "hello there"),
        ("Kaia:\nhello there", "hello there"),
        ("Kaia: Kaia: hello there", "hello there"),
        ("User: what are you doing?\nKaia: just working.", "what are you doing?\njust working."),
        ("Assistant: certainly!\n\nhere is your info.", "certainly!\n\nhere is your info."),
        ("(sighs) Kaia: i'm tired.", "i'm tired."),
        ("Kaia: *nods* sure thing.", "sure thing."),
        ("Kaia:   \n  \nhello", "hello"),
        ("Kaia: assistant: kaia: hello", "hello"),
    ]

    print("Running Response Filtering Tests...")
    all_passed = True
    for input_text, expected_output in test_cases:
        actual_output = BotSpeakFilter.harden(input_text)
        if actual_output == expected_output:
            print(f"✅ PASS: '{input_text.replace(chr(10), ' ')}' -> '{actual_output.replace(chr(10), ' ')}'")
        else:
            print(f"❌ FAIL: '{input_text.replace(chr(10), ' ')}'")
            print(f"   Expected: '{expected_output.replace(chr(10), ' ')}'")
            print(f"   Actual:   '{actual_output.replace(chr(10), ' ')}'")
            all_passed = False

    if all_passed:
        print("\nAll filtering tests passed successfully!")
    else:
        print("\nSome tests failed. Review the output above.")
        sys.exit(1)

if __name__ == "__main__":
    test_filtering()
