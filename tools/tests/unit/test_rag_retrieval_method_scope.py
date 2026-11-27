"""Query-specific retrieval labels must never mutate shared docstore nodes."""

import asyncio

from llama_index.core.schema import NodeWithScore, TextNode

from utils.core.kaia_rag_query import RAGQueryMixin, without_padding
from utils.core.kaia_rag_retriever import HybridRetriever


class _FakeVectorRetriever:
    def __init__(self, results):
        self.results = results

    async def aretrieve(self, _query):
        return list(self.results)


class _FakeVectorIndex:
    def __init__(self, results):
        self.results = results

    def as_retriever(self, similarity_top_k):
        assert similarity_top_k > 0
        return _FakeVectorRetriever(self.results)


class _QueryBM25:
    def __init__(self, general, keyword):
        self.general = general
        self.keyword = keyword

    def retrieve(self, query, top_k=10):
        assert top_k > 0
        if query == "vector-only":
            return [(self.keyword, 1.0)]
        return [(self.keyword, 1.0), (self.general, 0.9)]


def _scored(results):
    """Mirror the metadata hand-off performed by _score_and_filter_nodes()."""
    scored = []
    for result in results:
        metadata = dict(result.node.metadata)
        metadata["retrieval_method"] = metadata["_retrieval_method"]
        scored.append({
            "content": result.node.get_content(),
            "score": float(result.score or 0.0),
            "metadata": metadata,
        })
    return scored


def test_overlapping_queries_keep_their_own_hybrid_classification():
    async def scenario():
        general = TextNode(
            text="general knowledge candidate",
            metadata={"source_type": "general_knowledge", "quality_score": 0.5},
        )
        keyword = TextNode(
            text="keyword matched candidate",
            metadata={"source_type": "knowledge", "quality_score": 0.5},
        )
        vector_index = _FakeVectorIndex([
            NodeWithScore(node=general, score=0.9),
            NodeWithScore(node=keyword, score=0.8),
        ])
        hybrid = HybridRetriever(vector_index, _QueryBM25(general, keyword), multiplier=1.0)

        allow_first_score = asyncio.Event()
        first_retrieval_done = asyncio.Event()

        async def first_query():
            results = await hybrid.retrieve("vector-only", top_k=2)
            first_retrieval_done.set()
            # Model the caller's later await (fresh-news candidates) before
            # _score_and_filter_nodes consumes this request's node metadata.
            await allow_first_score.wait()
            return results

        first_task = asyncio.create_task(first_query())
        await first_retrieval_done.wait()
        second_results = await hybrid.retrieve("hybrid", top_k=2)
        allow_first_score.set()
        first_results = await first_task

        assert general.metadata == {
            "source_type": "general_knowledge", "quality_score": 0.5,
        }
        first_general = next(n for n in first_results if n.node.node_id == general.node_id)
        second_general = next(n for n in second_results if n.node.node_id == general.node_id)
        assert first_general.node is not general
        assert second_general.node is not general
        assert first_general.node.metadata["_retrieval_method"] == "vector"
        assert second_general.node.metadata["_retrieval_method"] == "hybrid"

        # The common keyword node activates without_padding. A's vector-only
        # general-knowledge candidate must be discarded; B's hybrid candidate stays.
        first_kept = without_padding(_scored(first_results), "ordinary statement")
        second_kept = without_padding(_scored(second_results), "ordinary statement")
        assert all(n["metadata"]["source_type"] != "general_knowledge" for n in first_kept)
        assert any(n["metadata"]["source_type"] == "general_knowledge" for n in second_kept)

    asyncio.run(scenario())


def test_vector_only_fallback_uses_a_request_local_node_copy():
    shared = TextNode(
        text="vector fallback candidate",
        metadata={"source_type": "general_knowledge"},
    )

    class QueryHarness(RAGQueryMixin):
        def __init__(self):
            self.indices = {"knowledge": _FakeVectorIndex([
                NodeWithScore(node=shared, score=0.9),
            ])}
            self.bm25_cache = {}

    results = asyncio.run(
        QueryHarness()._execute_hybrid_retrieval("knowledge", "question", 3)
    )

    assert len(results) == 1
    assert results[0].node is not shared
    assert results[0].node.metadata["_retrieval_method"] == "vector"
    assert shared.metadata == {"source_type": "general_knowledge"}
