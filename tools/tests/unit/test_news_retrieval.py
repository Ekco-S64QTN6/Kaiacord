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
