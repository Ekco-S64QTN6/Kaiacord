"""What leaves the index actually leaves it, and what goes in is indexed once.

A September 2026 audit of the live index found 70% of the knowledge docstore
was deleted content still searchable by BM25, 3,345 dream vectors from files
that no longer existed, 3,852 copies of old persona text, forum profiles never
refreshed, and log turns indexed twice on any file with a curly quote.
"""
import asyncio
import hashlib
import os
import threading

import pytest
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import MetadataMode, TextNode

from utils.core.kaia_rag_indexer import ConversationTurnSplitter, RAGIndexerMixin
from utils.core.kaia_rag_query import RAGQueryMixin


class _Indexer(RAGIndexerMixin):
    def __init__(self, kb_dir):
        self.knowledge_base_dir = str(kb_dir)
        self.persist_dir = os.path.join(str(kb_dir), "_rag_test_state")
        self.state_file = os.path.join(self.persist_dir, "file_manifest.json")
        os.makedirs(self.persist_dir, exist_ok=True)
        self.indices = {t: VectorStoreIndex([]) for t in ("knowledge", "logs", "dreams")}
        self.bm25_cache = {}
        self.indexed_files = {}
        self._file_to_nodes = {}
        self._data_lock = threading.RLock()


@pytest.fixture
def indexer(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "_embed_model", MockEmbedding(embed_dim=8))
    kb = tmp_path / "knowledge_base"
    kb.mkdir()
    return _Indexer(kb), kb


def _add(ix, itype, path, text="some text about tidal locking"):
    node = TextNode(text=text, metadata={"file_path": str(path)})
    ix.indices[itype].insert_nodes([node])
    return node.node_id


def test_delete_removes_the_node_from_the_docstore_too(indexer, tmp_path):
    ix, kb = indexer
    f = kb / "doc.md"
    f.write_text("x")
    nid = _add(ix, "knowledge", f)
    assert ix._delete_nodes("knowledge", [nid, "not-held"]) == 1
    assert not ix.indices["knowledge"].docstore.document_exists(nid)
    assert nid not in ix._vector_ids(ix.indices["knowledge"])


def test_reconcile_removes_what_must_not_be_retrievable(indexer):
    ix, kb = indexer
    live = kb / "news" / "brief.md"
    live.parent.mkdir()
    live.write_text("x")
    backup = kb / "user_logs" / ".compacted_backup" / "forum_A_1" / "post_history.md"
    backup.parent.mkdir(parents=True)
    backup.write_text("x")

    keep = _add(ix, "knowledge", live)
    gone = _add(ix, "dreams", kb / "kaia_dreams" / "deleted.md")
    excluded = _add(ix, "logs", backup)
    persona = _add(ix, "knowledge", kb / "kaia_persona.md")
    feedback = TextNode(text="User Query: hi\nKaia Response: hello", metadata={"source": "feedback"})
    ix.indices["logs"].insert_nodes([feedback])
    ghost = _add(ix, "knowledge", live)
    ix.indices["knowledge"].delete_nodes([ghost])  # the old default: docstore keeps it

    changed = ix._reconcile_indices()

    assert changed == {"knowledge", "dreams", "logs"}
    held = {n for idx in ix.indices.values() for n in idx.docstore.docs}
    assert held == {keep}
    for nid in (gone, excluded, persona, feedback.node_id, ghost):
        assert nid not in held
    assert ix._reconcile_indices() == set()


def test_a_forum_profile_is_scanned_but_the_post_history_is_not(indexer):
    ix, kb = indexer
    d = kb / "user_logs" / "forum_Videri_125307"
    d.mkdir(parents=True)
    (d / "user_profile.md").write_text("profile")
    (d / "post_history.md").write_text("history")
    found = {os.path.basename(p): itype for p, _, _, itype in ix._find_changed_files()}
    assert found == {"user_profile.md": "user_profiles"}


def test_log_tail_uses_bytes_and_indexes_each_turn_once(indexer):
    ix, kb = indexer
    log = kb / "user_logs" / "Ekco_1" / "interactions_20260922.md"
    log.parent.mkdir(parents=True)
    log.write_text("[2026-09-22 01:00:00] Ekco: it’s “curly” — twice’s the charm\n", encoding="utf-8")
    assert ix._index_log_tail(str(log), str(log), "logs")
    with open(log, "a", encoding="utf-8") as f:
        f.write("[2026-09-22 01:05:00] Kaia: a second turn\n")
    assert ix._index_log_tail(str(log), str(log), "logs")

    texts = "\n".join(n.text for n in ix.indices["logs"].docstore.docs.values())
    assert texts.count("curly") == 1
    assert texts.count("a second turn") == 1
    entry = ix.indexed_files[str(log)]
    assert entry["indexed_bytes"] == os.path.getsize(log)
    assert entry["indexed_prefix_sha1"] == hashlib.sha1(log.read_bytes()).hexdigest()


