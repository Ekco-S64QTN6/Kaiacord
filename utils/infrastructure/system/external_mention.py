"""
Shared logic for processing mentions from external platforms (Bluesky, Forum, etc.)
This module is isolated from the main bot object graph to prevent circular imports.
"""
from typing import Any
from utils.infrastructure.logging.kaia_logger import log_warning

async def process_external_mention(
    ctx: Any, content: str, author_name: str, author_id: Any, platform: str
):
    """
    Process mentions from external platforms.
    Constructs a MockMessage and routes it to the message processor.
    """
    from utils.infrastructure.system.messaging import MockMessage, MockUser, MockChannel
    
    # Create a compatible mock author
    mock_author = MockUser(
        id=author_id if isinstance(author_id, int) else (int(author_id) if str(author_id).isdigit() else 0),
        name=author_name,
        display_name=author_name
    )
    
    # Create a compatible mock channel/context
    mock_channel = MockChannel(id=hash(platform) % 10**10)
    
    # Construct the mock message
    mock_msg = MockMessage(
        content=content,
        author=mock_author,
        channel=mock_channel,
        platform=platform
    )
    
    if ctx.message_processor:
        # Directly process via the modular processor
        return await ctx.message_processor.process(mock_msg)
    else:
        log_warning(f"External mention from {platform} received but processor not ready.")
        return None
