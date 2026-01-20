import unittest
from unittest.mock import MagicMock

# Mocking the logic from Kaiacord.py
BLACKLISTED_CHANNELS = ["general", "announcements", "rules"]

async def on_message_mock(msg):
    # This is the logic we want to test
    if msg.author.bot: # Simplified for test
        return

    if msg.channel.name.lower() in BLACKLISTED_CHANNELS:
        return "IGNORED"

    if "kaia" in msg.content.lower():
        return "RESPONDED"
    
    return "SKIPPED"

class TestChannelBlacklist(unittest.IsolatedAsyncioTestCase):
    async def test_blacklisted_channel_ignored(self):
        msg = MagicMock()
        msg.author.bot = False
        msg.channel.name = "general"
        msg.content = "kaia, hello?"
        
        result = await on_message_mock(msg)
        self.assertEqual(result, "IGNORED")

    async def test_non_blacklisted_channel_responded(self):
        msg = MagicMock()
        msg.author.bot = False
        msg.channel.name = "kaia-opolis"
        msg.content = "kaia, hello?"
        
        result = await on_message_mock(msg)
        self.assertEqual(result, "RESPONDED")

if __name__ == "__main__":
    unittest.main()