def test_a_log_rewritten_in_place_is_reindexed_from_the_start(indexer):
    ix, kb = indexer
    log = kb / "user_logs" / "Ekco_1" / "interactions_20260922.md"
    log.parent.mkdir(parents=True)
    log.write_text("[2026-09-22 01:00:00] Kaia: the wrong answer, at length\n")
    ix._index_log_tail(str(log), str(log), "logs")
    log.write_text("[2026-09-22 01:00:00] Kaia: the right one\n")  # shorter: a correction
    assert ix._index_log_tail(str(log), str(log), "logs")

    texts = [n.text for n in ix.indices["logs"].docstore.docs.values()]
    assert any("the right one" in t for t in texts)
    assert not any("wrong answer" in t for t in texts)


def test_turns_split_on_multi_word_speakers():
    text = ("[2026-09-01 10:00:00] Tenno Henka: hi there\n"
            "[2026-09-01 10:00:05] Kaia: hello\n")
    nodes = ConversationTurnSplitter(turns_per_chunk=1, overlap_turns=0).get_nodes_from_documents(
        [Document(text=text)])
    assert [n.text.split("] ")[1].split(":")[0] for n in nodes] == ["Tenno Henka", "Kaia"]


def test_pre_chunking_cuts_between_paragraphs(indexer):
    ix, _ = indexer
    paragraph = "A sentence about the moon and its orbit. " * 20
    doc = Document(text="\n\n".join([paragraph.strip()] * 12))
    pieces = ix._pre_chunk_document(doc, chunk_size=4000)
    assert len(pieces) > 1
    for p in pieces[:-1]:
        assert p.text.endswith("\n\n")
    assert "".join(p.text for p in pieces) == doc.text


def test_only_descriptive_metadata_is_embedded():
    node = TextNode(text="body", metadata={
        "title": "Tidal Locking", "file_path": "/abs/path.md", "priority": 0.5,
        "timestamp": 1788570600.0, "quality_score": 0.3})
    RAGIndexerMixin._prepare_nodes([node])
    embedded = node.get_content(metadata_mode=MetadataMode.EMBED)
    assert "Tidal Locking" in embedded
    assert "/abs/path.md" not in embedded and "priority" not in embedded


