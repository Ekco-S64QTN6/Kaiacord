import sys
import os
sys.path.append(os.getcwd())

from utils.core.response_filter import BotSpeakFilter, EmergencyContaminationFilter

def test_filter():
    bot_filter = BotSpeakFilter()
    veracity_guard = EmergencyContaminationFilter()
    
    # Test case 1: Bot-speak (should strip SILENTLY)
    bot_speak_text = "look, i can help with that.\nAs an AI, I am programmed to be helpful."
    result = bot_filter.harden(bot_speak_text)
    print(f"Test 1 (Bot-Speak Strip):\nResult: '{result}'")
    assert "look, i can help" in result
    assert "As an AI" not in result
    
    # Test case 2: Natural conversation (should PASS)
    bait_text = "sixty seconds is better. anything else? how about you?"
    result = bot_filter.harden(bait_text)
    print(f"Test 2 (Natural Conversation Pass):\nResult: '{result}'")
    assert result == bait_text # NO STRIPPING
    
    # Test case 3: News Hallucination (should return None for RETRY)
    fictional_text = "According to a news report i saw, Steve Jobs has returned to lead Apple."
    result = veracity_guard.filter_response(fictional_text)
    print(f"Test 3 (Veracity Guard Retry Signal):\nResult: '{result}'")
    assert result is None
    
    # Test case 4: Mixed Hallucination (Majority fiction, should return None)
    mixed_text = "Yeah, i heard about that.\nBreaking news: Steve Jobs co-authored a paper on Quantum Consciousness with Einstein."
    result = veracity_guard.filter_response(mixed_text)
    print(f"Test 4 (Mixed Hallucination Retry Signal):\nResult: '{result}'")
    assert result is None

if __name__ == "__main__":
    test_filter()
    print("\nAll tests passed!")
