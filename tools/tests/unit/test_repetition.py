import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from Kaiacord import on_message
from utils.infrastructure.logging.kaia_logger import log_info

async def test_social_variety():
    """Simulate multiple social mentions and check for variety."""
    
    class MockChannel:
        def __init__(self):
            self.id = 12345
            self.sent_messages = []
        async def send(self, content=None, **kwargs):
            if content: 
                # Strip code blocks for analysis
                clean = content.replace("```\n", "").replace("```", "").strip()
                self.sent_messages.append(clean)
            return type('obj', (object,), {'id': 999})()
        
        @property
        def typing(self):
            @asyncio.coroutine
            def dummy(): yield
            return dummy

    class MockAuthor:
        def __init__(self):
            self.id = "social_bluesky_test_user"
            self.name = "test_user"
            self.display_name = "test_user"
            self.bot = False

    class MockMessage:
        def __init__(self, content):
            self.content = content
            self.author = MockAuthor()
            self.channel = MockChannel()
            self.attachments = []
            self.platform = "bluesky"
            self.id = 1
            self.guild = None
            self.reference = None
            self.mentions = []
        async def reply(self, content=None, **kwargs):
            return await self.channel.send(content, **kwargs)

    print("\n--- Starting Social Variety Test ---\n")
    
    responses = []
    mentions = [
        "what's new kaia",
        "tell me about your dreams",
        "hi kaia, any updates?"
    ]
    
    for content in mentions:
        print(f"Sending mention: '{content}'")
        msg = MockMessage(content)
        await on_message(msg)
        if msg.channel.sent_messages:
            resp = msg.channel.sent_messages[0]
            print(f"Response: {resp}")
            responses.append(resp)
        print("-" * 20)

    # Check for forbidden phrases/patterns
    forbidden = ["Another handle", "Another address", "Been around", "I'm around"]
    for i, resp in enumerate(responses):
        for phrase in forbidden:
            if phrase.lower() in resp.lower():
                print(f"FAILED: Response {i+1} contains forbidden phrase '{phrase}'")
                return False
                
    # Check for verbatim overlap in openings
    if len(responses) >= 2:
        openings = [r[:20].lower() for r in responses]
        if len(set(openings)) < len(openings):
            print("FAILED: Verbatim overlap detected in response openings.")
            return False

    print("\nSUCCESS: No forbidden phrases or obvious repetition detected.\n")
    return True

if __name__ == "__main__":
    asyncio.run(test_social_variety())