def test_clear_removes_the_index_and_keeps_runtime_state(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("reindex_rag_under_test",
                                                  "tools/maintenance/reindex_rag.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    store = tmp_path / "memory" / "rag_storage"
    (store / "knowledge").mkdir(parents=True)
    (store / "knowledge" / "docstore.json").write_text("{}")
    (store / "file_manifest.json").write_text("{}")
    (store / "dream_history.json").write_text('{"kept": true}')
    (store / "kaia_continuity.md").write_text("kept")

    monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_bot_running", lambda: False)
    monkeypatch.setenv("KAIA_EMBED_GPU", "")  # the rebuild sets it; restored after

    class _Stop(Exception):
        pass

    def _no_rag(*a, **k):
        raise _Stop

    monkeypatch.setattr(mod, "KaiaRAG", _no_rag)
    import asyncio
    with pytest.raises(SystemExit):
        asyncio.run(mod.rebuild_rag(clear_storage=True))

    assert sorted(p.name for p in store.iterdir()) == ["dream_history.json", "kaia_continuity.md"]


def test_the_news_quick_reference_is_not_indexed():
    """It condenses the same day's brief and carries no date of its own."""
    assert RAGIndexerMixin._is_excluded_path("/kb/news/daily/news_summary_20260915.md")
    assert not RAGIndexerMixin._is_excluded_path("/kb/news/daily/news_brief_20260915.md")


def test_a_failed_news_day_is_not_filled_with_yesterdays_brief():
    from pathlib import Path
    src = Path("tools/maintenance/update_kaia_news.py").read_text(encoding="utf-8")
    assert "FALLBACK from" not in src


@pytest.mark.parametrize("name,day", [
    ("news_brief_20260614.md", (2026, 6, 14)),
    ("tech_digest_20260922.md", (2026, 9, 22)),
    ("dream_20260728_030425_dream_20260315_035630_dream_20.md", (2026, 7, 28)),
])
def test_news_and_dreams_are_dated_by_their_name(name, day):
    from datetime import datetime
    ts = RAGIndexerMixin._dated_filename_ts(f"/kb/x/{name}")
    assert datetime.fromtimestamp(ts).timetuple()[:3] == day


def test_other_documents_keep_their_mtime():
    assert RAGIndexerMixin._dated_filename_ts("/kb/books/Book - 1984 by George Orwell.md") is None
    assert RAGIndexerMixin._dated_filename_ts("/kb/documents/AI - Report 20260101.md") is None


def test_a_question_about_the_news_retrieves_news():
    from utils.core.message_processor import _NEWS_CUE
    assert _NEWS_CUE.search("what's the latest news on Iran")
    assert _NEWS_CUE.search("any headlines?")
    assert not _NEWS_CUE.search("what's new with you")
    assert not _NEWS_CUE.search("newsletter from the guild")


def test_logging_keeps_the_users_bracketed_words():
    """User turns are never rewritten; the placeholder strip is for her replies."""
    from utils.core.kaia_rag_retriever import sanitize_log_content
    assert sanitize_log_content("[EDIT] fixed it [USER_MESSAGE] ok", users_words=True) == "[EDIT] fixed it ok"
    assert sanitize_log_content("see [IMAGE] here") == "see here"


def test_a_converted_pdf_is_not_retried_every_sweep(indexer, monkeypatch):
    """The original was recorded with size 0, and the scan reads any size
    change as an edit, so every sweep failed on it and converted it again."""
    ix, kb = indexer
    pdf = kb / "documents" / "paper.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF-1.4 not really a pdf")
    monkeypatch.setattr(ix, "_convert_pdf_to_md", lambda p: str(pdf.with_suffix(".md")))
    ix._handle_corrupt_file(str(pdf), "knowledge", str(kb / "_quarantine"))
    assert str(pdf.resolve()) not in {os.path.abspath(p) for p, *_ in ix._find_changed_files()}


def test_a_write_during_indexing_is_picked_up_next_sweep(indexer, monkeypatch):
    """The file's mtime and size were read after its text, so a write between
    the two was recorded as indexed and never re-read."""
    ix, kb = indexer
    doc = kb / "documents" / "notes.md"
    doc.parent.mkdir()
    doc.write_text("first version")
    old_mtime = os.path.getmtime(doc)
    import llama_index.core as li
    real_reader = li.SimpleDirectoryReader

    class ReadThenWrite:
        def __init__(self, **kw):
            self.inner = real_reader(**kw)

        def load_data(self):
            docs = self.inner.load_data()
            doc.write_text("second version, written while the first was indexing")
            os.utime(doc, (old_mtime + 5, old_mtime + 5))
            return docs
    monkeypatch.setattr(li, "SimpleDirectoryReader", ReadThenWrite)
    ix._index_regular_file(str(doc), str(doc.resolve()), "knowledge")
    assert str(doc.resolve()) in {os.path.abspath(p) for p, *_ in ix._find_changed_files()}


def _node(method, source="general_knowledge", score=0.85):
    return {"content": "x", "score": score, "metadata": {"retrieval_method": method, "source_type": source}}


def test_padding_is_dropped_on_an_ordinary_turn():
    from utils.core.kaia_rag_query import without_padding
    nodes = [_node("hybrid", score=1.2), _node("vector"), _node("vector"), _node("vector", source="user_logs")]
    kept = without_padding(nodes, "how e's are in strawberry")
    assert [n["metadata"]["retrieval_method"] for n in kept] == ["hybrid", "vector"]
    assert kept[1]["metadata"]["source_type"] == "user_logs", "her conversations stay"


def test_a_question_keeps_the_nearest_two():
    from utils.core.kaia_rag_query import VECTOR_ONLY_ON_A_QUESTION, without_padding
    nodes = [_node("bm25", score=1.2)] + [_node("vector") for _ in range(5)]
    kept = without_padding(nodes, "what is the answer to everything?")
    assert len(kept) == 1 + VECTOR_ONLY_ON_A_QUESTION


def test_nothing_is_dropped_when_keyword_search_found_nothing_or_a_document_was_asked_for():
    from utils.core.kaia_rag_query import without_padding
    only_vector = [_node("vector") for _ in range(4)]
    assert without_padding(only_vector, "statement") == only_vector, "keyword search may be down"
    mixed = [_node("hybrid"), _node("vector")]
    assert without_padding(mixed, "statement", strategy="PRECISE_RECALL") == mixed
    assert without_padding(mixed, "statement", strategy="SUMMARIZATION") == mixed



def test_partial_index_persist_does_not_advance_the_global_manifest(tmp_path, indexer, monkeypatch):
    """A stale index snapshot must not inherit the new file mtime from the manifest."""
    import json

    ix, _ = indexer
    ix.persist_dir = str(tmp_path / "rag_storage")
    ix.state_file = os.path.join(ix.persist_dir, "file_manifest.json")
    os.makedirs(ix.persist_dir)

    old_manifest = {
        "/kb/document.md": {"mtime": 10, "size": 5, "nodes": ["old-node"], "itype": "knowledge"}
    }
    with open(ix.state_file, "w", encoding="utf-8") as f:
        json.dump(old_manifest, f)

    # In-memory indexing has already seen the new file version, but the logs
    # index snapshot fails while knowledge succeeds.
    ix.indexed_files = {
        "/kb/document.md": {"mtime": 20, "size": 15, "nodes": ["new-node"], "itype": "knowledge"}
    }

    def persist_one(itype):
        if itype == "logs":
            raise OSError("disk full")
    monkeypatch.setattr(ix, "_persist_index_atomic", persist_one, raising=False)

    persisted = ix._persist_updated_indices({"knowledge", "logs"})

    assert persisted == {"knowledge"}
    with open(ix.state_file, encoding="utf-8") as f:
        assert json.load(f) == old_manifest


def test_complete_index_persist_advances_the_manifest(tmp_path, indexer, monkeypatch):
    """The manifest is still committed once every affected index reached disk."""
    import json

    ix, _ = indexer
    ix.persist_dir = str(tmp_path / "rag_storage")
    ix.state_file = os.path.join(ix.persist_dir, "file_manifest.json")
    os.makedirs(ix.persist_dir)
    ix.indexed_files = {
        "/kb/document.md": {"mtime": 20, "size": 15, "nodes": ["new-node"], "itype": "knowledge"}
    }
    monkeypatch.setattr(ix, "_persist_index_atomic", lambda _itype: None, raising=False)

    persisted = ix._persist_updated_indices({"knowledge", "logs"})

    assert persisted == {"knowledge", "logs"}
    with open(ix.state_file, encoding="utf-8") as f:
        assert json.load(f) == ix.indexed_files



def test_pruning_defers_manifest_until_changed_indices_persist(tmp_path, indexer, monkeypatch):
    """Deleting file nodes must not commit a manifest that outruns disk snapshots."""
    import json

    ix, kb = indexer
    ix.persist_dir = str(tmp_path / "rag_storage")
    ix.state_file = os.path.join(ix.persist_dir, "file_manifest.json")
    os.makedirs(ix.persist_dir)
    deleted = str((kb / "documents" / "deleted.md").resolve())
    old_manifest = {
        deleted: {"mtime": 10, "size": 5, "nodes": ["old-node"], "itype": "knowledge"}
    }
    with open(ix.state_file, "w", encoding="utf-8") as f:
        json.dump(old_manifest, f)

    ix.indexed_files = dict(old_manifest)
    ix._file_to_nodes = {deleted: ["old-node"]}
    ix.indices = {"knowledge": object()}
    monkeypatch.setattr(ix, "_delete_nodes", lambda _itype, _ids: 1, raising=False)
    def fail_persist(_itype):
        raise OSError("disk full")
    monkeypatch.setattr(ix, "_persist_index_atomic", fail_persist, raising=False)

    changed = ix._prune_deleted_files()
    assert changed == {"knowledge"}
    assert ix.indexed_files == {}
    with open(ix.state_file, encoding="utf-8") as f:
        assert json.load(f) == old_manifest

    persisted = ix._persist_updated_indices(changed)
    assert persisted == set()
    with open(ix.state_file, encoding="utf-8") as f:
        assert json.load(f) == old_manifest


def test_pruning_manifest_only_entries_still_saves_without_index_writes(tmp_path, indexer, monkeypatch):
    """Manifest cleanup with no index nodes to delete is safe to commit immediately."""
    import json

    ix, kb = indexer
    ix.persist_dir = str(tmp_path / "rag_storage")
    ix.state_file = os.path.join(ix.persist_dir, "file_manifest.json")
    os.makedirs(ix.persist_dir)
    deleted = str((kb / "documents" / "deleted.md").resolve())
    old_manifest = {
        deleted: {"mtime": 10, "size": 5, "nodes": [], "itype": "knowledge"}
    }
    with open(ix.state_file, "w", encoding="utf-8") as f:
        json.dump(old_manifest, f)

    ix.indexed_files = dict(old_manifest)
    ix.indices = {"knowledge": object()}
    monkeypatch.setattr(ix, "_delete_nodes", lambda _itype, _ids: 0, raising=False)

    changed = ix._prune_deleted_files()

    assert changed == set()
    with open(ix.state_file, encoding="utf-8") as f:
        assert json.load(f) == {}



def test_failed_modified_document_keeps_old_nodes_and_manifest(indexer, monkeypatch, tmp_path):
    """A parse failure must leave the last-good nodes searchable and the source in place."""
    ix, kb = indexer
    doc = kb / "documents" / "notes.md"
    doc.parent.mkdir()
    doc.write_text("old indexed document")
    old_mtime = os.path.getmtime(doc)
    old_stat = os.stat(doc)
    old_node = _add(ix, "knowledge", doc, "old indexed document")
    abs_path = str(doc.resolve())
    old_entry = {"mtime": old_stat.st_mtime, "size": old_stat.st_size, "nodes": [old_node], "itype": "knowledge"}
    ix.indexed_files[abs_path] = dict(old_entry)
    doc.write_text("replacement content that cannot be parsed")
    os.utime(doc, (old_mtime + 5, old_mtime + 5))
    monkeypatch.setattr(ix, "_get_node_parser_for_doc", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("parser failure")))

    assert ix._index_single_file(str(doc), True, False, "knowledge", str(kb / "_quarantine" / "corrupt_files")) is False
    assert doc.exists()
    assert ix.indices["knowledge"].docstore.document_exists(old_node)
    assert old_node in ix._vector_ids(ix.indices["knowledge"])
    assert ix.indexed_files[abs_path] == old_entry


