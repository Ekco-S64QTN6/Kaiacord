"""
Shared logic for processing mentions from external platforms (Bluesky, Forum, etc.)
This module is isolated from the main bot object graph to prevent circular imports.
"""
import zlib
from typing import Any
from utils.infrastructure.logging.kaia_logger import log_warning

def conversation_channel_id(platform: str, conversation_key: Any = None) -> int:
    """The channel id a given external conversation maps to.

    Exposed so callers can seed that channel's history before handing the
    message over — a forum thread's posts are its conversation, and Discord
    gets its channel history the same way.
    """
    key = f"{platform}:{conversation_key}" if conversation_key is not None else platform
    return zlib.crc32(key.encode("utf-8")) % 10**10


async def process_external_mention(
    ctx: Any, content: str, author_name: str, author_id: Any, platform: str,
    conversation_key: Any = None, no_persist: bool = False,
    image_urls=None,
):
    """
    Process mentions from external platforms.
    Constructs a MockMessage and routes it to the message processor.

    `conversation_key` distinguishes separate conversations on one platform —
    a forum thread id, say — so that each keeps its own channel memory instead
    of every thread on the site sharing one history.
    """
    from utils.infrastructure.system.messaging import (
        MockMessage, MockUser, MockChannel, MockAttachment)
    
    # Create a compatible mock author
    mock_author = MockUser(
        id=author_id if isinstance(author_id, int) else (int(author_id) if str(author_id).isdigit() else 0),
        name=author_name,
        display_name=author_name
    )
    
    # Stable across restarts. `hash()` on a str is salted per process
    # (PYTHONHASHSEED), and this id keys channel memory — so a salted hash
    # discards the conversation history of every external platform on each
    # boot.
    mock_channel = MockChannel(id=conversation_channel_id(platform, conversation_key))
    
    # Construct the mock message
    # Pictures in the post reach the vision model through the same attachment
    # path Discord uses. Without this the forum drafted replies to images it
    # could not see — "those symbols again? what are you trying to do?" in answer
    # to a post that was a photograph.
    mock_msg = MockMessage(
        content=content,
        author=mock_author,
        channel=mock_channel,
        platform=platform,
        no_persist=no_persist,
        attachments=[MockAttachment(u) for u in (image_urls or [])],
    )
    
    if not ctx.message_processor:
        log_warning(f"External mention from {platform} received but processor not ready.")
        return None

    # The processor delivers by calling channel.send(), and returns None. Callers
    # here have no channel to deliver to — they need the text back to post it
    # themselves — so read it off the mock channel. Without this the forum
    # auto-reply path received None from every call and could never post.
    await ctx.message_processor.process(mock_msg)
    if not mock_channel.sent_messages:
        return None
    return "\n".join(m for m in mock_channel.sent_messages if m).strip() or None
