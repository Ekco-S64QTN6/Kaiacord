import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

# Bypass config validation
os.environ["DISCORD_TOKEN"] = "dummy_token"
os.environ["BLUESKY_HANDLE"] = "dummy.handle"
os.environ["BLUESKY_APP_PASSWORD"] = "dummy_pass"

async def test_bypass_logic():
    print("Testing bypass logic...")
    
    # Mock config
    mock_config = MagicMock()
    mock_config.get.side_effect = lambda key, default=None: {
        'social.admin_handles': ["ekco-thewizard.bsky.social", "michaelschellhorn.link"],
        'bluesky.reply_to_mentions': True,
        'social.mention_lookback_hours': 3
    }.get(key, default)
    mock_config.bluesky_enabled = True
    
    # Test Thread Limit Bypass
    from utils.social.kaia_social_responder import _thread_counts, _replied_ids
    
    # Set thread count to limit
    test_uri = "at://did:plc:123/app.bsky.feed.post/456"
    _thread_counts[test_uri] = 3
    
    # Mock notification
    mock_notif = MagicMock()
    mock_notif.author.handle = "ekco-thewizard.bsky.social"
    mock_notif.uri = "at://did:plc:123/app.bsky.feed.post/789"
    mock_notif.reason = "mention"
    mock_notif.indexed_at = "2026-02-04T20:00:00Z"
    mock_notif.record.reply.root.uri = test_uri
    
    # Mock client and other dependencies
    with patch('utils.infrastructure.system.yaml_config.config', mock_config), \
         patch('utils.social.kaia_social_responder._bluesky_breaker') as mock_breaker, \
         patch('utils.social.kaia_bluesky.get_bluesky_client') as mock_get_client, \
         patch('utils.social.kaia_bluesky.is_bluesky_configured', return_value=True):
        
        mock_breaker.can_proceed.return_value = True
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        mock_notifs_obj = MagicMock()
        mock_notifs_obj.notifications = [mock_notif]
        # USE ASYNC MOCK FOR LIST NOTIFICATIONS
        future = asyncio.Future()
        future.set_result(mock_notifs_obj)
        mock_client.app.bsky.notification.list_notifications = MagicMock(return_value=future)
        
        from utils.social.kaia_social_responder import _get_bluesky_mentions
        mentions = await _get_bluesky_mentions()
        
        # Verify that the mention was NOT skipped despite thread count >= 3
        found = any(m['author'] == "ekco-thewizard.bsky.social" for m in mentions)
        if found:
            print("✅ SUCCESS: Admin handle bypassed thread limit.")
        else:
            print("❌ FAILURE: Admin handle was skipped by thread limit.")
            
    # Test Bot Loop Protection Bypass
    mock_mention = {
        'author': 'ekco-thewizard.bsky.social',
        'text': 'hello kaia bot',
        'id': 'bsky:123',
        'uri': 'at://123',
        'root_uri': MagicMock(uri=test_uri)
    }
    
    _thread_counts[test_uri] = 1 # Above bot threshold
    
    with patch('utils.infrastructure.system.yaml_config.config', mock_config), \
         patch('utils.social.kaia_social_responder._get_bluesky_mentions') as mock_get_mentions, \
         patch('utils.social.kaia_social_responder._generate_response') as mock_gen, \
         patch('utils.social.kaia_social_responder._reply_to_bluesky') as mock_reply:
             
        mock_get_mentions.return_value = [mock_mention]
        mock_gen.return_value = "hi admin"
        mock_reply.return_value = True
        
        from utils.social.kaia_social_responder import check_and_reply_mentions
        await check_and_reply_mentions(lambda x: None)
        
        if mock_reply.called:
            print("✅ SUCCESS: Admin handle bypassed bot loop protection.")
        else:
            print("❌ FAILURE: Admin handle was skipped by bot loop protection.")

if __name__ == "__main__":
    asyncio.run(test_bypass_logic())