def test_failed_log_rewrite_keeps_old_nodes_and_manifest(indexer, monkeypatch):
    """A failed full-log rebuild must not delete the last-good transcript chunks."""
    ix, kb = indexer
    log = kb / "user_logs" / "Ekco_1" / "interactions_20260922.md"
    log.parent.mkdir(parents=True)
    log.write_text("[2026-09-22 01:00:00] Kaia: original long answer to preserve\n")
    assert ix._index_log_tail(str(log), str(log), "logs")
    abs_path = str(log.resolve())
    old_entry = dict(ix.indexed_files[abs_path])
    old_nodes = list(old_entry["nodes"])
    log.write_text("[2026-09-22 01:00:00] Kaia: corrected\n")
    monkeypatch.setattr(ix, "_get_node_parser_for_doc", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("parser failure")))

    assert ix._index_single_file(str(log), True, True, "logs", str(kb / "_quarantine" / "corrupt_files")) is False
    assert all(ix.indices["logs"].docstore.document_exists(n) for n in old_nodes)
    assert ix.indexed_files[abs_path] == old_entry


def test_partial_old_node_delete_keeps_new_replacement_and_retries_leftovers(indexer, monkeypatch):
    """A partial backend delete must not roll back the new version and lose both."""
    ix, kb = indexer
    doc = kb / "documents" / "partial-delete.md"
    doc.parent.mkdir()
    doc.write_text("new replacement document content")
    old_one = _add(ix, "knowledge", doc, "old version one")
    old_two = _add(ix, "knowledge", doc, "old version two")
    abs_path = str(doc.resolve())
    stat = os.stat(doc)
    ix.indexed_files[abs_path] = {
        "mtime": stat.st_mtime - 10, "size": stat.st_size - 3,
        "nodes": [old_one, old_two], "itype": "knowledge",
    }
    original_delete = ix._delete_nodes
    def partially_delete_old(itype, node_ids):
        ids = list(node_ids)
        if old_one in ids and old_two in ids:
            original_delete(itype, [old_one])
            raise OSError("simulated partial docstore/vector delete")
        return original_delete(itype, ids)
    monkeypatch.setattr(ix, "_delete_nodes", partially_delete_old)

    assert ix._index_single_file(str(doc), True, False, "knowledge", str(kb / "_quarantine" / "corrupt_files"))
    entry = ix.indexed_files[abs_path]
    assert entry["nodes"]
    assert entry["stale_nodes"] == [old_two]
    stale_node = ix.indices["knowledge"].docstore.get_node(old_two)
    assert stale_node.metadata["_rag_replacement_stale"] is True
    assert "_rag_replacement_stale" in stale_node.excluded_llm_metadata_keys
    assert "_rag_replacement_stale" in stale_node.excluded_embed_metadata_keys
    assert not ix.indices["knowledge"].docstore.document_exists(old_one)
    assert ix.indices["knowledge"].docstore.document_exists(old_two)
    assert all(ix.indices["knowledge"].docstore.document_exists(n) for n in entry["nodes"])
    assert any("new replacement" in ix.indices["knowledge"].docstore.get_node(n).text for n in entry["nodes"])

    monkeypatch.setattr(ix, "_delete_nodes", original_delete)
    changed, manifest_changed = ix._cleanup_stale_file_nodes()
    assert changed == {"knowledge"}
    assert manifest_changed
    assert "stale_nodes" not in ix.indexed_files[abs_path]
    assert not ix.indices["knowledge"].docstore.document_exists(old_two)


