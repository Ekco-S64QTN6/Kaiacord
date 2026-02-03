import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock discord and other dependencies before importing Kaiacord
sys.modules['discord'] = MagicMock()
sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.ext.commands'] = MagicMock()
sys.modules['discord.ext.tasks'] = MagicMock()
sys.modules['watchdog'] = MagicMock()
sys.modules['watchdog.observers'] = MagicMock()
sys.modules['watchdog.events'] = MagicMock()

# Now we can import the functions we want to test
# We need to mock the global variables in Kaiacord.py
import Kaiacord
from Kaiacord import send_kaia_response, EmergencyContaminationFilter

async def test_response_fallback():
    print("--- Testing Response Fallback ---")
    
    # Mock channel
    mock_channel = AsyncMock()
    
    # Test 1: Empty response
    print("Test 1: Empty response")
    await send_kaia_response(mock_channel, "")
    mock_channel.send.assert_not_called()
    print("Test 1 passed: No message sent for empty input")

    # Test 2: Response that becomes empty after cleaning
    print("Test 2: Response that becomes empty after cleaning")
    # "user profile:" is a skip pattern in clean_response_for_discord
    await send_kaia_response(mock_channel, "user profile: some data")
    mock_channel.send.assert_not_called()
    print("Test 2 passed: No message sent for cleaned-to-empty input")

    # Test 3: Fallback in on_message logic (simulated)
    print("Test 3: Fallback in on_message logic")
    # We'll simulate the logic in on_message where content becomes empty
    content = ""
    if not content or not content.strip():
        content = "..."
    
    await send_kaia_response(mock_channel, content)
    mock_channel.send.assert_called_with("```\n...\n```")
    print("Test 3 passed: Fallback '...' sent for empty content")

    # Test 4: Contamination filter fallback
    print("Test 4: Contamination filter fallback")
    contaminated_text = "juanita deane bonbons" # All patterns in CONTAMINATION_PATTERNS
    filtered = EmergencyContaminationFilter.filter_response(contaminated_text)
    print(f"Filtered text: '{filtered}'")
    if filtered == "":
        print("Test 4 passed: Contamination filter returned empty string for highly contaminated text")
    else:
        print(f"Test 4 failed: Expected empty string, got '{filtered}'")

if __name__ == "__main__":
    asyncio.run(test_response_fallback())
