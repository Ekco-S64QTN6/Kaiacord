import pytest
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.social.kaia_social_responder import generate_quip

@pytest.mark.asyncio
async def test_generate_quip_unbound_local_error_fix():
    # Mock dependencies
    bot = AsyncMock()
    bot.ids = []
    
    ollama_client = AsyncMock()
    ollama_client.chat.return_value = {'message': {'content': 'test quip'}}
    
    run_rag_func = AsyncMock()
    rag_instance = MagicMock()
    
    # Mock channel
    channel = AsyncMock()
    channel.name = "general"
    channel.permissions_for.return_value.send_messages = True
    bot.get_channel.return_value = channel
    
    # Mock random.choice to avoid errors when lists are empty if logic fails
    # But wait, the logic we are testing is explicitly handling empty lists.
    
    # Mock config
    with patch('utils.infrastructure.system.yaml_config.config') as mock_config:
        mock_config.social_max_interval_hours = 1
        mock_config.idle_quip_timeout_minutes = 10
        mock_config.max_consecutive_quips = 5
        mock_config.blacklisted_channels = []
        mock_config.chat_model = "test-model"
        mock_config.bluesky_cross_post_quips = False
        mock_config.x_cross_post_quips = False
        
        # Mock bot state
        with patch('utils.infrastructure.system.bot_state.bot_state') as mock_state:
            mock_state.last_quip_time = 0.0
            mock_state.last_manual_quip_time = 0.0
            mock_state.last_interaction_time = 0.0
            mock_state.consecutive_quips = 0
            
            # Mock internal functions to return EMPTY lists
            with patch('utils.social.kaia_social_responder.get_random_dream_reflection', new_callable=AsyncMock) as mock_dreams, \
                 patch('utils.social.kaia_social_responder.get_random_memories', new_callable=AsyncMock) as mock_memories, \
                 patch('utils.social.kaia_social_responder.load_persona', return_value="system prompt"):
                
                mock_dreams.return_value = []
                mock_memories.return_value = []
                rag_instance.get_recent_highlights = AsyncMock(return_value=[])
                
                with patch('utils.social.kaia_social_responder.is_interesting_post', return_value=True), \
                     patch('utils.social.kaia_social_responder.is_too_vague', return_value=False):
                    
                    class MockCtx:
                        def __init__(self):
                            self.bot = bot
                            self.ollama_client = ollama_client
                            self.rag = rag_instance
                            self.bot_state = mock_state
                            self.config = mock_config
                    
                    ctx = MockCtx()
                    
                    # Execution
                    # This should NOT raise UnboundLocalError
                    await generate_quip(ctx, is_manual=True, target_channel=channel)


                
                # Verification
                # It should have called ollama (because of the fallback)
                assert ollama_client.chat.called
                
                # It should have sent a message
                assert channel.send.called

