from utils.core.response_filter import BotSpeakFilter

def test_harden():
    test_cases = [
        ("hello. (a long pause. a faint clicking sound, almost imperceptrible.) how are you?", "hello. how are you?"),
        ("i *scratches head* don't really know about that.", "i don't really know about that."),
        ("nested (actions (within actions)) should be fine.", "nested should be fine."),
        ("empty lines: \n\n(action)\n\ntext", "empty lines:\n\ntext"),
        ("multiple spaces: (action)  between text", "multiple spaces: between text"),
    ]
    
    for input_text, expected in test_cases:
        result = BotSpeakFilter.harden(input_text)
        print(f"Input: {input_text!r}")
        print(f"Result: {result!r}")
        print(f"Match: {result == expected}")
        print("-" * 20)

if __name__ == "__main__":
    test_harden()
