"""NewsManager parses the filed briefs into plain-text items per category."""
from pathlib import Path

import pytest

from utils.news.kaia_news import NewsManager

NEWS = Path(__file__).resolve().parents[3] / "knowledge_base" / "news"


@pytest.fixture(scope="module")
def manager():
    if not any(NEWS.glob("**/news_brief_*.md")):
        pytest.skip("no news briefs filed in this checkout")
    nm = NewsManager(base_path=str(NEWS))
    nm.refresh()
    return nm


def test_briefs_parse_into_items(manager):
    assert sum(len(v) for v in manager.news_cache.values()) > 0


def test_items_are_text_not_stringified_dicts(manager):
    for cat, items in manager.news_cache.items():
        for item in items:
            text = item.get("text")
            assert isinstance(text, str), (cat, type(text))
            assert not text.startswith("{"), (cat, text[:60])


def test_a_bare_source_name_is_not_an_item(manager):
    sources = {"Reuters", "The Record", "BleepingComputer", "Financial Times", "404 Media"}
    for cat, items in manager.news_cache.items():
        assert not [i["text"] for i in items if i["text"] in sources], cat


def test_get_news_returns_items_for_a_populated_category(manager):
    cat = next(c for c, v in manager.news_cache.items() if v)
    assert manager.get_news(cat, limit=5)


def test_sync_get_news_does_not_call_refresh_under_the_cache_lock(tmp_path, monkeypatch):
    """The refresh owns the non-reentrant lock; get_news must not pre-acquire it."""
    manager = NewsManager(base_path=str(tmp_path))
    (tmp_path / "news_brief.md").write_text(
        "## SUMMARY\n- A sufficiently long test news item.\n",
        encoding="utf-8",
    )
    original_refresh = manager.refresh

    def guarded_refresh():
        assert not manager._lock.locked(), (
            "get_news entered refresh while already holding the cache lock"
        )
        original_refresh()

    monkeypatch.setattr(manager, "refresh", guarded_refresh)

    assert manager.get_news()



def test_generated_tech_digest_parses_as_one_story_per_headline(tmp_path, monkeypatch):
    """The scraper's digest format must match NewsManager's story parser."""
    from tools.maintenance.scrape_tech_news import TechNewsScraper

    scraper = TechNewsScraper.__new__(TechNewsScraper)
    scraper.today = "2026-11-05"
    monkeypatch.setattr(
        scraper, "generate_executive_summary",
        lambda _body: "Two technical developments were reported.",
    )
    markdown, count = scraper.generate_digest_markdown([
        {
            "title": "A new model release",
            "source": "Hacker News",
            "url": "https://example.test/model",
            "summary": "The project published a new model and technical report.",
        },
        {
            "title": "A cloud platform update",
            "source": "Ars Technica",
            "url": "https://example.test/cloud",
            "summary": "The provider announced a platform infrastructure change.",
        },
        {
            "title": "A new model release",
            "source": "Duplicate",
            "url": "https://example.test/duplicate",
            "summary": "This duplicate must not become a separate story.",
        },
    ])
    assert count == 2

    digest = tmp_path / "tech_updates" / "tech_digest_20261105.md"
    digest.parent.mkdir(parents=True)
    digest.write_text(markdown, encoding="utf-8")

    manager = NewsManager(base_path=str(tmp_path))
    manager.refresh()
    items = manager.get_news("technology", limit=10)
    texts = [item["text"] for item in items]

    assert len(texts) == 2
    assert "A new model release" in texts[0]
    assert "new model and technical report" in texts[0]
    assert "Hacker News" in texts[0]
    assert "https://example.test/model" in texts[0]
    assert "A cloud platform update" in texts[1]
    assert not any(text.startswith("Source:") for text in texts)
    assert not any(text.startswith("Reference:") for text in texts)
