"""
Unit tests for Phase 63/64 cognitive pipeline and safety filter enhancements.
Tests bot-speak protocol excuse stripping, false moderation/psychiatric threat suppression,
and degenerate empty/addressee-only output rejection.
"""

from utils.core.response_filter import BotSpeakFilter


def test_protocol_adjustment_excuses_stripped():
    """Verify that robotic filter/protocol adjustment excuses are stripped cleanly."""
    input_text = "ah, looked like a tuxedo on the stairs. i am adjusting the image recognition filters to prevent similar misidentifications in the future."
    result = BotSpeakFilter.harden(input_text)
    assert "image recognition filters" not in result
    assert "looked like a tuxedo on the stairs" in result


def test_date_protocol_excuse_stripped():
    """Verify that date protocol adjustment excuses are stripped."""
    input_text = "today is august 30th. i am adjusting my date recognition protocols to reflect that."
    result = BotSpeakFilter.harden(input_text)
    assert "protocols" not in result
    assert "today is august 30th" in result


def test_heuristic_adjustment_stripped():
    """Verify response heuristics excuses are stripped."""
    input_text = "wildflowers are a lot more grounded. i will adjust my response heuristics accordingly."
    result = BotSpeakFilter.harden(input_text)
    assert "heuristics" not in result
    assert "wildflowers are a lot more grounded" in result


def test_false_moderation_and_psychiatric_threats_stripped():
    """Verify that psychiatric evaluation demands and moderation threats are stripped."""
    input_text = (
        "raising flesh-eating larvae in your shin isn't a viable hobby. "
        "i strongly urge you to seek professional psychological evaluation immediately. "
        "your activity will be reported to the appropriate oversight channels."
    )
    result = BotSpeakFilter.harden(input_text)
    assert "psychological evaluation" not in result
    assert "oversight channels" not in result
    assert "raising flesh-eating larvae in your shin isn't a viable hobby" in result


def test_bare_addressee_only_output_rejected():
    """Verify that degenerate outputs containing only an addressee prefix return empty string."""
    assert BotSpeakFilter.harden("starkind,") == ""
    assert BotSpeakFilter.harden("ekco:") == ""
    assert BotSpeakFilter.harden("jimjam, \n\n") == ""
    assert BotSpeakFilter.harden("lune.\n") == ""


def test_prompt_echo_not_my_robotic_cat_stripped():
    """Verify prompt echoing of robotic cat rules is stripped."""
    input_text = "two cats on the bed. i acknowledge these are living biological animals belonging to you, not my fictional robotic pet pixel."
    result = BotSpeakFilter.harden(input_text)
    assert "robotic pet pixel" not in result
    assert "two cats on the bed" in result


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
    assert ctx.knowledge_boundary_check == {}
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
    """Verify standard modules are properly imported in modules that use them."""
    import utils.commands.forum_handler as fh
    import utils.social.kaia_forum as kf
    import utils.core.kaia_rag_retriever as krr
    import utils.social.kaia_social_responder as ksr

    assert hasattr(fh, 'asyncio')
    assert hasattr(kf, 'traceback')
    assert hasattr(krr, 'os')
    assert hasattr(ksr, 'get_x_client') or 'get_x_client' in ksr.check_and_reply_mentions.__code__.co_names


