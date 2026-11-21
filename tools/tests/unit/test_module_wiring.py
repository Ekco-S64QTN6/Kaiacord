import pytest
"""
Unit tests for Phase 63/64 cognitive pipeline and safety filter enhancements.
Tests bot-speak protocol excuse stripping, false moderation/psychiatric threat suppression,
and degenerate empty/addressee-only output rejection.
"""

from utils.core.response_filter import BotSpeakFilter


def test_message_context_default_pipeline_attributes():
    """Verify MessageContext initializes all pipeline attributes safely to avoid AttributeErrors."""
    from unittest.mock import MagicMock
    from utils.core.message_context import MessageContext

    mock_msg = MagicMock()
    ctx = MessageContext(message=mock_msg, sanitized_content="hello")
    assert ctx.raw_nodes == []
    assert ctx.context_nodes == []
    assert ctx.system_prompt == ""
    assert ctx.user_traits == {}
    assert ctx.classification_task is None
    assert ctx._is_channel_recall is False
    assert ctx._channel_refs is None


def test_bm25_retriever_tokenize_node_imports():
    """Verify SimpleBM25Retriever._tokenize_node safely handles file paths without NameErrors."""
    from utils.core.kaia_rag_retriever import SimpleBM25Retriever

    retriever = SimpleBM25Retriever(nodes=[])
    node = {
        "text": "aquarium tank setup and maintenance",
        "metadata": {
            "file_path": "/path/to/Kaia - Limnological Biosphere.md",
            "title": "Limnological Biosphere"
        }
    }

    tokens = retriever._tokenize_node(node)
    assert "aquarium" in tokens
    assert "limnological" in tokens
    assert "biosphere" in tokens


def test_module_global_imports_exist():
    """A module that uses a standard module imports it.

    Unused-import cleanups are how these go missing, and a NameError only
    shows when the path runs.
    """
    import importlib
    import re
    for mod_name in ("utils.commands.forum_handler", "utils.social.kaia_forum",
                     "utils.core.kaia_rag_retriever", "utils.social.kaia_social_responder"):
        mod = importlib.import_module(mod_name)
        src = open(mod.__file__, encoding="utf-8").read()
        for std in ("asyncio", "traceback", "os", "json", "re", "time"):
            if re.search(rf"(?<![\w.]){std}\.\w", src):
                imported = hasattr(mod, std) or re.search(rf"^\s*import {std}\b", src, re.M)
                assert imported, f"{mod_name} uses {std}. without importing it"


