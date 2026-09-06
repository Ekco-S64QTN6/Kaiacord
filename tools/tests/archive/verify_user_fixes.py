import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
import sys
import os

# Mock dependencies before importing the client
sys.path.append('/home/ekco/github/Kaiacord')

from utils.social.kaia_forum import ForumClient, PostInfo, ThreadInfo

class TestForumUserFixes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = ForumClient("http://example.com", 1)
        self.client.USER_LOGS_DIR = Path("./test_user_logs")
        self.client.USER_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Mock session
        self.mock_session = MagicMock()
        self.mock_session.get = AsyncMock()
        self.client._session = self.mock_session
        self.client._logged_in = True

    def tearDown(self):
        import shutil
        if self.client.USER_LOGS_DIR.exists():
            shutil.rmtree(self.client.USER_LOGS_DIR)

    async def test_profile_metadata_contamination_fix(self):
        """Test that profile metadata is ONLY applied to the matching user."""
        posts = [
            PostInfo(author="UserA", user_id=1, post_id=101, content="Post A"),
            PostInfo(author="UserB", user_id=2, post_id=102, content="Post B"),
        ]
        
        # Metadata specifically for UserA
        metadata = {
            'username': 'UserA',
            'user_id': 1,
            'rank': 'Elite',
            'total_posts': 1000,
            'join_date': '2010-01-01'
        }
        
        self.client.update_forum_user_profiles(posts, metadata)
        
        # Check UserA profile
        profile_a = (self.client.USER_LOGS_DIR / "forum_UserA_1" / "user_profile.md").read_text()
        self.assertIn("rank of 'Elite'", profile_a)
        self.assertIn("1000 times", profile_a)
        
        # Check UserB profile - should NOT have UserA's metadata
        profile_b = (self.client.USER_LOGS_DIR / "forum_UserB_2" / "user_profile.md").read_text()
        self.assertIn("rank of 'forum user'", profile_b)
        self.assertIn("posted ? times", profile_b)
        self.assertIn("joining Norrath's digital extension in ?", profile_b)

    @patch('utils.infrastructure.system.yaml_config.config')
    async def test_scrape_active_users_config_limit(self, mock_config):
        """Test that scrape_active_users respects the config limit."""
        mock_config.get.side_effect = lambda k, d=None: 2 if k == 'forum.max_active_users_scrape' else d
        
        threads = []
        posts = [
            PostInfo(author="User1", user_id=1, post_id=1, content="..."),
            PostInfo(author="User2", user_id=2, post_id=2, content="..."),
            PostInfo(author="User3", user_id=3, post_id=3, content="..."),
            PostInfo(author="User4", user_id=4, post_id=4, content="..."),
        ]
        
        self.client.scrape_user_profile = AsyncMock(return_value={'total_posts': 5})
        self.client.scrape_user_post_history = AsyncMock(return_value=[])
        self.client.scrape_user_threads_started = AsyncMock(return_value=[])
        
        count = await self.client.scrape_active_users(threads, posts)
        
        # Should stop after 2 users because of the config limit
        self.assertEqual(count, 2)
        self.assertEqual(self.client.scrape_user_profile.call_count, 2)

if __name__ == "__main__":
    asyncio.run(unittest.main())
