import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from utils.social.kaia_forum import ThreadInfo, PostInfo, get_forum_client
from utils.infrastructure.logging.kaia_logger import log_info

async def verify_fixes():
    print("--- Verifying Forum Scraper Fixes ---")
    
    client = await get_forum_client()
    
    # 1. Verify fix for AttributeError: 'dict' object has no attribute 'author'
    print("\n[1] Testing update_forum_user_profiles with dict input...")
    mock_posts = [
        {
            'post_id': '12345',
            'author': 'TestUser',
            'user_id': 67890,
            'content': 'This is a test post from a dict.',
            'timestamp': '2026-02-13 12:00:00'
        }
    ]
    
    try:
        # This shouldn't raise AttributeError now
        client.update_forum_user_profiles(mock_posts)
        print("✅ SUCCESS: update_forum_user_profiles handled dict input.")
    except AttributeError as e:
        print(f"❌ FAILURE: update_forum_user_profiles still raises AttributeError: {e}")
    except Exception as e:
        print(f"❌ FAILURE: Unexpected error: {e}")

    # 2. Verify recursive thread check
    print("\n[2] Testing recursive thread update check...")
    # Create a mock thread file in a subdirectory
    tech_dir = Path("./knowledge_base/forum_posts/technical")
    tech_dir.mkdir(parents=True, exist_ok=True)
    mock_thread_file = tech_dir / "thread_999999_mock-thread.md"
    mock_thread_file.write_text("---\nthread_id: 999999\npost_count: 5\n---\n# Mock")
    
    # Check if update is needed for thread 999999 with 4 replies (total 5 posts)
    # It should return False because it finds the file in the technical/ folder
    update_needed = client.is_thread_update_needed(999999, 4)
    if not update_needed:
        print("✅ SUCCESS: is_thread_update_needed found file in technical/ subdirectory.")
    else:
        print("❌ FAILURE: is_thread_update_needed failed to find file in technical/ subdirectory.")
    
    # Clean up mock file
    mock_thread_file.unlink()

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify_fixes())