def test_manifest_rebuild_preserves_stale_replacement_marker(indexer):
    """A restart must not turn leftover old nodes back into active content."""
    ix, kb = indexer
    doc = kb / "documents" / "restart-marker.md"
    doc.parent.mkdir()
    doc.write_text("content")
    active = _add(ix, "knowledge", doc, "current indexed content")
    stale = _add(ix, "knowledge", doc, "superseded old content")
    abs_path = str(doc.resolve())
    stat = os.stat(doc)
    ix._mark_nodes_stale("knowledge", [stale])
    # Simulate a crash after index snapshot persistence but before the global
    # manifest could commit: the per-node marker is the recovery authority.
    ix.indexed_files = {}
    ix._populate_indexed_files()
    assert ix.indexed_files[abs_path]["nodes"] == [active]
    assert ix.indexed_files[abs_path]["stale_nodes"] == [stale]


def test_ingestion_history_failure_does_not_turn_index_success_into_failure(indexer, monkeypatch):
    """Ancillary telemetry failure must not trigger manifest-only persistence."""
    from utils.infrastructure.system.bot_state import bot_state
    ix, kb = indexer
    doc = kb / "documents" / "history-write.md"
    doc.parent.mkdir()
    doc.write_text("document that should still be indexed")
    monkeypatch.setattr(bot_state, "add_ingestion", lambda *_a, **_k: (_ for _ in ()).throw(OSError("history disk failure")))
    assert ix._index_single_file(str(doc), False, False, "knowledge", str(kb / "_quarantine" / "corrupt_files"))
    entry = ix.indexed_files[str(doc.resolve())]
    assert entry["nodes"]
    assert all(ix.indices["knowledge"].docstore.document_exists(n) for n in entry["nodes"])



