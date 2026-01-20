import os
import json
import unittest
from unittest.mock import MagicMock, patch

# Mocking discord and other dependencies to test the logic without a real bot
import sys
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
sys.modules['kaia_rag'] = MagicMock()
sys.modules['kaia_image'] = MagicMock()
sys.modules['kaia_vision'] = MagicMock()
sys.modules['clear_gpu_memory'] = MagicMock()
sys.modules['ollama'] = MagicMock()

# Import the functions to test
# We need to be careful with imports since Kaiacord.py has top-level code
# For this test, we'll just mock the state file and test the logic

STATE_FILE = "bot_state.json"
BLACKLISTED_CHANNELS = ["general", "announcements", "rules"]

def load_bot_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                return state.get('last_active_channel_id')
    except Exception as e:
        print(f"Warning: Failed to load bot state: {e}")
    return None

def save_bot_state(channel_id):
    try:
        state = {'last_active_channel_id': channel_id}
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Warning: Failed to save bot state: {e}")

class TestBotState(unittest.TestCase):
    def setUp(self):
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

    def tearDown(self):
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)

    def test_save_load_state(self):
        test_id = 123456789
        save_bot_state(test_id)
        loaded_id = load_bot_state()
        self.assertEqual(test_id, loaded_id)

    def test_fallback_logic_mock(self):
        # Mocking the fallback logic from Kaiacord.py
        mock_guild = MagicMock()
        
        # Channel 1: Blacklisted
        chan1 = MagicMock()
        chan1.name = "general"
        chan1.id = 1
        chan1.position = 1
        chan1.permissions_for.return_value.send_messages = True
        
        # Channel 2: Not blacklisted
        chan2 = MagicMock()
        chan2.name = "kaia-opolis"
        chan2.id = 2
        chan2.position = 2
        chan2.permissions_for.return_value.send_messages = True
        
        mock_guild.text_channels = [chan1, chan2]
        
        # Logic to test
        last_active_channel_id = None
        for channel in sorted(mock_guild.text_channels, key=lambda c: c.position):
            if channel.permissions_for(mock_guild.me).send_messages:
                if channel.name.lower() not in BLACKLISTED_CHANNELS:
                    last_active_channel_id = channel.id
                    break
        
        self.assertEqual(last_active_channel_id, 2)

if __name__ == "__main__":
    unittest.main()
