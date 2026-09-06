"""
Test: Bluesky Integration
=========================

Unit tests for the Bluesky posting module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from utils.infrastructure.system.yaml_config import config


class TestBlueskyModule:
    """Tests for kaia_bluesky.py"""
    
    def test_is_bluesky_configured_without_env(self):
        """Test that unconfigured Bluesky returns False"""
        with patch.dict('os.environ', {'DISCORD_TOKEN': 'dummy'}, clear=True):
            from utils.social.kaia_bluesky import is_bluesky_configured
            assert is_bluesky_configured() is False
    
    def test_is_bluesky_configured_with_env(self):
        """Test that configured Bluesky returns True.

        is_bluesky_configured() checks BOTH credentials and the bluesky.enabled flag, so
        this test pins the flag on rather than inheriting the deployment config. The live
        config has Bluesky disabled (the account was deleted in Sept 2026); that is a
        deployment choice and must not decide whether credential detection is covered.
        """
        with patch.dict('os.environ', {
            'DISCORD_TOKEN': 'dummy',
            'BLUESKY_HANDLE': 'test.bsky.social',
            'BLUESKY_APP_PASSWORD': 'test-password'
        }), patch.object(type(config), 'bluesky_enabled', property(lambda self: True)):
            from utils.social.kaia_bluesky import is_bluesky_configured
            # Need to reimport to pick up env change
            import importlib
            import utils.social.kaia_bluesky as bsky_module
            importlib.reload(bsky_module)
            assert bsky_module.is_bluesky_configured() is True

    def test_is_bluesky_configured_respects_disabled_flag(self):
        """Credentials alone are not enough: the enabled flag gates the integration.

        Regression guard for the Sept 2026 shutdown — with the account deleted, leaving
        credentials in .env must not be enough to bring the integration back to life.
        """
        with patch.dict('os.environ', {
            'DISCORD_TOKEN': 'dummy',
            'BLUESKY_HANDLE': 'test.bsky.social',
            'BLUESKY_APP_PASSWORD': 'test-password'
        }), patch.object(type(config), 'bluesky_enabled', property(lambda self: False)):
            import importlib
            import utils.social.kaia_bluesky as bsky_module
            importlib.reload(bsky_module)
            assert bsky_module.is_bluesky_configured() is False
    
    @pytest.mark.asyncio
    async def test_post_to_bluesky_without_client(self):
        """Test posting fails gracefully without credentials"""
        with patch.dict('os.environ', {'DISCORD_TOKEN': 'dummy'}, clear=True):
            from utils.social.kaia_bluesky import post_to_bluesky
            import importlib
            import utils.social.kaia_bluesky as bsky_module
            importlib.reload(bsky_module)
            
            # Clear the client
            bsky_module._client = None
            
            success, result = await bsky_module.post_to_bluesky("Test post")
            assert success is False
            assert "not available" in result.lower() or "not configured" in result.lower()
    
    @pytest.mark.asyncio
    async def test_post_truncation(self):
        """Test that long posts are truncated to 300 chars"""
        long_text = "word " * 80
        
        with patch.dict('os.environ', {
            'BLUESKY_HANDLE': 'test.bsky.social',
            'BLUESKY_APP_PASSWORD': 'test-password'
        }):
            from utils.social.kaia_bluesky import post_to_bluesky
            
            # Mock the client
            mock_client = AsyncMock()
            mock_client.send_post = AsyncMock(return_value=Mock(uri="at://test/post/123"))
            
            with patch('utils.social.kaia_bluesky.get_bluesky_client', return_value=mock_client):
                success, result = await post_to_bluesky(long_text)
                
                if success:
                    # Check that the posted text was truncated
                    call_args = mock_client.send_post.call_args
                    posted_text = call_args[0][0] if call_args[0] else call_args[1].get('text', '')
                    assert len(posted_text) <= 300
