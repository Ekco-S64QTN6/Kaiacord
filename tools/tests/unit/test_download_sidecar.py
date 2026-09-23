"""The page's own metadata reaches the filed document.

`!download` extracted the author, meta description and keywords and built them
into a frontmatter block it never wrote; the sidecar that process_ingress reads
carried none of them, so every filed download lost its author.
"""
import importlib.util
import json
from pathlib import Path


def _load_ingress():
    spec = importlib.util.spec_from_file_location(
        "process_ingress_under_test", "tools/maintenance/process_ingress.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_page_metadata_is_the_fallback_for_frontmatter(tmp_path, monkeypatch):
    ingress = _load_ingress()
    monkeypatch.setattr(ingress, "KB", tmp_path)
    # The model is unavailable: no summary or keywords of its own.
    monkeypatch.setattr(ingress, "derive_topic_and_title",
                        lambda body, title, **k: ("Reference", title, "", []))

    staged = tmp_path / "_ingress"
    staged.mkdir()
    md = staged / "page.md"
    md.write_text("# Tidal Locking\n\n" + "The moon keeps one face toward us. " * 30,
                  encoding="utf-8")
    md.with_suffix(".meta.json").write_text(json.dumps({
        "title": "Tidal Locking",
        "author": "A. Writer",
        "page_summary": "Why the moon shows one face.",
        "keywords": ["tidal locking", "orbital resonance"],
        "document_type": "Article",
        "folder": "documents",
    }), encoding="utf-8")

    ok, msg = ingress.process_one(md)
    assert ok, msg
    [filed] = list((tmp_path / "documents").glob("*.md"))
    text = filed.read_text(encoding="utf-8")
    assert "A. Writer" in text
    assert "Why the moon shows one face." in text
    assert "orbital resonance" in text


def test_the_downloader_no_longer_builds_frontmatter_it_discards():
    src = Path("utils/commands/download_handler.py").read_text(encoding="utf-8")
    assert "dump_frontmatter" not in src
    assert "'page_summary'" in src and "'author'" in src
