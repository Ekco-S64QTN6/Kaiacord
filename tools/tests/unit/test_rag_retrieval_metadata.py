"""Request-scoped retrieval metadata must survive overlapping RAG work."""
import asyncio

from utils.core.kaia_rag_query import RAGQueryMixin, RetrievalResults
from utils.core.message_processor import _retrieval_metrics


def test_retrieval_results_remain_ordinary_list_values():
    result = RetrievalResults(
        [{"content": "one"}],
        confidence=0.72,
        node_count=3,
    )

    assert isinstance(result, list)
    assert result[0]["content"] == "one"
    assert _retrieval_metrics(result) == (0.72, 3)


def test_parallel_retrieval_metadata_stays_with_its_own_result():
    async def run():
        both_started = asyncio.Event()
        release_low = asyncio.Event()
        release_high = asyncio.Event()
        started = 0

        async def retrieve(confidence, node_count, release):
            nonlocal started
            started += 1
            if started == 2:
                both_started.set()
            await both_started.wait()
            await release.wait()
            return RetrievalResults(
                [{"content": f"confidence={confidence}"}],
                confidence=confidence,
                node_count=node_count,
            )

        low_task = asyncio.create_task(retrieve(0.21, 1, release_low))
        high_task = asyncio.create_task(retrieve(0.91, 7, release_high))
        await both_started.wait()

        # Force the high-confidence query to finish first. The low result is
        # still in flight, so any shared "last result" field now belongs to a
        # different request when the low result is eventually consumed.
        release_high.set()
        high_result = await high_task
        release_low.set()
        low_result = await low_task
        return low_result, high_result

    low_result, high_result = asyncio.run(run())

    # A simulated compatibility/diagnostic cache now contains only the later
    # completed request. Consumers must use the exact result they received.
    last_retrieval_confidence = high_result.retrieval_confidence
    last_retrieval_node_count = high_result.retrieval_node_count
    assert (last_retrieval_confidence, last_retrieval_node_count) == (0.91, 7)

    assert _retrieval_metrics(low_result) == (0.21, 1)
    assert _retrieval_metrics(high_result) == (0.91, 7)


def test_plain_list_result_does_not_inherit_another_requests_metrics():
    assert _retrieval_metrics([{"content": "legacy result"}]) == (0.0, 1)


def test_empty_observational_retrieval_cannot_reuse_a_stale_node_count():
    class EmptyRAG(RAGQueryMixin):
        def __init__(self):
            self.indices = {}
            self._last_retrieval_confidence = 0.0
            self._last_retrieval_node_count = 99

    result = EmptyRAG().search_recent_events("anything", hours=24, limit=5)

    assert isinstance(result, RetrievalResults)
    assert _retrieval_metrics(result) == (0.5, 0)
