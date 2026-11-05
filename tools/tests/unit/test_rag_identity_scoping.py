"""Identity scoping for RAG's whole-document retrieval shortcuts."""

from types import SimpleNamespace

import pytest

from utils.core.kaia_rag_query import RAGQueryMixin


class _Node:
    def __init__(self, path: str, text: str):
        self.metadata = {"file_path": path, "chunk_index": 0, "source_type": "user_logs"}
        self.text = text


class _DocStore:
    def __init__(self, nodes):
        self.docs = nodes

    def get_document(self, node_id):
        return self.docs[node_id]


class _SummaryRAG(RAGQueryMixin):
    def __init__(self, indexed_files, nodes):
        self.indexed_files = indexed_files
        docstore = _DocStore(nodes)
        self.indices = {
            "logs": SimpleNamespace(storage_context=SimpleNamespace(docstore=docstore)),
            "knowledge": SimpleNamespace(storage_context=SimpleNamespace(docstore=docstore)),
        }


def test_summary_path_scope_matches_normal_identity_policy():
    allowed = {"111", "222"}
    assert RAGQueryMixin._summary_path_allowed(
        "/kb/user_logs/Alice_111/interactions_20261104.md", True, allowed
    )
    assert not RAGQueryMixin._summary_path_allowed(
        "/kb/user_logs/Bob_333/interactions_20261104.md", True, allowed
    )
    assert RAGQueryMixin._summary_path_allowed(
        "/kb/user_logs/Bob_222/interactions_20261104.md", True, allowed
    )
    assert RAGQueryMixin._summary_path_allowed(
        "/kb/user_logs/social_x_handle/interactions_20261104.md",
        True, {"handle"},
    )
    assert RAGQueryMixin._summary_path_allowed(
        "/kb/documents/public.md", True, allowed
    )
    assert RAGQueryMixin._summary_path_allowed(
        "/kb/user_logs/Bob_333/interactions_20261104.md", False, set()
    )
    assert not RAGQueryMixin._summary_path_allowed(
        "/kb/user_logs/malformed/interactions_20261104.md", True, allowed
    )


def test_summary_picker_skips_other_users_with_identical_daily_filename(tmp_path):
    """A same-named daily transcript must not resolve to another user's entry."""
    alice_path = str(tmp_path / "user_logs" / "Alice_111" / "interactions_20261104.md")
    bob_path = str(tmp_path / "user_logs" / "Bob_222" / "interactions_20261104.md")
    nodes = {
        "alice": _Node(alice_path, "Alice private conversation"),
        "bob": _Node(bob_path, "Bob private conversation"),
    }
    rag = _SummaryRAG({
        alice_path: {"itype": "logs", "nodes": ["alice"]},
        bob_path: {"itype": "logs", "nodes": ["bob"]},
    }, nodes)

    results = rag._get_summarization_nodes(
        "summarize interactions_20261104.md",
        strict_identity=True, allowed_user_ids={"111"},
    )

    assert results
    assert {n["metadata"]["file_path"] for n in results} == {alice_path}
    assert all("Bob private conversation" not in n["content"] for n in results)


def test_summary_target_path_cannot_bypass_identity_scope(tmp_path):
    bob_path = str(tmp_path / "user_logs" / "Bob_222" / "interactions_20261104.md")
    nodes = {"bob": _Node(bob_path, "Bob private conversation")}
    rag = _SummaryRAG({
        bob_path: {"itype": "logs", "nodes": ["bob"]},
    }, nodes)

    denied = rag._get_summarization_nodes(
        "interactions_20261104.md", target_path=bob_path,
        strict_identity=True, allowed_user_ids={"111"},
    )
    allowed_named_person = rag._get_summarization_nodes(
        "interactions_20261104.md", target_path=bob_path,
        strict_identity=True, allowed_user_ids={"111", "222"},
    )
    general = rag._get_summarization_nodes(
        "interactions_20261104.md", target_path=bob_path,
    )

    assert denied == []
    assert allowed_named_person and allowed_named_person[0]["metadata"]["file_path"] == bob_path
    assert general and general[0]["metadata"]["file_path"] == bob_path


