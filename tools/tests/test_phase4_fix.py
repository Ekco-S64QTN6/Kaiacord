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
mock_config.rag_path_boost = 0.5
mock_config.rag_type_boosts = {'persona': 0.15, 'user_profile': 0.20, 'dream': 0.10, 'memory': 0.25}

from utils.core.kaia_rag import KaiaRAG
from utils.core.kaia_intelligence import PersonalizationEngine
from utils.core.response_filter import BotSpeakFilter

async def test_name_verification():
    print("--- Testing RAG Name Verification ---")
    # Mocking indices and retrievers is complex, but we can test the filter logic if we had access.
    # Instead, we'll verify the persona instructions.
    pe = PersonalizationEngine()
    prompt = pe.adapt_prompt("Base", {'conciseness': 0.5, 'technicality': 0.5})
    
    print("Veracity Guard in Prompt:")
    assert "VERACITY GUARD" in prompt
    assert "skeptical of unverified premises" in prompt
    print("✅ Veracity guard is present in the system prompt.")
    
    assert "Hallucination Indicators" in prompt
    assert "Do not invent personal anecdotes" in prompt
    print("✅ Anecdote ban is strengthened and labeled.")

async def test_violation_stripper():
    print("\n--- Testing Programmatic Violation Stripping ---")
    bad_response = "I'm so sorry, I made a major error in my memory retrieval context.\nActually, the fact is X.\nMy apologies for the conflation error."
    
    clean = BotSpeakFilter.strip_bot_speak(bad_response)
    print("Cleaned Response:")
    print(f"'{clean}'")
    
    assert "apologies" not in clean.lower()
    assert "error" not in clean.lower()
    assert "retrieval" not in clean.lower()
    assert "Actually, the fact is X." in clean
    print("✅ Violation stripper correctly removed apologies and meta-talk.")

if __name__ == "__main__":
    asyncio.run(test_name_verification())
    asyncio.run(test_violation_stripper())
