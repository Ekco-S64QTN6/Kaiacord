import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

import pytest
import discord
from unittest.mock import MagicMock, patch, AsyncMock
from utils.core.message_processor import MessageProcessor

@pytest.fixture
def mock_processor():
    ctx_mock = MagicMock()
    bot_mock = MagicMock()
    bot_user = MagicMock()
    bot_user.id = 999999
    bot_user.display_name = "Kaia"
    bot_user.name = "Kaia"
    bot_mock.user = bot_user
    ctx_mock.bot = bot_mock
    
    config_mock = MagicMock()
    config_mock.ignored_users = []
    config_mock.blacklisted_channels = []
    config_mock.whitelisted_channels = []
    config_mock.url_fetch_timeout = 5
    config_mock.get.return_value = "aethelgard"
    ctx_mock.config = config_mock
    
    bot_state_mock = MagicMock()
    bot_state_mock.boot_complete = True
    bot_state_mock.channel_memory = {}
    ctx_mock.bot_state = bot_state_mock
    
    processor = MessageProcessor(
        ctx=ctx_mock,
        response_optimizer=MagicMock(),
        context_optimizer=MagicMock(),
        relevance_feedback=MagicMock(),
        news_enhancer=MagicMock(),
        rag_enhancer=MagicMock()
    )
    processor.bot = bot_mock
    processor.rate_limiter = MagicMock()
    processor.rate_limiter.is_allowed.return_value = True
    processor.shutdown_manager = MagicMock()
    processor.shutdown_manager.shutting_down = False
    processor.bot_state = bot_state_mock
    processor.context_enricher = MagicMock()
    processor.context_enricher.enrich_content = AsyncMock(side_effect=lambda msg: msg.content)
    processor.stats_tracker = MagicMock()
    processor._run_intelligence_pipeline = AsyncMock()
    return processor

@pytest.mark.asyncio
async def test_dm_triggers_without_kaia_mention(mock_processor):
    """Verify that in DMs (guild is None / DMChannel), any message triggers the bot."""
    dm_channel = MagicMock(spec=discord.DMChannel)
    dm_channel.id = 123456
    dm_channel.type = discord.ChannelType.private

    user = MagicMock(spec=discord.User)
    user.id = 111111
    user.name = "Alice"
    user.display_name = "Alice"
    user.bot = False

    msg = MagicMock(spec=discord.Message)
    msg.platform = "discord"
    msg.author = user
    msg.guild = None
    msg.channel = dm_channel
    msg.mentions = []
    msg.role_mentions = []
    msg.content = "Can you help me write a python script?"

    await mock_processor._process_internal(msg)

    # Pipeline should have been called
    assert mock_processor._run_intelligence_pipeline.called
    called_ctx = mock_processor._run_intelligence_pipeline.call_args[0][0]
    assert called_ctx.is_dm is True
    assert called_ctx.is_mention is True
    assert called_ctx.sanitized_content == "Can you help me write a python script?"

@pytest.mark.asyncio
async def test_guild_message_without_kaia_is_ignored(mock_processor):
    """Verify that in a guild channel, a message without Kaia or a mention is ignored."""
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 654321
    channel.name = "general-discussion"
    channel.parent = None

    user = MagicMock(spec=discord.Member)
    user.id = 222222
    user.name = "Bob"
    user.display_name = "Bob"
    user.bot = False

    msg = MagicMock(spec=discord.Message)
    msg.platform = "discord"
    msg.author = user
    msg.guild = guild
    msg.channel = channel
    msg.mentions = []
    msg.role_mentions = []
    msg.content = "Does anyone know what time it is?"

    await mock_processor._process_internal(msg)

    # Intelligence pipeline should NOT be called
    assert not mock_processor._run_intelligence_pipeline.called

@pytest.mark.asyncio
async def test_guild_message_with_kaia_triggers(mock_processor):
    """Verify that in a guild channel, a message mentioning Kaia triggers the bot."""
    guild = MagicMock(spec=discord.Guild)
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 654321
    channel.name = "general-discussion"
    channel.parent = None

    user = MagicMock(spec=discord.Member)
    user.id = 222222
    user.name = "Bob"
    user.display_name = "Bob"
    user.bot = False

    msg = MagicMock(spec=discord.Message)
    msg.platform = "discord"
    msg.author = user
    msg.guild = guild
    msg.channel = channel
    msg.mentions = []
    msg.role_mentions = []
    msg.content = "hey kaia, what time is it?"

    await mock_processor._process_internal(msg)

    # Intelligence pipeline should be called
    assert mock_processor._run_intelligence_pipeline.called
    called_ctx = mock_processor._run_intelligence_pipeline.call_args[0][0]
    assert called_ctx.is_dm is False
    assert called_ctx.is_mention is True
