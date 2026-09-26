"""ingest_manual_news rewrites the news corpus, so it is a dry run unless told
--apply, and its title normaliser works below frontmatter: prepending the
title above the '---' fence broke every brief update_kaia_news files."""
import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools/maintenance/ingest_manual_news.py"


@pytest.fixture
def tool():
    spec = importlib.util.spec_from_file_location("ingest_manual_news_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BRIEF = ("---\ntitle: News Brief - 2026-09-26\ncategory: news\n---\n\n"
         "# NEWS_BRIEF: 2026-09-26\n\n## EXECUTIVE_SUMMARY\nThings happened.\n")


def test_a_filed_brief_is_unchanged(tool):
    assert tool.normalize(BRIEF, False, "2026-09-26") == BRIEF


def test_the_title_goes_below_the_frontmatter(tool):
    out = tool.normalize("---\ntitle: x\n---\nTECH_OUTAGES\nstuff\n", False, "2026-09-26")
    assert out.startswith("---\ntitle: x\n---\n# NEWS_BRIEF: 2026-09-26\n")
    assert "## TECH_OUTAGES" in out


def test_a_bare_title_is_replaced_not_duplicated(tool):
    out = tool.normalize("NEWS_BRIEF: 2026-09-26\n\nSECURITY_INCIDENTS\nx\n", False, "2026-09-26")
    assert out.count("NEWS_BRIEF") == 1 and out.startswith("# NEWS_BRIEF: 2026-09-26")


def test_without_apply_nothing_is_touched(tool, tmp_path, monkeypatch):
    daily, weekly = tmp_path / "daily", tmp_path / "weekly"
    daily.mkdir(); weekly.mkdir()
    monkeypatch.setattr(tool, "KNOWLEDGE_DIR_DAILY", daily)
    monkeypatch.setattr(tool, "KNOWLEDGE_DIR_WEEKLY", weekly)
    monkeypatch.chdir(tmp_path)
    src = daily / "manual_news_2026-09-20.md"
    src.write_text("NEWS_BRIEF: 2026-09-20\nWORLD\nx\n")
    tool.ingest_manual_news()
    assert [p.name for p in daily.iterdir()] == [src.name]
    assert src.read_text() == "NEWS_BRIEF: 2026-09-20\nWORLD\nx\n"
