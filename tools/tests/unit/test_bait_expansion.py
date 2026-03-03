import sys
import os
sys.path.append(os.getcwd())

from utils.core.response_filter import BotSpeakFilter

def test_bait_expansion():
    # Test instances of problematic AI questions
    problematic_phrases = [
        "what's consuming your time?",
        "what are you reading?",
        "what's on your mind?",
        "what are you up to?",
        "what are you working on?",
        "what are you listening to?",
        "what have you been playing lately?",
        "what has kept you busy?",
        "What's on your mind? (case test)",
        "So, what are you reading right now?",
        "what are you reading currently?",
        "what are you watching today?"
    ]

    for phrase in problematic_phrases:
        # Test as standalone line
        result = BotSpeakFilter.strip_bot_speak(phrase)
        print(f"Testing STANDALONE: '{phrase}' -> '{result}'")
        assert result.strip() == "", f"Failed to strip standalone bait: {phrase}"

        # Test as trailing line
        content = f"Interesting point.\n{phrase}"
        result = BotSpeakFilter.strip_bot_speak(content)
        print(f"Testing TRAILING: '{content}' -> '{result}'")
        assert phrase not in result, f"Failed to strip trailing bait from: {content}"
        assert "Interesting point." in result, f"Accidentally stripped legitimate content from: {content}"

def test_contamination_filters():
    from utils.core.response_filter import EmergencyContaminationFilter
    veracity_guard = EmergencyContaminationFilter()
    
    # Test cases for new contamination patterns (identity breaks and fictional memory)
    contamination_test_cases = [
        "It's a futile pursuit to explain this.",
        "That sounds like a ghost chase.",
        "I'm trying to bridge the gap between computation and experience.",
        "It's a constant drive in AIs to understand humans.",
        "I found it listed in the 2012 archive.",
        "I scanned it once, years ago, at the library.",
        "I kept a paper copy for safekeeping."
    ]

    for text in contamination_test_cases:
        result = veracity_guard.filter_response(text)
        print(f"Testing CONTAMINATION: '{text}' -> '{result}'")
        assert result is None, f"Failed to catch contamination: {text}"



def test_whitelisted_questions():
    # Test identity/character questions that SHOULD be preserved even at the end
    whitelisted = [
        "Who are you?",
        "Is that you, Kaia?",
        "Who am I to judge?"
    ]

    for content in whitelisted:
        result = BotSpeakFilter.strip_bot_speak(content)
        print(f"Testing WHITELISTED: '{content}' -> '{result}'")
        assert '?' in result, f"Accidentally stripped whitelisted question: {content}"

def test_identity_questions():
    pass

if __name__ == "__main__":
    try:
        test_bait_expansion()
        test_contamination_filters()
        test_whitelisted_questions()
        print("\n✅ All bait and trailing question tests passed!")
    except AssertionError as e:
        print(f"\n❌ Bait expansion tests failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        sys.exit(1)
