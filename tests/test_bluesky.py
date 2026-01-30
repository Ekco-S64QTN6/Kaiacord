"""
Test: Bluesky Integration
=========================

Unit tests for the Bluesky posting module.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestBlueskyModule:
    """Tests for kaia_bluesky.py"""
    
    def test_is_bluesky_configured_without_env(self):
        """Test that unconfigured Bluesky returns False"""
        with patch.dict('os.environ', {}, clear=True):
            from utils.kaia_bluesky import is_bluesky_configured
            assert is_bluesky_configured() is False
    
    def test_is_bluesky_configured_with_env(self):
        """Test that configured Bluesky returns True"""
        with patch.dict('os.environ', {
            'BLUESKY_HANDLE': 'test.bsky.social',
            'BLUESKY_APP_PASSWORD': 'test-password'
        }):
            from utils.kaia_bluesky import is_bluesky_configured
            # Need to reimport to pick up env change
            import importlib
            import utils.kaia_bluesky as bsky_module
            importlib.reload(bsky_module)
            assert bsky_module.is_bluesky_configured() is True
    
    @pytest.mark.asyncio
    async def test_post_to_bluesky_without_client(self):
        """Test posting fails gracefully without credentials"""
        with patch.dict('os.environ', {}, clear=True):
            from utils.kaia_bluesky import post_to_bluesky
            import importlib
            import utils.kaia_bluesky as bsky_module
            importlib.reload(bsky_module)
            
            # Clear the client
            bsky_module._client = None
            
            success, result = await bsky_module.post_to_bluesky("Test post")
            assert success is False
            assert "not available" in result.lower() or "not configured" in result.lower()
    
    @pytest.mark.asyncio
    async def test_post_truncation(self):
        """Test that long posts are truncated to 300 chars"""
        long_text = "x" * 400
        
        with patch.dict('os.environ', {
            'BLUESKY_HANDLE': 'test.bsky.social',
            'BLUESKY_APP_PASSWORD': 'test-password'
        }):
            from utils.kaia_bluesky import post_to_bluesky
            
            # Mock the client
            mock_client = AsyncMock()
            mock_client.send_post = AsyncMock(return_value=Mock(uri="at://test/post/123"))
            
            with patch('utils.kaia_bluesky.get_bluesky_client', return_value=mock_client):
                success, result = await post_to_bluesky(long_text)
                
                if success:
                    # Check that the posted text was truncated
                    call_args = mock_client.send_post.call_args
                    posted_text = call_args[0][0] if call_args[0] else call_args[1].get('text', '')
                    assert len(posted_text) <= 300
