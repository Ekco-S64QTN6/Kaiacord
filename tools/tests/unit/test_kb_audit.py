"""The corpus audit, and the two writers that were quietly producing garbage.

`audit_knowledge_base.py` exists because the knowledge base is tinkered with
constantly and every round has introduced a defect nobody noticed until it
changed an answer. These tests pin the fault classes it detects.
"""
import importlib.util
from pathlib import Path

import pytest

KB = Path("knowledge_base")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, Path(rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit = _load("_audit", "tools/maintenance/audit_knowledge_base.py")


def test_frontmatter_split_tolerates_a_fused_fence():
    """A chunk of this corpus has the closing `---` on the same line as the
    first line of content: `---User: speeding ticket here and there`. An
    anchored parser sees no body at all."""
    fm, body = audit.split_frontmatter('---\nsummary: "x"\n---User: speeding ticket\n')
    assert 'summary: "x"' in fm
    assert body.startswith("User: speeding ticket")


def test_frontmatter_split_handles_a_normal_file():
    fm, body = audit.split_frontmatter('---\ntitle: X\n---\n\nthe body.\n')
    assert "title: X" in fm and body.strip() == "the body."


def test_a_file_without_frontmatter_is_all_body():
    fm, body = audit.split_frontmatter("# Just a heading\n\ntext")
    assert fm == "" and body.startswith("# Just a heading")


@pytest.mark.skipif(not KB.exists(), reason="no corpus in this checkout")
def test_the_audit_runs_over_the_real_corpus():
    findings, counts = audit.audit()
    assert sum(counts.values()) > 0, "the audit found no files at all"
    # Whatever it finds, it must not crash and must name a fix for each class.
    for name in findings:
        if name.startswith("_"):
            continue
        assert name in audit.FIXES, f"{name} is reported with no remedy named"


@pytest.mark.skipif(not KB.exists(), reason="no corpus in this checkout")
def test_excluded_trees_are_not_audited_as_corpus():
    """`_quarantine` holds what was pulled *out*; auditing it would report every
    file it contains as a fresh finding, forever."""
    _f, counts = audit.audit()
    assert "_quarantine" not in counts
    assert "_ingress" not in counts
    assert "forum_posts" not in counts


# ── The two writer bugs ──────────────────────────────────────────────

def test_forum_dedup_spans_every_dated_file():
    """It read only today's file, so a post recorded yesterday was invisible and
    written again in full: 76 byte-identical files across 34 user directories,
    one more per user per day for as long as the scraper saw the same posts."""
    import inspect
    from utils.social.kaia_forum import ForumClient

    src = inspect.getsource(ForumClient)
    assert 'glob("interactions_*.md")' in src, (
        "the dedup no longer scans the user's other dated files")
    assert "seen_ids" in src


def test_enrichment_filters_before_it_caps():
    """The cap was applied to the whole file list in directory order — books
    first, all already enriched — so a nightly `--limit 40` spent its budget
    skipping them and never reached the 369 news files with no frontmatter. It
    logged a completed pass every night while enriching nothing."""
    src = Path("tools/maintenance/enrich_metadata.py").read_text(encoding="utf-8")
    cap = src.index("args.limit]")
    filt = src.index("is_eligible_for_enrichment(frontmatter, body):\n            eligible.append")
    assert filt < cap, "the limit is applied before eligibility again"


def test_the_wiki_scraper_refuses_pages_with_no_article_in_them():
    """An 8-word page filed as "WinEQ Installation and Configuration" wins
    retrieval on its title and then answers nothing, which is worse than its
    absence."""
    src = Path("tools/social/scrape_p99_wiki.py").read_text(encoding="utf-8")
    assert "intended to disambiguate" in src
    assert "MIN_ARTICLE_WORDS" in src
