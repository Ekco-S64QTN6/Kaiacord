
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from utils.social.kaia_social_responder import _split_into_thread_posts
from utils.social.kaia_bluesky import _split_into_thread

def test_limits():
    print("🧪 Testing Thread Capping Logic...")
    
    # Create a very long text (~2000 chars) that would normally be many posts
    long_text = ("This is a very long sentence that will be repeated to ensure we have enough content to exceed the default limits. " * 20)
    print(f"Input length: {len(long_text)} chars")
    
    # Test Responder splitting (default limit 5)
    print("\n--- Testing Social Responder Splitting ---")
    posts_5 = _split_into_thread_posts(long_text)
    print(f"Posts with default limit (5): {len(posts_5)}")
    assert len(posts_5) == 5, f"Expected 5 posts, got {len(posts_5)}"
    
    posts_3 = _split_into_thread_posts(long_text, max_posts=3)
    print(f"Posts with explicit limit (3): {len(posts_3)}")
    assert len(posts_3) == 3, f"Expected 3 posts, got {len(posts_3)}"
    
    # Test Bluesky direct splitting (default limit 5)
    print("\n--- Testing Bluesky Client Splitting ---")
    bsky_posts_5 = _split_into_thread(long_text)
    print(f"Bluesky posts with default limit (5): {len(bsky_posts_5)}")
    assert len(bsky_posts_5) == 5, f"Expected 5 posts, got {len(bsky_posts_5)}"
    
    bsky_posts_2 = _split_into_thread(long_text, max_posts=2)
    print(f"Bluesky posts with explicit limit (2): {len(bsky_posts_2)}")
    assert len(bsky_posts_2) == 2, f"Expected 2 posts, got {len(bsky_posts_2)}"
    
    print("\n✅ Thread capping verification successful!")

if __name__ == "__main__":
    try:
        test_limits()
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        sys.exit(1)
