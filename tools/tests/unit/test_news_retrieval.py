"""News retrieval actually retrieves news; sections and duplicates classified by word."""

def test_the_news_searches_ask_for_news():
    """retrieve() drops every news node unless include_news is set; the
    dedicated news search and the what's-new expansions never set it."""
    import inspect
    from utils.core.message_processor import MessageProcessor
    src = inspect.getsource(MessageProcessor._start_retrieval_tasks) if hasattr(
        MessageProcessor, "_start_retrieval_tasks") else inspect.getsource(MessageProcessor)
    block = src[src.index("tasks['rag_news']"):src.index("return tasks, ask_whats_new")]
    assert block.count("include_news=True") == 2


def test_news_sections_and_duplicates():
    from utils.news.kaia_news import NewsManager, RAGEnhancer
    n = NewsManager.__new__(NewsManager)
    n.categories = {}
    assert n._map_to_category("Domestic affairs") == "general"
    assert n._map_to_category("AI and robotics") == "technology"
    dup = [{"content": "same brief", "score": 1.0}, {"content": "same brief", "score": 0.4}]
    assert len(RAGEnhancer().deduplicate_results(dup)) == 1

def test_mentioned_news_retention_keeps_the_latest_100_in_recency_order(tmp_path):
    import json
    from collections import defaultdict
    from utils.news.kaia_news import NewsRetrievalEnhancer

    enhancer = NewsRetrievalEnhancer()
    enhancer.memory_path = tmp_path / "mentioned_news.json"
    enhancer.mentioned_news_cache = defaultdict(list)

    ids = [f"item-{i:03d}" for i in range(105)]
    enhancer.track_mentioned_news(ids, "user-42")

    expected = ids[-100:]
    assert isinstance(enhancer.mentioned_news_cache["user-42"], list)
    assert enhancer.mentioned_news_cache["user-42"] == expected
    assert json.loads(enhancer.memory_path.read_text(encoding="utf-8"))["user-42"] == expected

    # Mentioning an existing ID again moves it to the newest position.
    enhancer.track_mentioned_news([expected[0]], "user-42")
    expected = expected[1:] + [expected[0]]
    assert enhancer.mentioned_news_cache["user-42"] == expected
    assert json.loads(enhancer.memory_path.read_text(encoding="utf-8"))["user-42"] == expected

    # The order survives reloads so future eviction remains recency-based.
    reloaded = NewsRetrievalEnhancer()
    reloaded.memory_path = enhancer.memory_path
    reloaded.load_mentioned_news()
    assert reloaded.mentioned_news_cache["user-42"] == expected
