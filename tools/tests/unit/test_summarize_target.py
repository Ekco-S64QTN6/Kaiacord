"""Which document a summarise request reads.

On 4 Oct a transcript dropped into knowledge_base/transcripts/ four minutes
earlier was asked for by its exact name. The index had not reached it, the
word-overlap fallback matched "transcript" + "linux" to a different
transcript, and she summarised a document she had never read under the name
asked for.
"""
import utils.core.kaia_rag_query as rq
from utils.core.context_optimizer import ContextOptimizer


def _query(kb, indexed=None):
    o = rq.RAGQueryMixin.__new__(rq.RAGQueryMixin)
    o.indices, o.knowledge_base_dir = {}, str(kb)
    o.indexed_files = indexed or {}
    return o


def _kb(tmp_path):
    t = tmp_path / "transcripts"
    t.mkdir()
    (t / "Transcript - Linux Threat Hunting - PSW 942.md").write_text("threat hunting talk\n")
    new = t / "Transcript - Linux Update October 2026.md"
    new.write_text("\n\n".join(f"paragraph {i} about market share" for i in range(400)))
    return tmp_path, t


def test_a_named_file_not_yet_indexed_is_read_from_disk(tmp_path):
    kb, t = _kb(tmp_path)
    other = str(t / "Transcript - Linux Threat Hunting - PSW 942.md")
    out = _query(kb, {other: {"itype": "knowledge", "nodes": ["x"]}})._get_summarization_nodes(
        "kaia can you provide a summary of transcript - linux update october 2026.md")
    assert out and all(n["label"] == "Full Content: Transcript - Linux Update October 2026.md" for n in out)
    assert "paragraph 0 " in out[0]["content"] and "paragraph 399" in out[-1]["content"]
    idx = [n["metadata"]["chunk_index"] for n in out]
    assert idx == sorted(idx) and len(out) <= 16


def test_a_named_file_that_does_not_exist_is_not_swapped_for_another(tmp_path):
    kb, t = _kb(tmp_path)
    other = str(t / "Transcript - Linux Threat Hunting - PSW 942.md")
    out = _query(kb, {other: {"itype": "knowledge", "nodes": ["x"]}})._get_summarization_nodes(
        "kaia summarize transcript - linux kernel news 2026.md")
    assert len(out) == 1 and out[0]["metadata"]["source_type"] == "missing_document"
    assert out[0]["label"] == "Not found: transcript - linux kernel news 2026.md"


def test_she_is_told_the_document_was_not_found():
    node = rq._missing_document_node("notes on cats.md")
    text = ContextOptimizer().optimize_context("GENERAL", "persona", [node], [],
                                               user_msg_text="summarize notes on cats.md")["rag"]
    assert "[DOCUMENT NOT FOUND: notes on cats.md]" in text and "not in your knowledge base" in text


def test_reference_words_are_stripped_whole_not_out_of_names(tmp_path):
    """"doc" was cut out of "Doctorow", so the exact-name match never fired."""
    t = tmp_path / "transcripts"
    t.mkdir()
    f = str(t / "Transcript - Cory Doctorow on the Big AI Lie.md")
    seen = []
    orig = rq.log_action
    rq.log_action = seen.append
    try:
        _query(tmp_path, {f: {}, str(t / "Transcript - Big AI Lie.md"): {}})._get_summarization_nodes(
            "summarize transcript - cory doctorow on the big ai lie")
    finally:
        rq.log_action = orig
    assert seen == [f"Summarization target identified: {f}"]
