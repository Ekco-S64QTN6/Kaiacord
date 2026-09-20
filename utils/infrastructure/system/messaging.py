import asyncio
from typing import List
from utils.infrastructure.logging.kaia_logger import log_warning, log_error


def _split_text_into_safe_chunks(text: str, limit: int) -> List[str]:
    """
    Split text into chunks guaranteed to be <= limit characters each.
    Splits by newlines where possible, then words, then hard char slices.
    """
    if not text:
        return []
    
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    lines = text.split('\n')
    current_chunk = ""

    for line in lines:
        # If single line itself exceeds limit, split it by words or characters
        if len(line) > limit:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Sub-split long line
            words = line.split(' ')
            sub_chunk = ""
            for word in words:
                if len(word) > limit:
                    if sub_chunk.strip():
                        chunks.append(sub_chunk.strip())
                        sub_chunk = ""
                    for i in range(0, len(word), limit):
                        slice_str = word[i:i+limit]
                        if slice_str:
                            chunks.append(slice_str)
                elif len(sub_chunk) + len(word) + 1 > limit:
                    if sub_chunk.strip():
                        chunks.append(sub_chunk.strip())
                    sub_chunk = word + ' '
                else:
                    sub_chunk += word + ' '
            if sub_chunk.strip():
                chunks.append(sub_chunk.strip())
            continue

        if len(current_chunk) + len(line) + 1 > limit:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c.strip()]


async def send_kaia_response(channel, text, use_code_block=False):
    """Helper to split long messages and optionally wrap them in Kaia's style"""
    if not text or not str(text).strip():
        log_warning("send_kaia_response called with empty text. Skipping.")
        return
        
    text_clean = str(text).strip()
    
    # Discord limit is 2000. 
    # Use 1980 for code blocks to leave room for ```\n and \n```
    # Use 1990 for plain text for a small safety margin.
    limit = 1980 if use_code_block else 1990
    
    chunks = _split_text_into_safe_chunks(text_clean, limit)
    if not chunks:
        return

    for chunk in chunks:
        if not chunk:
            continue
        try:
            if use_code_block:
                payload = f"```\n{chunk}\n```"
                if len(payload) > 2000:
                    payload = f"```\n{chunk[:1980]}\n```"
                await channel.send(payload)
            else:
                await channel.send(chunk[:1990])
        except Exception as e:
            log_error(f"Failed to send Discord message payload (len={len(chunk)}): {e}")
        await asyncio.sleep(0.5) # Prevent rate limiting

# ─────────────────────────────────────────────
# MOCKING INFRASTRUCTURE
# Centralized mocks for external platforms
# ─────────────────────────────────────────────

class MockUser:
    def __init__(self, id: int, name: str, display_name: str, bot: bool = False):
        self.id = id
        self.name = name
        self.display_name = display_name
        self.bot = bot

class MockChannel:
    def __init__(self, id: int, name: str = "mock-channel"):
        self.id = id
        self.name = name
        self.sent_messages = []

    async def send(self, content: str = None, **kwargs):
        if content:
            self.sent_messages.append(content)
        return type('MockResponse', (), {'id': 12345})()

    @property
    def typing(self):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def _typing():
            yield
        return _typing

class MockAttachment:
    """Enough of a discord.Attachment for the vision path to fetch it.

    That path keys off `.filename` and `.url` and nothing else, so a forum post's
    images can reach the model through the same code Discord uses. The extension
    matters: it is how `_prepare_image_payload` decides whether to take the first
    frame of a GIF, and a vBulletin attachment URL carries no extension at all.
    """

    __slots__ = ("url", "filename", "content_type", "size")

    def __init__(self, url: str, filename: str = "", content_type: str = "image/jpeg"):
        self.url = url
        self.filename = filename or _filename_for(url)
        self.content_type = content_type
        self.size = 0


def _filename_for(url: str) -> str:
    """A filename with a usable extension, inferred from the URL.

    `attachment.php?attachmentid=12345` is how vBulletin serves an uploaded
    image and has no extension, so the vision path's suffix test rejects it. It
    is a JPEG far more often than not, and a wrong guess costs the GIF
    first-frame branch rather than the image itself.
    """
    from urllib.parse import urlparse
    name = (urlparse(url).path.rsplit("/", 1)[-1] or "image").strip()
    if any(name.lower().endswith(e) for e in (".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return name
    return f"{name or 'image'}.jpg"


class MockMessage:
    def __init__(self, content: str, author: MockUser, channel: MockChannel,
                 platform: str = "discord", no_persist: bool = False,
                 attachments=None):
        # no_persist: run the pipeline for its output only. Used when drafting
        # a forum reply, where the "author" is someone being quoted rather than
        # someone Kaia is in conversation with, so writing interaction logs,
        # relationships and open loops against them is wrong.
        self.no_persist = no_persist
        self.content = content
        self.author = author
        self.channel = channel
        self.platform = platform
        self.attachments = list(attachments or [])
        self.embeds = []
        self.id = 123456789
        self.guild = None
        self.reference = None
        self.mentions = []

    async def reply(self, content: str = None, **kwargs):
        return await self.channel.send(content, **kwargs)
