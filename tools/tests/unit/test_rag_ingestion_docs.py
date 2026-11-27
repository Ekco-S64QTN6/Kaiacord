"""The RAG architecture guide must describe the real ingestion safety boundary."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_rag_ingestion_documentation_matches_pdf_and_docx_implementation():
    guide = (ROOT / "docs/03-architecture/rag-system.md").read_text(encoding="utf-8")
    indexer = (ROOT / "utils/core/kaia_rag_indexer.py").read_text(encoding="utf-8")

    # Keep the user-facing architecture guide tied to the actual parser entry
    # points rather than an obsolete generic llama-index reader description.
    assert "utils.core.pdf_worker.extract_pdf_file()" in guide
    assert "docx2txt.process()" in guide
    assert "pdf_worker.extract_pdf_file(file_path)" in indexer
    assert "docx2txt.process(file_path)" in indexer

    # Resource-limit/unavailable/no-text skips are deliberately distinct from
    # exception-driven sidecar conversion: a skip preserves the last-good index.
    assert "last-good indexed nodes" in guide
    assert "later retry" in guide
    assert "skipped for the current sweep" in guide
    assert "attempts a Markdown sidecar conversion" in guide
    assert "PDF and DOCX through llama_index's reader" not in guide
