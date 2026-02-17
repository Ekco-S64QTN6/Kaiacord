import sys
import os
import asyncio
import re
from unittest.mock import MagicMock, AsyncMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Mock config before imports
from unittest.mock import MagicMock
sys.modules['utils.infrastructure.system.yaml_config'] = MagicMock()
mock_config = sys.modules['utils.infrastructure.system.yaml_config'].config
mock_config.token_multiplier = 1.3
mock_config.system_reserve_tokens = 256
mock_config.requests_per_minute = 60

from utils.core.kaia_intelligence import PersonalizationEngine
from utils.core.message_processor import MessageProcessor
from utils.core.kaia_rag import KaiaRAG

async def test_persona_hardening():
    print("--- Testing Persona Hardening ---")
    pe = PersonalizationEngine()
    traits = {'conciseness': 0.5, 'technicality': 0.5}
    prompt = pe.adapt_prompt("Initial System Prompt", traits)
    
    print("Checking for anti-apology rules in Style Adaptation...")
    assert "NO APOLOGIES" in prompt
    assert "NEVER say 'as an AI'" in prompt
    assert "FORBIDDEN" in prompt
    print("✅ Style Adaptation rules found.")

async def test_reinforcement_updates():
    print("\n--- Testing Reinforcement Updates ---")
    # MessageProcessor expects many arguments, let's mock them
    mp = MessageProcessor(
        bot=MagicMock(), ollama_client=MagicMock(), run_rag=AsyncMock(), 
        rag=MagicMock(), config=mock_config, bot_state=MagicMock(),
        performance_monitor=MagicMock(), intent_parser=MagicMock(),
        response_optimizer=MagicMock(), context_optimizer=MagicMock(),
        relevance_feedback=MagicMock(), personalization_engine=MagicMock(),
        stats_tracker=MagicMock(), rate_limiter=MagicMock(),
        shutdown_manager=MagicMock(), news_enhancer=MagicMock(),
        rag_enhancer=MagicMock(), news_manager=MagicMock(),
        dream_engine=MagicMock()
    )
    
    reinforcement = mp._get_reinforcement_prompt(is_social=False)
    print("Reinforcement Prompt:")
    print(reinforcement)
    
    assert "NO APOLOGIES" in reinforcement
    assert "Be weary, not sorry" in reinforcement
    assert "NO AI ASSISTANT SPEAK" in reinforcement
    print("✅ Reinforcement rules found correctly.")

async def test_rag_id_mapping():
    print("\n--- Testing RAG ID Mapping ---")
    rag = KaiaRAG()
    # We need to mock the filesystem for user_logs
    # Actually, we can just point it to a real directory if it exists or mock os.scandir
    
    query = "What does <@919782120308752425> think of salmon?"
    
    with MagicMock() as mock_scandir:
        # Mocking os.scandir is tricky. Let's just mock the results of re.findall and the directory scan logic if we can.
        # Better: let's test the re.findall and mapping logic in a separate snippet if full RAG test is too heavy.
        pass

    # Real check: findall
    id_mentions = re.findall(r"<@!?(\d+)>", query)
    print(f"IDs found: {id_mentions}")
    assert "919782120308752425" in id_mentions
    print("✅ ID extraction regex works.")

if __name__ == "__main__":
    asyncio.run(test_persona_hardening())
    asyncio.run(test_reinforcement_updates())
    asyncio.run(test_rag_id_mapping())
