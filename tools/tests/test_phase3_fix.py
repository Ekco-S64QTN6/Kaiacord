import sys
import os
import asyncio
import re
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Mock config
sys.modules['utils.infrastructure.system.yaml_config'] = MagicMock()
mock_config = sys.modules['utils.infrastructure.system.yaml_config'].config
mock_config.token_multiplier = 1.3
mock_config.system_reserve_tokens = 256

from utils.news.kaia_news import ResponseEnhancer
from utils.core.kaia_intelligence import PersonalizationEngine
from utils.core.message_processor import MessageProcessor

async def test_style_prose():
    print("--- Testing Style Adaptation Prose Constraints ---")
    pe = PersonalizationEngine()
    prompt = pe.adapt_prompt("Base", {'conciseness': 0.5, 'technicality': 0.5})
    
    print("Style Adaptation Segment:")
    print(prompt[len("Base"):])
    
    assert "NO MARKDOWN" in prompt
    assert "NO bullet points" in prompt
    assert "NO bolding" in prompt
    assert "plain prose only" in prompt
    print("✅ Style adaptation restricts markdown correctly.")

if __name__ == "__main__":
    asyncio.run(test_style_prose())
