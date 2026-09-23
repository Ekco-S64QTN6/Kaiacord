"""Only a turn that asks about a document may be answered from one document.

Both retrieval shortcuts replace normal retrieval with a single file at full
confidence. Ungated, they fired on idle quips whose topic shared "ai" and
"international" with a report's title, and on ordinary conversation.
"""
import pytest

from utils.core.kaia_rag_query import RAGQueryMixin


@pytest.mark.parametrize("query", [
    "can you provide more data from the tragedy of the commons document",
    "summarize the international ai safety report",
    "what does the article about sustainable war say",
    "look at 2026-09-01_apollo-ai-labor-market-impact",
    "check notes.md",
    "what happens in the book neuromancer",
])
def test_a_document_request_is_recognised(query):
    assert RAGQueryMixin._is_document_request(query)


@pytest.mark.parametrize("query", [
    "can you explain this to me",
    "what do you think about the state-of-the-art models",
    "i was doing some research on ai and war",
    "reflecting on how ai reshapes international politics",
    "check that out, it's wild",
])
def test_conversation_is_not_a_document_request(query):
    assert not RAGQueryMixin._is_document_request(query)


def test_conversation_is_not_routed_to_summarisation():
    router = RAGQueryMixin()
    for query in ("can you explain this to me",
                  "what do you think about the state-of-the-art models"):
        assert router._route_retrieval_strategy("general", query, None)["strategy"] != "SUMMARIZATION"
    assert router._route_retrieval_strategy(
        "general", "summarize the international ai safety report", None)["strategy"] == "SUMMARIZATION"


def test_a_log_chunk_is_dated_by_its_conversation_not_its_file():
    """A recap of "the last 24 hours" took any chunk whose file had been
    rewritten recently — a monthly archive the rollup just touched — as new."""
    import types
    from datetime import datetime
    node = lambda **m: types.SimpleNamespace(metadata=m)
    recent = datetime(2026, 9, 22).timestamp()

    assert RAGQueryMixin._node_timestamp(node(timestamp=123.0)) == 123.0
    assert datetime.fromtimestamp(RAGQueryMixin._node_timestamp(
        node(file_path="/logs/Ekco_177011971818782721/interactions_20260911.md",
             last_modified_at=recent))).date().isoformat() == "2026-09-11"
    assert datetime.fromtimestamp(RAGQueryMixin._node_timestamp(
        node(file_path="/logs/x/interactions_202607_archive.md",
             last_modified_at=recent))).date().isoformat() == "2026-07-31"
