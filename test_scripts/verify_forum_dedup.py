
import sys
import os
import asyncio
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append('/home/ekco/github/Kaiacord')

# Mock what we need
from utils.social.kaia_forum import ForumClient, PostInfo

async def verify_deduplication():
    client = ForumClient("https://www.project1999.com/forums", 19)
    
    # --- 1. Verify save_thread_scrape deduplication ---
    test_thread_id = 999999
    test_data = {
        'thread_id': test_thread_id,
        'title': "Test Thread for Deduplication",
        'posts': [
            PostInfo(post_id=1, author="Tester", user_id=101, content="Message 1", timestamp="Today", post_number=1),
            PostInfo(post_id=2, author="Tester", user_id=101, content="Message 2", timestamp="Today", post_number=2),
        ],
        'page': 1
    }
    
    # First save should return True
    changed1 = client.save_thread_scrape(test_data)
    print(f"First save (new thread): {changed1}")
    
    # Second save with same data should return False
    changed2 = client.save_thread_scrape(test_data)
    print(f"Second save (same data): {changed2}")
    
    # Third save with extra post should return True
    test_data['posts'].append(PostInfo(post_id=3, author="Tester", user_id=101, content="Message 3", timestamp="Today", post_number=3))
    changed3 = client.save_thread_scrape(test_data)
    print(f"Third save (one new post): {changed3}")
    
    # --- 2. Verify update_forum_user_profiles deduplication ---
    test_posts = [
        PostInfo(post_id=10, author="TestUser", user_id=202, content="Hello World", timestamp="Today", post_number=1)
    ]
    
    user_key = "forum_TestUser_202"
    user_dir = client.USER_LOGS_DIR / user_key
    if user_dir.exists():
        import shutil
        shutil.rmtree(user_dir)
        
    # First update should create file and add post
    client.update_forum_user_profiles(test_posts)
    today_str = datetime.now().strftime("%Y%m%d")
    interaction_file = user_dir / f"interactions_{today_str}.md"
    
    content1 = interaction_file.read_text()
    print(f"Interaction file created with {content1.count('[Post ID: 10]')} instance of Post ID 10")
    
    # Second update with same post should NOT add it again
    client.update_forum_user_profiles(test_posts)
    content2 = interaction_file.read_text()
    print(f"After second update, file has {content2.count('[Post ID: 10]')} instance of Post ID 10")
    
    # Third update with NEW post should add it
    test_posts.append(PostInfo(post_id=11, author="TestUser", user_id=202, content="Another Post", timestamp="Today", post_number=2))
    client.update_forum_user_profiles(test_posts)
    content3 = interaction_file.read_text()
    print(f"After third update (with new post), file has {content3.count('[Post ID: 10]')} ID 10 and {content3.count('[Post ID: 11]')} ID 11")

    # Cleanup test artifacts
    for f in client.KNOWLEDGE_DIR.glob(f"thread_{test_thread_id}_*.md"):
        f.unlink()
    if user_dir.exists():
        import shutil
        shutil.rmtree(user_dir)

    if changed1 and not changed2 and changed3 and content2.count('[Post ID: 10]') == 1 and content3.count('[Post ID: 11]') == 1:
        print("\nSUCCESS: All deduplication tests passed!")
    else:
        print("\nFAILURE: One or more tests failed.")

if __name__ == "__main__":
    asyncio.run(verify_deduplication())
