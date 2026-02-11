import sys
import os
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))


from utils.infrastructure.system.yaml_config import config
from utils.infrastructure.system.bot_state import bot_state
from utils.social.kaia_social_responder import generate_quip

async def test_social_frequency():
    print("Testing Social Frequency Logic...")
    
    # Mock dependencies
    bot = MagicMock()
    ollama_client = AsyncMock()
    ollama_client.chat.return_value = {'message': {'content': 'test quip'}}
    
    # CASE 1: Recent interaction, recent quip -> SHOULD SKIP
    print("\nCase 1: Recent interaction, recent quip")
    bot_state.last_interaction_time = time.time()
    bot_state.last_quip_time = time.time()
    bot_state.consecutive_quips = 0
    
    class MockCtx:
        def __init__(self, bot, ollama, rag, state, config):
            self.bot = bot
            self.ollama_client = ollama
            self.rag = rag
            self.bot_state = state
            self.config = config

    ctx = MockCtx(bot, ollama_client, MagicMock(), bot_state, config)
    
    await generate_quip(ctx, is_manual=False)
    # Validation: We can't easily spy on internal logic without more mocking, 
    # but we can check if consecutive_quips incremented (it shouldn't)
    if bot_state.consecutive_quips == 0:
        print("PASS: Skipped as expected.")
    else:
        print(f"FAIL: Quip generated unexpectedly. Consec={bot_state.consecutive_quips}")

    # CASE 2: Recent interaction, OLD quip (> max interval) -> SHOULD POST
    print("\nCase 2: Recent interaction, OLD quip (> max interval)")
    bot_state.last_interaction_time = time.time() # Active right now
    # Force last quip to be 3 hours ago (default max is 2h)
    bot_state.last_quip_time = time.time() - (3.5 * 3600) 
    bot_state.consecutive_quips = 0
    
    # Mock channel to avoid errors
    channel = AsyncMock()
    channel.name = "general"
    bot.get_channel.return_value = channel
    bot.guilds = [MagicMock(text_channels=[channel])]
    channel.permissions_for.return_value.send_messages = True
    
    ctx = MockCtx(bot, ollama_client, MagicMock(), bot_state, config)
    await generate_quip(ctx, is_manual=False)

    
    if bot_state.consecutive_quips == 1:
        print("PASS: Forced post generated.")
    else:
        print(f"FAIL: Forced post skipped. Consec={bot_state.consecutive_quips}")

if __name__ == "__main__":
    asyncio.run(test_social_frequency())
