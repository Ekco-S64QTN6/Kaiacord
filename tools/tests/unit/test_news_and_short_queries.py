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


import pytest


@pytest.mark.parametrize("text, about_her", [
    ("kaia tell me about neuromancer", False),
    ("kaia, who is ekco", False),
    ("tell me about the whole raid", False),
    ("kaia who are you", True),
    ("kaia what is your favourite book", True),
    ("tell me about yourself", True),
])
def test_precise_recall_is_about_her_only_when_she_is_the_subject(text, about_her):
    """Addressing her by name is not asking about her."""
    from types import SimpleNamespace
    from utils.core.kaia_rag import KaiaRAG
    rag = KaiaRAG.__new__(KaiaRAG)
    r = rag._route_retrieval_strategy("general", text, SimpleNamespace(suggested_strategy="PRECISE_RECALL"), text)
    assert r["is_kaia_query"] is about_her
    assert r["is_entity_query"] is (not about_her)


@pytest.mark.parametrize("text", [
    "how do I fix error 1017 on project 1999",
    "my eqgame keeps crashing at zoning",
])
def test_a_diagnostic_searches_the_guides_as_well_as_the_logs(text):
    """An error question is answered from knowledge_base/troubleshooting and
    wiki; searching chat logs alone never reached them."""
    from utils.core.intent_classifier import IntentParser
    from utils.core.kaia_rag import KaiaRAG
    intent = IntentParser().fast_parse(text)
    assert intent.suggested_strategy == "DIAGNOSTIC_DEEP_DIVE"
    rag = KaiaRAG.__new__(KaiaRAG)
    routing = rag._route_retrieval_strategy("tech", text.lower(), intent, text.lower())
    targets, _ = rag._target_indices(routing, 5)
    assert "knowledge" in targets and "logs" in targets


# ── Whose profile and logs, and what counts as news ───────────────────

_ROUTING = {"strategy": "PRECISE_RECALL", "is_casual": False, "is_dream_query": False,
            "is_social_identity": False, "is_entity_query": True, "is_news_query": False}


def _node(path, text, **meta):
    from llama_index.core.schema import NodeWithScore, TextNode
    return NodeWithScore(node=TextNode(text=text, metadata={"file_path": path, **meta}), score=1.0)


def _scored(nodes, routing, relevant_ids, **kw):
    rag = RAGQueryMixin()
    rag.indices = {}
    out = rag._score_and_filter_nodes(nodes, "who is starkind", relevant_ids, routing, 20,
                                      kw.get("include_news", False), kw.get("strict", True))
    return {r["metadata"]["file_path"]: r["label"] for r in out}


def test_who_is_x_reaches_the_named_persons_profile_and_logs():
    """Identity-scoped to the asker alone, "who is starkind" reached nothing
    Starkind had said. Profiles indexed before they were typed carry
    source_type user_logs, so they are recognised by filename."""
    star = "/kb/user_logs/Starkind_2/"
    nodes = [
        _node(star + "user_profile.md", "Starkind profile", source_type="user_logs", user_id="2"),
        _node(star + "interactions_20260920.md", "Starkind: nala again", source_type="user_logs", user_id="2"),
        _node("/kb/user_logs/forum_Bones_197/user_profile.md", "a stranger", source_type="user_profile", user_id="197"),
        _node("/kb/user_logs/Other_3/interactions_20260920.md", "someone else", source_type="user_logs", user_id="3"),
    ]
    got = _scored(nodes, dict(_ROUTING, named_ids={"2"}), {"1"})
    assert got[star + "user_profile.md"].startswith("Profile")
    assert star + "interactions_20260920.md" in got
    assert "/kb/user_logs/forum_Bones_197/user_profile.md" not in got
    assert "/kb/user_logs/Other_3/interactions_20260920.md" not in got


def test_a_short_id_does_not_admit_a_folder_that_contains_it():
    nodes = [_node("/kb/user_logs/Ekco_177011971818782721/interactions_20260920.md", "x",
                   source_type="user_logs")]
    assert not _scored(nodes, dict(_ROUTING, named_ids=set()), {"197"})


def test_only_the_news_folder_is_news():
    """A dream about a brief is named after it, and a document may have news
    in its title; neither is dropped from a turn that is not about news."""
    nodes = [
        _node("/kb/kaia_dreams/other/dream_20260928_033930_news_brief_20260924.md", "a dream", source_type="news"),
        _node("/kb/documents/research - news analysis and extraction plan.md", "a plan", source_type="general_knowledge"),
        _node("/kb/news/daily/news_brief_20260924.md", "a brief", source_type="news"),
    ]
    routing = dict(_ROUTING, strategy=None, is_entity_query=False, named_ids=set())
    got = _scored(nodes, routing, set(), strict=False)
    assert set(got) == {nodes[0].node.metadata["file_path"], nodes[1].node.metadata["file_path"]}


@pytest.mark.parametrize("itype, path, expected", [
    ("user_profiles", "/kb/user_logs/Starkind_2/user_profile.md", "user_profile"),
    ("logs", "/kb/user_logs/Starkind_2/interactions_20260920.md", "user_logs"),
    ("dreams", "/kb/kaia_dreams/other/dream_20260928_news_brief_20260924.md", "dream"),
    ("knowledge", "/kb/news/daily/news_brief_20260924.md", "news"),
])
def test_the_indexer_types_profiles_and_dreams_by_what_they_are(itype, path, expected):
    from llama_index.core import Document
    doc = Document(text="text")
    RAGIndexerMixin._apply_priority_metadata(None, doc, itype, path)
    assert doc.metadata["source_type"] == expected


def test_a_question_names_people_by_their_log_folder():
    rag = RAGQueryMixin()
    rag._known_user_folders = ["Starkind_2", "forum_BiG SiP_221666", "Tenno_Henka_9",
                               "Kaia-Autonomous_channel_5", "forum_Bones_197"]
    rag._resolve_identity_mappings = lambda uid: {uid}
    assert rag._named_user_ids("who is starkind's cat") == {"2"}
    assert rag._named_user_ids("ask big sip and tenno henka") == {"221666", "9"}
    assert rag._named_user_ids("starkindness") == set()
    assert rag._named_user_ids("kaia-autonomous channel") == set()
