
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from utils.social.kaia_social_responder import _split_into_thread_posts

def test_split():
    print("Testing _split_into_thread_posts logic...")
    
    # Test 1: Short text - Should be 1 post
    short_text = "This is a short post. It fits easily within the limit."
    posts = _split_into_thread_posts(short_text)
    assert len(posts) == 1, f"Expected 1 post, got {len(posts)}"
    assert posts[0] == short_text
    print("PASS: Short text")
    
    # Test 2: Long text with sentence boundary - Should split cleanly
    # Create a string > 280 chars but with a clear sentence break near end
    part1 = "A" * 250 + ". "
    part2 = "B" * 50 + "."
    long_text = part1 + part2
    posts = _split_into_thread_posts(long_text)
    assert len(posts) == 2, f"Expected 2 posts, got {len(posts)}"
    assert posts[0] == part1.strip(), f"Expected split at '{part1.strip()}', got '{posts[0]}'"
    assert posts[1] == part2
    print("PASS: Clean sentence split")
    
    # Test 3: Long text with clause boundary (semicolon)
    # Create a string where sentence break is too far back, but semicolon is available
    # 280 chars total limit.
    # We want a split point in the last 60 chars (220-280)
    # Put a semicolon at 260.
    prefix = "C" * 260
    suffix = "; " + "D" * 50
    long_text_clause = prefix + suffix
    posts = _split_into_thread_posts(long_text_clause)
    # It might split at the semicolon or hard split if it can't find anything better?
    # Actually wait. My logic:
    # 1. Look for sentence end in last 60 chars.
    # 2. Look for clause delimiters in last 60 chars.
    # 3. Look for space.
    # 4. Hard cut.
    
    # Let's test specific logic.
    # "A" * 280 -> hard cut
    # "A" * 270 + ". " + "B" * 10
    
    text_hard = "E" * 300
    posts = _split_into_thread_posts(text_hard)
    assert len(posts) == 2
    assert len(posts[0]) == 280
    print("PASS: Hard cut fallback")
    
    # Test 4: Space fallback
    prefix = "F" * 270 + " " + "G" * 50
    posts = _split_into_thread_posts(prefix)
    assert len(posts) == 2
    # Should split at the space
    assert len(posts[0]) == 270
    print("PASS: Space fallback")

    # Test 5: Real world simulation
    real_text = """This is a simulated long response from Kaia. It talks about systems and user interactions. 
It goes on for quite a while, explaining complex topics about memory and caching. 
The idea is that we shouldn't anthropomorphize storage layers because it leads to bad design. 
Instead, we should focus on reliability and clear interfaces. 
Debugging becomes a nightmare when you try to make caches 'smart'. 
Just keep it simple."""
    # This is short enough for 2 posts maybe? 
    # Length: ~350 chars.
    posts = _split_into_thread_posts(real_text)
    print(f"Real text split into {len(posts)} posts:")
    for i, p in enumerate(posts):
        print(f"--- Post {i+1} ({len(p)} chars) ---\n{p}\n")
    
    assert len(posts) >= 2
    
test_split()