def test_partial_new_insert_rollback_is_tracked_and_forces_full_reindex(indexer, monkeypatch):
    """A partially inserted failed replacement is marked stale and retried after restart."""
    from llama_index.core.schema import TextNode

    ix, kb = indexer
    doc = kb / "documents" / "partial-insert.md"
    doc.parent.mkdir()
    doc.write_text("new content")
    old = _add(ix, "knowledge", doc, "last good content")
    abs_path = str(doc.resolve())
    stat = os.stat(doc)
    ix.indexed_files[abs_path] = {
        "mtime": stat.st_mtime - 5, "size": stat.st_size - 1,
        "nodes": [old], "itype": "knowledge",
    }

    class TwoNodeParser:
        def get_nodes_from_documents(self, documents):
            return [
                TextNode(text="new partial node one", metadata=dict(documents[0].metadata)),
                TextNode(text="new partial node two", metadata=dict(documents[0].metadata)),
            ]

    monkeypatch.setattr(ix, "_get_node_parser_for_doc", lambda *_a, **_k: TwoNodeParser())
    target = ix.indices["knowledge"]
    original_insert = target.insert_nodes
    def partial_insert(nodes):
        prepared = list(nodes)
        original_insert([prepared[0]])
        raise OSError("simulated second vector insert failure")
    monkeypatch.setattr(target, "insert_nodes", partial_insert)
    original_delete_nodes = ix._delete_nodes
    monkeypatch.setattr(ix, "_delete_nodes", lambda *_a, **_k: (_ for _ in ()).throw(OSError("rollback failed")))

    assert ix._index_single_file(
        str(doc), True, False, "knowledge", str(kb / "_quarantine" / "corrupt_files")
    )
    entry = ix.indexed_files[abs_path]
    assert entry["nodes"] == [old]
    assert entry["reindex_required"] is True
    assert len(entry["stale_nodes"]) == 1
    assert ix.indices["knowledge"].docstore.document_exists(old)
    assert ix.indices["knowledge"].docstore.get_node(old).metadata["_rag_reindex_required"] is True
    partial = entry["stale_nodes"][0]
    assert ix.indices["knowledge"].docstore.get_node(partial).metadata["_rag_replacement_stale"] is True
    assert ix.indices["knowledge"].docstore.get_node(partial).metadata["_rag_reindex_required"] is True

    # Simulate a restart where the file-manifest commit was not reached.
    ix.indexed_files = {}
    ix._populate_indexed_files()
    rebuilt = ix.indexed_files[abs_path]
    assert rebuilt["nodes"] == [old]
    assert rebuilt["stale_nodes"] == [partial]
    assert rebuilt["reindex_required"] is True

    # A rollback may remove the partial node from the docstore but leave its
    # vector behind. In that state only the last-good node's durable
    # reindex-required marker can rediscover the source after manifest loss.
    index = ix.indices["knowledge"]
    index.docstore.delete_document(partial, raise_error=False)
    assert not index.docstore.document_exists(partial)
    assert partial in ix._vector_ids(index)

    ix.indexed_files = {}
    ix._populate_indexed_files()
    rebuilt_again = ix.indexed_files[abs_path]
    assert rebuilt_again["nodes"] == [old]
    assert rebuilt_again["reindex_required"] is True
    assert rebuilt_again.get("stale_nodes", []) == []

    # Reconciliation removes the orphaned vector; restore the real delete
    # helper after the simulated rollback failure has been exercised.
    monkeypatch.setattr(ix, "_delete_nodes", original_delete_nodes)
    # The marked active node still makes the unchanged source due for a rebuild.
    changed = ix._reconcile_indices()
    assert "knowledge" in changed
    assert partial not in ix._vector_ids(index)
    due = ix._find_changed_files()
    assert any(os.path.abspath(item[0]) == abs_path for item in due)





def test_partial_log_insert_rollback_is_tracked_and_retried_as_full_rewrite(indexer, monkeypatch):
    """A partial insert in a rewritten log must not duplicate or supersede last-good turns."""
    from llama_index.core.schema import TextNode

    ix, kb = indexer
    log = kb / "user_logs" / "Ekco_1" / "interactions_20260922.md"
    log.parent.mkdir(parents=True)
    log.write_text("[2026-09-22 01:00:00] Kaia: last good answer to preserve\n")
    assert ix._index_log_tail(str(log), str(log), "logs")
    abs_path = str(log.resolve())
    old_nodes = list(ix.indexed_files[abs_path]["nodes"])

    log.write_text("[2026-09-22 01:05:00] Kaia: corrected replacement answer\n")

    class TwoNodeParser:
        def get_nodes_from_documents(self, documents):
            return [
                TextNode(text="partial corrected log chunk one", metadata=dict(documents[0].metadata)),
                TextNode(text="partial corrected log chunk two", metadata=dict(documents[0].metadata)),
            ]

    original_parser = ix._get_node_parser_for_doc
    monkeypatch.setattr(ix, "_get_node_parser_for_doc", lambda *_a, **_k: TwoNodeParser())
    index = ix.indices["logs"]
    original_insert = index.insert_nodes
    original_delete = ix._delete_nodes

    def partial_insert(nodes):
        prepared = list(nodes)
        original_insert([prepared[0]])
        raise OSError("simulated second log chunk insertion failure")

    monkeypatch.setattr(index, "insert_nodes", partial_insert)
    monkeypatch.setattr(ix, "_delete_nodes", lambda *_a, **_k: (_ for _ in ()).throw(OSError("rollback failed")))

    assert ix._index_single_file(
        str(log), True, True, "logs", str(kb / "_quarantine" / "corrupt_files")
    )
    entry = ix.indexed_files[abs_path]
    partial_node_id = entry["stale_nodes"][0]
    assert entry["nodes"] == old_nodes
    assert entry["reindex_required"] is True
    assert len(entry["stale_nodes"]) == 1
    assert all(index.docstore.document_exists(node_id) for node_id in old_nodes)

    # The retry must rebuild the full log (not append from EOF), then remove both
    # the last-good old nodes and the partial attempted replacement.
    monkeypatch.setattr(index, "insert_nodes", original_insert)
    monkeypatch.setattr(ix, "_delete_nodes", original_delete)
    monkeypatch.setattr(ix, "_get_node_parser_for_doc", original_parser)
    assert ix._index_log_tail(str(log), str(log), "logs")
    new_entry = ix.indexed_files[abs_path]
    assert "reindex_required" not in new_entry
    assert "stale_nodes" not in new_entry
    assert all(not index.docstore.document_exists(node_id) for node_id in old_nodes)
    assert not index.docstore.document_exists(partial_node_id)
    assert any(
        "corrected replacement answer" in index.docstore.get_node(node_id).text
        for node_id in new_entry["nodes"]
    )
    texts = "\n".join(index.docstore.get_node(node_id).text for node_id in new_entry["nodes"])
    assert "partial corrected log chunk one" not in texts



