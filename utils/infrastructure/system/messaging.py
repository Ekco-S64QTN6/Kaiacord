import asyncio
from utils.infrastructure.logging.kaia_logger import log_warning

async def send_kaia_response(channel, text, use_code_block=False):
    """Helper to split long messages and optionally wrap them in Kaia's style"""
    if not text:
        log_warning("send_kaia_response called with empty text. Skipping.")
        return
        
    # Discord limit is 2000. 
    # Use 1980 for code blocks to leave room for ```\n and \n```
    # Use 1990 for plain text for a small safety margin.
    limit = 1980 if use_code_block else 1990
    
    if len(text) <= limit:
        if use_code_block:
            await channel.send(f"```\n{text.strip()}\n```")
        else:
            await channel.send(text.strip())
        return

    # Split into chunks
    chunks = []
    current_chunk = ""
    
    for line in text.split('\n'):
        if len(current_chunk) + len(line) + 1 > limit:
            chunks.append(current_chunk.strip())
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
            
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    for chunk in chunks:
        if not chunk: continue
        if use_code_block:
            await channel.send(f"```\n{chunk}\n```")
        else:
            await channel.send(chunk)
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

class MockMessage:
    def __init__(self, content: str, author: MockUser, channel: MockChannel, platform: str = "discord"):
        self.content = content
        self.author = author
        self.channel = channel
        self.platform = platform
        self.attachments = []
        self.embeds = []
        self.id = 123456789
        self.guild = None
        self.reference = None
        self.mentions = []

    async def reply(self, content: str = None, **kwargs):
        return await self.channel.send(content, **kwargs)
