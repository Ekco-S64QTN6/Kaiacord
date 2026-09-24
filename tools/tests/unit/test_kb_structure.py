"""The shape of knowledge_base, and the rules that depend on it.

Sixteen top-level folders had grown up one at a time — `corrupt_files` (0 files)
beside `quarantine` (868), `snapshots` (0) beside `system_logs` (1),
`documents/tech_updates` (121) beside a separate `news/` (250). Restructured
2026-09-19. These tests pin the parts that code reads rather than the tidiness.
"""
import importlib.util
import os
from pathlib import Path

import pytest

KB = Path("knowledge_base")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, Path(rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _walk_included():
    """Every directory the indexer would walk, by its own rules."""
    out = []
    for root, _dirs, files in os.walk(KB):
        n = root.replace("\\", "/")
        if any(p.startswith(".") and p not in (".", "..") for p in n.split("/")):
            continue
        if ("/_quarantine" in n or n.endswith("/_quarantine")
                or "forum_posts" in n
                or "/_ingress" in n or n.endswith("/_ingress")):
            continue
        if files:
            out.append(n)
    return out


@pytest.mark.skipif(not KB.exists(), reason="no corpus in this checkout")
def test_the_folders_that_were_merged_are_gone():
    for dead in ("corrupt_files", "quarantine", "snapshots", "system_logs",
                 "deep_dive_reports", "blogs"):
        assert not (KB / dead).exists(), (
            f"{dead}/ is back — something recreated it, which means a writer "
            f"still points at the old path"
        )
    assert not (KB / "documents" / "tech_updates").exists()


@pytest.mark.skipif(not KB.exists(), reason="no corpus in this checkout")
def test_nothing_excluded_is_walked_into_the_index():
    walked = _walk_included()
    for n in walked:
        assert "_quarantine" not in n, n
        assert "_ingress" not in n, n
        assert "forum_posts" not in n, n


@pytest.mark.skipif(not KB.exists(), reason="no corpus in this checkout")
def test_backup_directories_are_not_indexed():
    """`.compacted_backup` held 474 files — the raw forum post histories that
    compaction had just replaced — and was being walked into the index, so she
    retrieved the compacted profile *and* everything it replaced. The named
    exclusion covered `.test` only; the rule is now the leading dot itself."""
    walked = _walk_included()
    for n in walked:
        assert ".compacted_backup" not in n, n
        assert ".dream_archive" not in n, n
        assert "/.test" not in n, n


def test_the_indexer_excludes_dot_directories_as_a_class():
    src = Path("utils/core/kaia_rag_indexer.py").read_text(encoding="utf-8")
    assert 'part.startswith(".")' in src, (
        "the dot-directory exclusion was replaced by named exclusions again; "
        "the next backup directory anyone adds will be indexed"
    )


def test_every_download_destination_is_a_folder_ingress_will_accept():
    """`_classify_folder` returned "Books" while the allow-list held "books", so
    on a case-sensitive filesystem every long PDF had its folder hint discarded
    and was filed as a plain document. A destination the allow-list rejects
    fails silently, which is why this is asserted rather than eyeballed."""
    pi = _load("_pi", "tools/maintenance/process_ingress.py")
    from utils.commands.download_handler import _classify_folder

    cases = [
        ("https://simonwillison.net/2026/blog/thing", "A Blog Post", "html", 1200),
        ("https://arstechnica.com/news/x", "Some News", "html", 900),
        ("https://example.com/paper.pdf", "A Long Manual", "pdf", 40000),
        ("https://example.com/x", "Quarterly Report", "html", 3000),
        ("https://example.com/y", "Random Page", "html", 700),
    ]
    for url, title, ftype, words in cases:
        dest = _classify_folder(url, title, ftype, words)
        root = dest.split("/")[0]
        assert root in pi.ALLOWED_FOLDERS, (
            f"{title!r} routes to {dest!r}, which process_ingress will discard "
            f"in favour of {pi.DEFAULT_FOLDER!r}"
        )


def test_the_ingress_allow_list_names_only_real_folders():
    pi = _load("_pi", "tools/maintenance/process_ingress.py")
    if not KB.exists():
        pytest.skip("no corpus in this checkout")
    for folder in pi.ALLOWED_FOLDERS:
        assert (KB / folder).exists(), f"allow-list names {folder}/, which does not exist"


def test_the_knowledge_boundary_names_only_real_folders():
    """`knowledge_boundary` lists the corpus directories it will vouch for. It
    still named `blogs` and `deep_dive_reports` after both were folded into
    `documents`, which means it vouched for nothing in either."""
    import ast
    src = Path("utils/core/knowledge_boundary.py").read_text(encoding="utf-8")
    lists = [n for n in ast.walk(ast.parse(src))
             if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "subdirs" for t in n.targets)]
    assert lists, "knowledge_boundary no longer has a subdirs list — re-point this test"
    for folder in ast.literal_eval(lists[0].value):
        assert (KB / folder).is_dir(), f"knowledge_boundary names {folder}/, which does not exist"