def test_stale_replacement_nodes_are_excluded_from_normal_scoring_and_dedup(indexer):
    from llama_index.core.schema import NodeWithScore

    ix, kb = indexer
    path = str((kb / "same.md").resolve())
    stale = TextNode(text="identical current source content", metadata={
        "file_path": path, "source_type": "general_knowledge", "_rag_replacement_stale": True,
    })
    active = TextNode(text="identical current source content", metadata={
        "file_path": path, "source_type": "general_knowledge",
    })
    stale.excluded_llm_metadata_keys = ["_rag_replacement_stale"]
    stale.excluded_embed_metadata_keys = ["_rag_replacement_stale"]
    active.excluded_llm_metadata_keys = []
    active.excluded_embed_metadata_keys = []

    # Supply authoritative docstore entries: scoring now fails closed for
    # vector candidates that cannot be found in any active docstore.
    ix.indices["knowledge"].insert_nodes([stale, active])
    ix._mark_nodes_stale("knowledge", [stale.node_id])

    rag = RAGQueryMixin()
    rag.indices = ix.indices
    rag.indexed_files = {
        path: {"nodes": [active.node_id], "stale_nodes": [stale.node_id], "itype": "knowledge"}
    }
    out = rag._score_and_filter_nodes(
        [NodeWithScore(node=stale, score=1.5), NodeWithScore(node=active, score=1.0)],
        "current source?",
        set(),
        {
            "strategy": None, "is_casual": False, "is_dream_query": False,
            "is_social_identity": False, "is_entity_query": False, "is_news_query": False,
        },
        10, False, False,
    )
    assert len(out) == 1
    assert out[0]["node_id"] == active.node_id


def test_summarization_docstore_fallback_never_returns_stale_only_nodes(indexer):
    ix, kb = indexer
    path = str((kb / "documents" / "stale-only.md").resolve())
    doc = kb / "documents" / "stale-only.md"
    doc.parent.mkdir()
    doc.write_text("last failed partial replacement")
    stale = TextNode(text="partial uncommitted replacement text", metadata={
        "file_path": path, "source_type": "general_knowledge", "_rag_replacement_stale": True,
    })
    ix.indices["knowledge"].insert_nodes([stale])

    rag = RAGQueryMixin()
    rag.indices = {"knowledge": ix.indices["knowledge"]}
    rag.indexed_files = {
        path: {"mtime": os.path.getmtime(path), "size": os.path.getsize(path),
               "nodes": [], "stale_nodes": [stale.node_id], "itype": "knowledge"}
    }
    assert rag._get_summarization_nodes("stale-only.md", target_path=path) == []


def test_recent_event_and_highlight_docstore_scans_skip_stale_log_nodes(indexer):
    import time

    ix, kb = indexer
    path = str((kb / "user_logs" / "Ekco_1" / "interactions_20261104.md").resolve())
    stale = TextNode(
        text="unique_stale_marker should never be returned in a recent event",
        metadata={"file_path": path, "timestamp": time.time(), "_rag_replacement_stale": True},
    )
    active = TextNode(
        text="a valid recent log entry that should remain",
        metadata={"file_path": path, "timestamp": time.time()},
    )
    ix.indices["logs"].insert_nodes([stale, active])

    rag = RAGQueryMixin()
    rag.indices = {"logs": ix.indices["logs"]}
    highlights = rag.get_recent_highlights(hours=24, limit=20)
    assert all("unique_stale_marker" not in text for text in highlights)
    searched = rag.search_recent_events("unique_stale_marker", hours=24, limit=20)
    assert not any("unique_stale_marker" in item["content"] for item in searched)



