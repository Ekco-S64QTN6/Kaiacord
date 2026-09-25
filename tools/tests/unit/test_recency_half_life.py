"""Per-type recency half-lives."""

def test_recency_half_life_is_per_source_type():
    """News goes stale faster than conversation."""
    from unittest.mock import MagicMock
    from utils.core.kaia_rag_query import RECENCY_HALF_LIFE_DAYS, recency_half_lives

    class Cfg:
        def __init__(self, values): self.values = values
        def get(self, key, default=None): return self.values.get(key, default)

    lives = recency_half_lives(Cfg({"performance.rag_recency_half_life_days": 60,
                                    "performance.rag_recency_half_life_by_type": {"news": 14}}))
    assert lives["user_logs"] == 60 and lives["news"] == 14 and lives["dream"] == 180
    assert recency_half_lives(MagicMock()) == RECENCY_HALF_LIFE_DAYS


def test_eager_warm_still_exists():
    """Kaiacord.py --eager-rag-warm calls rag.pre_warm; removing the pickle
    cache must not remove the method the flag runs."""
    import asyncio
    from types import SimpleNamespace
    from utils.core.kaia_rag_query import RAGQueryMixin
    node = SimpleNamespace(text="pixel is a robot cat", metadata={}, get_content=lambda: "pixel is a robot cat")
    rag = SimpleNamespace(bm25_cache={}, indices={"knowledge": SimpleNamespace(
        storage_context=SimpleNamespace(docstore=SimpleNamespace(docs={"a": node})))})
    asyncio.run(RAGQueryMixin.pre_warm(rag))
    assert rag.bm25_cache["knowledge"].bm25 is not None
