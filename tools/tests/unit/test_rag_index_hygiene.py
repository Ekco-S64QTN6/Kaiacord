"""What leaves the index actually leaves it, and what goes in is indexed once.

A September 2026 audit of the live index found 70% of the knowledge docstore
was deleted content still searchable by BM25, 3,345 dream vectors from files
that no longer existed, 3,852 copies of old persona text, forum profiles never
refreshed, and log turns indexed twice on any file with a curly quote.
"""
import hashlib
import os
import threading

import pytest
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import MetadataMode, TextNode

from utils.core.kaia_rag_indexer import ConversationTurnSplitter, RAGIndexerMixin


class _Indexer(RAGIndexerMixin):
    def __init__(self, kb_dir):
        self.knowledge_base_dir = str(kb_dir)
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
