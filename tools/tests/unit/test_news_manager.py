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
