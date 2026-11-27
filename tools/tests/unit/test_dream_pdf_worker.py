"""PDF use in nightly dream triage must remain inside the shared worker."""
from pathlib import Path

from utils.core.kaia_dream import DreamEngine
from utils.core import pdf_worker


def test_dream_pdf_snippets_use_the_bounded_worker_and_choose_a_middle_page(tmp_path, monkeypatch):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 fixture")
    engine = DreamEngine.__new__(DreamEngine)
    calls = []

    def extract(path, **kwargs):
        calls.append((path, kwargs))
        pages = [(number, f"bounded dream text from page {number}") for number in range(1, 22)]
        return {
            "page_count": len(pages),
            "pages": pages,
            "text": "\n".join(text for _number, text in pages),
            "truncated": False,
        }

    monkeypatch.setattr(pdf_worker, "extract_pdf_file", extract)
    monkeypatch.setattr("utils.core.kaia_dream.random.choice", lambda choices: choices[0])

    snippet = engine._extract_snippet(pdf)

    assert snippet == "bounded dream text from page 6"
    assert len(calls) == 1
    assert Path(calls[0][0]) == pdf
    assert calls[0][1]["queue_wait_seconds"] == 600
