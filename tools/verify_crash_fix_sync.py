
from utils.core.response_filter import BotSpeakFilter

def test_fix():
    print("Testing BotSpeakFilter fix...")
    
    text = "This is a test message. "
    
    # Test 1: Class method usage (triggered the crash in message_processor.py)
    try:
        res = BotSpeakFilter.strip_bot_speak(text)
        print(f"✅ Class method call successful: '{res}'")
    except Exception as e:
        print(f"❌ Class method call FAILED: {e}")

    # Test 2: Instance method usage (used in kaia_social_responder.py)
    try:
        harden = BotSpeakFilter()
        res = harden.harden(text)
        print(f"✅ Instance method call successful: '{res}'")
    except Exception as e:
        print(f"❌ Instance method call FAILED: {e}")

if __name__ == "__main__":
    test_fix()
