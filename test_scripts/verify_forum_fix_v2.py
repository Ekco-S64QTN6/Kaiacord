import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

# Mock dependencies before importing the handler
sys.modules['utils.infrastructure.logging.kaia_logger'] = MagicMock()
sys.modules['utils.infrastructure.system.yaml_config'] = MagicMock()

from utils.commands.forum_handler import _handle_scrape

class MockTyping:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class TestForumScrape(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a class that looks like AppContext (no .get method)
        class MockAppContext:
            def __init__(self):
                self.config = MagicMock()
        
        self.ctx = MockAppContext()
        self.ctx.config.get.side_effect = lambda k, d=None: {
            'forum.max_posts_per_thread_scrape': 20,
            'forum.max_pages_per_thread_scrape': 6,
            'forum.full_scrape_max_pages': 50
        }.get(k, d)
        
        self.msg = AsyncMock()
        self.msg.channel.typing = MagicMock(return_value=MockTyping())
        self.msg.author.name = "ekco"
        self.msg.author.id = "123"
        
        self.client = AsyncMock()
        self.client.is_thread_update_needed = MagicMock()
        self.client.save_forum_listing = MagicMock()
        self.client.save_thread_scrape = MagicMock()
        self.client.update_forum_user_profiles = MagicMock()

    async def test_handle_scrape_pagination_and_skip(self):
        print("\nStarting test_handle_scrape_pagination_and_skip")
        self.msg.content = "!forum scrape page=1 limit=10"
        
        # Mock threads for page 1
        thread1 = MagicMock(thread_id=101, title="Thread 1", is_sticky=False, reply_count=5)
        thread2 = MagicMock(thread_id=102, title="Thread 2", is_sticky=False, reply_count=10)
        
        # Page 1 has no new content, Page 2 has new content
        self.client.scrape_forum_listing.side_effect = [
            [thread1, thread2], # Page 1
            [MagicMock(thread_id=103, title="Thread 3", is_sticky=False, reply_count=0)] # Page 2
        ]
        
        self.client.is_thread_update_needed.side_effect = [False, False, True]
        self.client.scrape_thread.return_value = {'thread_id': 103, 'posts': [{'post_number': 1, 'content': 'hello'}]}
        
        with patch('utils.social.kaia_forum.get_forum_client', return_value=self.client), \
             patch('utils.infrastructure.system.yaml_config.config', self.ctx.config), \
             patch('pathlib.Path.touch', MagicMock()):
            
            await _handle_scrape(self.ctx, self.msg)
            
            # Verify pagination moved to page 2 automatically
            self.assertEqual(self.client.scrape_forum_listing.call_count, 2)
            # Verify scrape_thread was called for thread 103 with full_scrape=False
            self.client.scrape_thread.assert_called_with(103, last_n_posts=20, full_scrape=False)

    async def test_handle_scrape_full_flag(self):
        print("\nStarting test_handle_scrape_full_flag")
        self.msg.content = "!forum scrape full=true"
        
        thread = MagicMock(thread_id=201, title="Large Thread", is_sticky=False, reply_count=500)
        self.client.scrape_forum_listing.return_value = [thread]
        self.client.is_thread_update_needed.return_value = True
        self.client.scrape_thread.return_value = {'thread_id': 201, 'posts': [{'post_number': 1, 'content': 'big'}]}
        
        with patch('utils.social.kaia_forum.get_forum_client', return_value=self.client), \
             patch('utils.infrastructure.system.yaml_config.config', self.ctx.config), \
             patch('pathlib.Path.touch', MagicMock()):
            
            await _handle_scrape(self.ctx, self.msg)
            # Verify full_scrape=True was passed
            self.client.scrape_thread.assert_called_with(201, last_n_posts=20, full_scrape=True)
            print("Full flag verified")

    async def test_app_context_no_get_fix(self):
        print("\nStarting test_app_context_no_get_fix")
        # ctx is already an object without .get() from setUp
        self.msg.content = "!forum scrape"
        self.client.scrape_forum_listing.return_value = []
        
        with patch('utils.social.kaia_forum.get_forum_client', return_value=self.client), \
             patch('utils.infrastructure.system.yaml_config.config', self.ctx.config):
            
            await _handle_scrape(self.ctx, self.msg)
            print("Success")

if __name__ == "__main__":
    unittest.main()
