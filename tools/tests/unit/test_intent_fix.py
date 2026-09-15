import sys
import os
import asyncio
import re
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


@pytest.mark.asyncio
async def test_fast_parse_biographical():
    """Test that biographical queries hit PRECISE_RECALL via fast-path."""
    print("--- Testing Biographical Fast Parse ---")

    # Use patch() context manager to mock config cleanly — no sys.modules poisoning
    with patch('utils.infrastructure.system.yaml_config.config') as mock_config:
        mock_config.classification_timeout = 15.0
        mock_config.chat_model = "gemma3:12b"
        mock_config.max_context_tokens = 24000
        mock_config.token_multiplier = 1.3
        mock_config.system_reserve_tokens = 256
        mock_config.get.side_effect = lambda key, default=None: {
            'models.classification_on_gpu': False,
        }.get(key, default)
        mock_config.classification_context_tokens = 2048
        mock_config.num_thread = 6

        from utils.core.kaia_intelligence import IntentParser
        parser = IntentParser(ollama_client=AsyncMock())

        test_queries = [
            "I would like a dossier on Morgan Everett",
            "tell me about Thorne",
            "give me a biography of Elara",
            "background on the Illuminati"
        ]

        for query in test_queries:
            intent = parser.fast_parse(query)
            print(f"Query: '{query}' -> Strategy: {intent.suggested_strategy if intent else 'None'}")
            assert intent is not None
            assert intent.suggested_strategy == "PRECISE_RECALL"

        print("✅ All biographical fast-triggers matched correctly.")


def test_the_llm_second_pass_is_gone():
    """This file used to verify `_analyze_with_llm` "still functions". It no
    longer exists: the second pass ran gemma2:2b on every ambiguous message and
    nothing ever read the result, so the dispatch, the model and the config
    that fed it were removed. The fast path above is the whole classifier."""
    from utils.core.kaia_intelligence import IntentParser

    parser = IntentParser()
    assert not hasattr(parser, "_analyze_with_llm")
    assert not hasattr(parser, "parse_intent")
