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


import pytest


@pytest.mark.parametrize("text", [
    "kaia what do you think about the solar system?",
    "the status quo is boring",
    "kaia did you fix your hair",
    "kaia mark my words, it will rain",
    "we should hang out later",
    "Kaia, https://x.com/SoIL_Ops/status/2102768975125868609?s=20",
])
def test_words_in_passing_are_not_a_diagnosis_or_a_greeting(text):
    """Diagnostics search chat logs only and run at the grounded temperature;
    a greeting skips retrieval. Neither fits these."""
    from utils.core.intent_classifier import IntentParser
    intent = IntentParser().fast_parse(text)
    assert intent is None or intent.suggested_strategy not in (
        "DIAGNOSTIC_DEEP_DIVE", "SOCIAL_GREETING", "PRECISE_RECALL")


@pytest.mark.parametrize("text", [
    "how do I fix a CUDA error in pytorch?", "kaia check your logs",
    "kaia restart", "kaia why is it slow", "there's a traceback in the output",
])
def test_real_diagnostics_still_are(text):
    from utils.core.intent_classifier import IntentParser
    assert IntentParser().fast_parse(text).suggested_strategy == "DIAGNOSTIC_DEEP_DIVE"