@pytest.mark.asyncio
async def test_bm25_warmup_does_not_index_stale_replacement_nodes(indexer):
    """Stale docstore entries must not crowd current nodes out of BM25 top-k."""
    from utils.core.kaia_rag_query import RAGQueryMixin

    ix, kb = indexer
    path = str((kb / "bm25-stale.md").resolve())
    stale = _add(ix, "knowledge", kb / "bm25-stale.md", "old unique stale replacement phrase")
    active = _add(ix, "knowledge", kb / "bm25-stale.md", "current unique active replacement phrase")
    ix._mark_nodes_stale("knowledge", [stale])

    query = RAGQueryMixin.__new__(RAGQueryMixin)
    query.indices = ix.indices
    query.bm25_cache = {}
    await query.pre_warm()

    nodes = query.bm25_cache["knowledge"].nodes
    assert [node.node_id for node in nodes] == [active]



def test_marking_stale_nodes_invalidates_cached_bm25_and_rejects_detached_candidates(indexer):
    """A BM25 node copy created before marker persistence cannot re-enter retrieval."""
    from llama_index.core.schema import TextNode
    from utils.core.kaia_rag_query import RAGQueryMixin

    ix, kb = indexer
    doc = kb / "documents" / "cached-stale.md"
    doc.parent.mkdir()
    doc.write_text("current source")
    stale_id = _add(ix, "knowledge", doc, "superseded cached node content")

    detached = TextNode(
        id_=stale_id,
        text="superseded cached node content",
        metadata={"file_path": str(doc.resolve()), "source_type": "general_knowledge"},
    )
    ix.bm25_cache["knowledge"] = type("Cached", (), {"nodes": [detached]})()

    ix._mark_nodes_stale("knowledge", [stale_id])

    assert "knowledge" not in ix.bm25_cache
    query = RAGQueryMixin.__new__(RAGQueryMixin)
    query.indices = ix.indices
    query.indexed_files = {
        str(doc.resolve()): {"nodes": [], "stale_nodes": [stale_id], "itype": "knowledge"}
    }
    assert query._is_stale_replacement_node(detached)

    # If the manifest was also lost and a partial vector survives without its
    # docstore node, the scoring gate must still reject the orphan by ID.
    index = ix.indices["knowledge"]
    index.docstore.delete_document(stale_id, raise_error=False)
    assert stale_id in ix._vector_ids(index)
    query.indexed_files = {}
    assert query._is_stale_replacement_node(detached)

def test_partial_snapshot_persist_failure_is_retried_on_same_process_refresh(
    indexer, monkeypatch
):
    """A failed index snapshot remains dirty even when the next scan finds no changed files."""
    import json

    ix, kb = indexer
    doc = kb / "documents" / "durability.md"
    doc.parent.mkdir()
    doc.write_text("new document version")
    path = str(doc.resolve())
    ix.indexed_files[path] = {
        "mtime": os.path.getmtime(path),
        "size": os.path.getsize(path),
        "nodes": ["new-node"],
        "itype": "knowledge",
    }
    old_manifest = {path: {
        "mtime": 1, "size": 1, "nodes": ["old-node"], "itype": "knowledge"
    }}
    with open(ix.state_file, "w", encoding="utf-8") as handle:
        json.dump(old_manifest, handle)

    writes = []
    def fail_logs_once(itype):
        writes.append(itype)
        if itype == "logs" and writes.count("logs") == 1:
            raise OSError("simulated full disk")

    monkeypatch.setattr(ix, "_persist_index_atomic", fail_logs_once, raising=False)
    persisted = ix._persist_updated_indices({"knowledge", "logs"})

    assert persisted == {"knowledge"}
    assert ix._get_pending_index_persist_types() == {"knowledge", "logs"}
    with open(ix.state_file, encoding="utf-8") as handle:
        assert json.load(handle) == old_manifest

    # The follow-up refresh intentionally sees no changed files. It still has
    # to retry the pending snapshots before it may report a successful sweep.
    ix._index_lock = threading.Lock()
    ix._refresh_pending = False
    ix._indexing_in_progress = False
    monkeypatch.setattr(ix, "_prune_deleted_files", lambda: set())
    monkeypatch.setattr(ix, "_reconcile_indices", lambda: set())
    monkeypatch.setattr(ix, "_cleanup_stale_file_nodes", lambda: (set(), False))
    monkeypatch.setattr(ix, "_find_changed_files", lambda: [])
    monkeypatch.setattr(ix, "_persist_index_atomic", lambda itype: writes.append(f"retry:{itype}"))

    assert asyncio.run(ix.refresh_knowledge_base()) is True
    assert "retry:knowledge" in writes and "retry:logs" in writes
    assert ix._get_pending_index_persist_types() == set()
    with open(ix.state_file, encoding="utf-8") as handle:
        assert json.load(handle) == ix.indexed_files


def test_failed_persist_does_not_advance_in_memory_pending_state_until_complete(
    indexer, monkeypatch
):
    ix, _ = indexer
    calls = []
    def partial(itype):
        calls.append(itype)
        if itype == "dreams":
            raise OSError("snapshot unavailable")
    monkeypatch.setattr(ix, "_persist_index_atomic", partial, raising=False)
    monkeypatch.setattr(ix, "_save_indexed_files", lambda: pytest.fail(
        "manifest must not be committed after a partial snapshot batch"
    ))

    assert ix._persist_updated_indices({"knowledge", "dreams"}) == {"knowledge"}
    assert ix._get_pending_index_persist_types() == {"knowledge", "dreams"}

