"""DECISIONS M2 stage 5: per-type recency half-lives."""

def test_recency_half_life_is_per_source_type():
    """DECISIONS M2 stage 5: news goes stale faster than conversation."""
    from unittest.mock import MagicMock
    from utils.core.kaia_rag_query import RECENCY_HALF_LIFE_DAYS, recency_half_lives

    class Cfg:
        def __init__(self, values): self.values = values
        def get(self, key, default=None): return self.values.get(key, default)

    lives = recency_half_lives(Cfg({"performance.rag_recency_half_life_days": 60,
                                    "performance.rag_recency_half_life_by_type": {"news": 14}}))
    assert lives["user_logs"] == 60 and lives["news"] == 14 and lives["dream"] == 180
    assert recency_half_lives(MagicMock()) == RECENCY_HALF_LIFE_DAYS
