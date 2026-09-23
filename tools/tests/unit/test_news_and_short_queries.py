"""Retrieval routing for news turns and short questions."""
import threading
from datetime import datetime

import pytest
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import NodeWithScore, TextNode

from utils.core.kaia_rag_query import (
    RAGQueryMixin, _FRESH_NEWS, _NAMED_PERIOD)
from utils.core.kaia_rag_indexer import RAGIndexerMixin


@pytest.mark.parametrize("q,question", [
    ("who wrote neuromancer?", True),
    ("tell me about neuromancer", True),
    ("what is a pogonip", True),
    ("how are you?", False),
    ("anyone?", False),
    ("hehe", False),
    ("australians are crazy", False),
    ("https://youtube.com/shorts/abc?is=xyz", False),
])
def test_a_short_question_is_not_small_talk(q, question):
    assert RAGQueryMixin._is_short_question(q) is question


def test_freshness_and_named_periods_are_told_apart():
    assert _FRESH_NEWS.search("what's the latest news on iran")
    assert not _FRESH_NEWS.search("what happened with iran in june? any news")
    assert _NAMED_PERIOD.search("what happened with iran in june")
    assert _NAMED_PERIOD.search("news from last month")
    assert not _NAMED_PERIOD.search("what's the latest news on iran")


class _Rag(RAGQueryMixin, RAGIndexerMixin):
    def __init__(self):
        self.indices = {"knowledge": VectorStoreIndex([])}
        self.indexed_files = {}
        self._data_lock = threading.RLock()


def test_the_newest_briefs_on_the_topic_join_a_news_pool(monkeypatch):
    monkeypatch.setattr(Settings, "_embed_model", MockEmbedding(embed_dim=8))
    rag = _Rag()

    def brief(day, text):
        path = f"/kb/news/daily/news_brief_202609{day:02d}.md"
        node = TextNode(text=text, metadata={"file_path": path})
        rag.indices["knowledge"].insert_nodes([node])
        rag.indexed_files[path] = {"nodes": [node.node_id]}
        return node.node_id

    old = brief(1, "Iran talks stall.")
    brief(20, "Crop yields fall.")           # newest, but off topic
    new = brief(21, "Iran and the Gulf states meet.")
    pool = [NodeWithScore(node=rag.indices["knowledge"].docstore.get_node(old), score=1.2)]

    added = rag._latest_news_candidates(pool, "what's the latest news on iran")
    assert [n.node.node_id for n in added] == [new]
    assert added[0].score == 1.2

    general = rag._latest_news_candidates(pool, "any news today?")
    assert len(general) == 2  # no topic: every newest brief not already held


@pytest.mark.parametrize("q,strategy", [
    ("Kaia, tell me about recent hacker news", "SYNTHESIS_SCAN"),
    ("Kaia, tell me about recent Iran war news", "SYNTHESIS_SCAN"),
    ("any news today?", "SYNTHESIS_SCAN"),
    ("tell me about neuromancer", "PRECISE_RECALL"),
    ("who is starkind", "PRECISE_RECALL"),
    ("thats good news", None),
])
def test_a_news_request_is_not_routed_as_a_question_about_kaia(q, strategy):
    from utils.core.intent_classifier import IntentParser
    intent = IntentParser().fast_parse(q)
    assert (intent.suggested_strategy if intent else None) == strategy


def test_chat_logs_keep_their_weight_when_the_conversation_is_the_question():
    from utils.core.kaia_rag_query import _CONVERSATION_CUE
    assert _CONVERSATION_CUE.search("what did we say about the iran news")
    assert not _CONVERSATION_CUE.search("tell me about recent hacker news")
