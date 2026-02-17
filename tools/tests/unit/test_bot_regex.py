import re

def test_bot_detection():
    bot_keywords = ["bot", "agent", "automated"]
    
    test_cases = [
        ("lilyevesinclair.bsky.social", False),
        ("kaia_bot", True),
        ("bot_kaia", True),
        ("ai_agent", True),
        ("lily.ai.helper", True),
        ("sinclair_ai", True),
        ("main_ai_bot", True),
        ("dain", False),
        ("clair", False),
        ("brain", False),
    ]
    
    for author, expected in test_cases:
        author_l = author.lower()
        is_bot = False
        
        # Refined logic from kaia_social_responder.py
        if any(re.search(fr"(^|[\._-]){k}([\._-]|$)", author_l) for k in bot_keywords):
            is_bot = True
        elif re.search(r"(^|[\._-])ai([\._-]|$)", author_l) or author_l.endswith("ai"):
            is_bot = True
            
        print(f"Author: {author:30} | Bot: {is_bot:5} | Expected: {expected:5} | Match: {is_bot == expected}")

if __name__ == "__main__":
    test_bot_detection()