@pytest.mark.asyncio
async def test_retrieve_resolves_requester_and_named_people_before_summary_shortcut(tmp_path):
    class FakeRAG(RAGQueryMixin):
        def __init__(self):
            self.indices = {"knowledge": object()}
            self._last_retrieval_confidence = 0.0
            self._last_retrieval_node_count = 0
            self._last_retrieval_time = 0.0
            self._last_retrieval_results = []
            self._known_user_folders = []
            self._known_users_cache = []
            self._last_user_scan = 0.0
            self._user_scan_interval = 300
            self.knowledge_base_dir = str(tmp_path)

        def _route_retrieval_strategy(self, category, query_lower, intent, own_lower):
            return {"strategy": "SUMMARIZATION", "is_news_query": False, "is_casual": False}

        def _resolve_identity_mappings(self, user_id):
            return {str(user_id)}

        def _named_user_ids(self, own_lower):
            assert "Bob_222" in self._known_user_folders
            return {"222"}

        def _get_summarization_nodes(
            self, query_lower, target_path=None, strict_identity=False, allowed_user_ids=None
        ):
            self.captured = (strict_identity, set(allowed_user_ids or ()))
            return [{"content": "safe", "metadata": {}, "label": "summary", "score": 1.0}]

        def _get_channel_key(self):
            return "test-channel"

    logs = tmp_path / "user_logs"
    (logs / "Bob_222").mkdir(parents=True)
    rag = FakeRAG()
    result = await rag.retrieve(
        "summarize Bob's interactions_20261104.md",
        user_id="111", strict_identity=True, category="entity",
    )

    assert result and rag.captured == (True, {"111", "222"})



def test_manifest_title_match_ignores_disallowed_same_named_logs(tmp_path):
    filename = "2026-11-04-interactions-forum-events.md"
    alice_path = str(tmp_path / "user_logs" / "Alice_111" / filename)
    bob_path = str(tmp_path / "user_logs" / "Bob_222" / filename)
    rag = _SummaryRAG({alice_path: {}, bob_path: {}}, {})

    path, overlap = rag._title_match(
        {"interactions", "forum", "events"}, set(),
        strict_identity=True, allowed_user_ids={"111"},
    )

    assert path == alice_path
    assert overlap == {"interactions", "forum", "events"}


def test_unindexed_disk_fallback_obeys_identity_scope(tmp_path):
    """The on-disk fallback is safe even when its configured root is narrowed to logs."""
    from pathlib import Path

    logs = tmp_path / "user_logs"
    alice = logs / "Alice_111" / "interactions_20261104.md"
    bob = logs / "Bob_222" / "interactions_20261104.md"
    alice.parent.mkdir(parents=True)
    bob.parent.mkdir(parents=True)
    alice.write_text("Alice private content", encoding="utf-8")
    bob.write_text("Bob private content", encoding="utf-8")

    rag = _SummaryRAG({}, {})
    rag.knowledge_base_dir = str(logs)

    scoped_to_alice = rag._named_file_on_disk(
        "interactions_20261104.md", "interactions_20261104.md",
        strict_identity=True, allowed_user_ids={"111"},
    )
    scoped_to_bob = rag._named_file_on_disk(
        "interactions_20261104.md", "interactions_20261104.md",
        strict_identity=True, allowed_user_ids={"222"},
    )
    general = rag._named_file_on_disk(
        "interactions_20261104.md", "interactions_20261104.md",
    )

    assert scoped_to_alice == str(alice.resolve())
    assert scoped_to_bob == str(bob.resolve())
    assert general in {str(alice.resolve()), str(bob.resolve())}

    # With no copy owned by the requester, the other user's file is not a
    # fallback candidate at all.
    only_bob = tmp_path / "only_bob" / "user_logs"
    private = only_bob / "Bob_222" / "interactions_20261104.md"
    private.parent.mkdir(parents=True)
    private.write_text("Bob's private interaction", encoding="utf-8")
    rag.knowledge_base_dir = str(only_bob)
    denied = rag._named_file_on_disk(
        "interactions_20261104.md", "interactions_20261104.md",
        strict_identity=True, allowed_user_ids={"111"},
    )
    assert denied is None



def test_manifest_node_ids_cannot_cross_file_or_user_boundaries(tmp_path):
    """A stale manifest entry must not make a permitted path return another user's node."""
    alice_path = str(tmp_path / "user_logs" / "Alice_111" / "interactions_20261104.md")
    bob_path = str(tmp_path / "user_logs" / "Bob_222" / "interactions_20261104.md")
    nodes = {
        "bob": _Node(bob_path, "Bob private conversation"),
    }
    rag = _SummaryRAG({
        # The path itself belongs to Alice, but the manifest points at Bob's node.
        alice_path: {"itype": "logs", "nodes": ["bob"]},
    }, nodes)

    results = rag._get_summarization_nodes(
        "interactions_20261104.md", target_path=alice_path,
        strict_identity=True, allowed_user_ids={"111"},
    )

    assert results == []
