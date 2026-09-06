
import sys
import os
sys.path.append(os.getcwd())

from utils.core.response_filter import BotSpeakFilter

def test_harden():
    test_cases = [
        ("i'm doing alright. what's on your mind?", "i'm doing alright."),
        ("yeah, the server is humming nicely. any thoughts?", "yeah, the server is humming nicely."),
        ("i lost a weekend to that bug in '08. why? what’s driving your interest?", "i lost a weekend to that bug in '08."),
        ("the news is bleak today. you following anything specific?", "the news is bleak today."),
        ("it's a memory issue. what are you working on?", "it's a memory issue."),
        ("i don't have an answer for that. let me know if you need?", "i don't have an answer for that."),
        ("just stay grounded. anything else?", "just stay grounded."),
        ("this is a legit question? i'm not sure.", "this is a legit question? i'm not sure."), # Should NOT strip if not in bait patterns
        ("who are you?", "who are you?"), # Should NOT strip legitimate short questions
    ]
    
    for input_text, expected in test_cases:
        result = BotSpeakFilter.strip_trailing_questions(input_text)
        print(f"Input: {input_text}")
        print(f"Result: {result}")
        print(f"Expected: {expected}")
        assert result == expected
        print("---")

if __name__ == "__main__":
    test_harden()
    print("Verification complete. All bait questions stripped correctly.")
