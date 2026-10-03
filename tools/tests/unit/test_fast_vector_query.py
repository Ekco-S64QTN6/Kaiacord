"""Vector search from the cached matrix gives llama_index's answer, without its
one-call array build — the 100 ms GIL stall that stuttered music on every
reply. Filtered and node-restricted queries are most real ones, and those went
the slow way until the cached path took them too."""
import random

import pytest
from llama_index.core.vector_stores.simple import SimpleVectorStore
from llama_index.core.vector_stores.types import (FilterOperator, MetadataFilter, MetadataFilters,
                                                  VectorStoreQuery)
from llama_index.core.schema import TextNode

from utils.core import kaia_rag_retriever as kr


def _store(n=300, dim=16, seed=3):
    rng = random.Random(seed)
    store = SimpleVectorStore()
    nodes = []
    for i in range(n):
        node = TextNode(text=f"n{i}", id_=f"id{i}",
                        metadata={"kind": "logs" if i % 3 else "knowledge", "user": f"u{i % 5}"})
        node.embedding = [rng.uniform(-1, 1) for _ in range(dim)]
        nodes.append(node)
    store.add(nodes)
    return store, rng


def _queries(rng, dim=16):
    q = [rng.uniform(-1, 1) for _ in range(dim)]
    return [
        VectorStoreQuery(query_embedding=q, similarity_top_k=7),
        VectorStoreQuery(query_embedding=q, similarity_top_k=7, filters=MetadataFilters(
            filters=[MetadataFilter(key="kind", value="knowledge")])),
        VectorStoreQuery(query_embedding=q, similarity_top_k=5, filters=MetadataFilters(
            filters=[MetadataFilter(key="user", value=["u1", "u2"], operator=FilterOperator.IN)])),
        VectorStoreQuery(query_embedding=q, similarity_top_k=4, node_ids=[f"id{i}" for i in range(0, 300, 7)]),
        VectorStoreQuery(query_embedding=q, similarity_top_k=4, node_ids=["nope"]),
    ]


def test_the_cached_path_answers_as_llama_index_does():
    kr.install_fast_vector_query()
    fast = SimpleVectorStore.query
    store, rng = _store()
    for query in _queries(rng):
        got = fast(store, query)
        want = SimpleVectorStore.__mro__[0].__dict__["query"]  # the patched one
        assert want is fast
        ref = _reference(store, query)
        assert got.ids == ref.ids
        assert got.similarities == pytest.approx(ref.similarities, abs=1e-5)


def _reference(store, query):
    """llama_index's own answer, through its unpatched code."""
    from llama_index.core.indices.query.embedding_utils import get_top_k_embeddings
    from llama_index.core.vector_stores.simple import build_metadata_filter_fn
    from llama_index.core.vector_stores.types import VectorStoreQueryResult
    keep = build_metadata_filter_fn(lambda nid: store.data.metadata_dict[nid], query.filters)
    allowed = set(query.node_ids) if query.node_ids is not None else None
    ids, embs = [], []
    for nid, emb in store.data.embedding_dict.items():
        if (allowed is None or nid in allowed) and keep(nid):
            ids.append(nid)
            embs.append(emb)
    if not ids:
        return VectorStoreQueryResult(similarities=[], ids=[])
    sims, top = get_top_k_embeddings(query.query_embedding, embs, similarity_top_k=query.similarity_top_k,
                                     embedding_ids=ids)
    return VectorStoreQueryResult(similarities=sims, ids=top)


def test_no_query_builds_the_candidate_array(monkeypatch):
    kr.install_fast_vector_query()
    store, rng = _store()
    import llama_index.core.vector_stores.simple as simple

    def boom(*a, **k):
        raise AssertionError("llama_index's array build ran")
    monkeypatch.setattr(simple, "get_top_k_embeddings", boom)
    for query in _queries(rng):
        store.query(query)


def test_an_added_node_is_searchable_at_once():
    kr.install_fast_vector_query()
    store, rng = _store(n=20)
    store.query(VectorStoreQuery(query_embedding=[1.0] * 16, similarity_top_k=3))
    node = TextNode(text="new", id_="fresh", metadata={"kind": "knowledge", "user": "u9"})
    node.embedding = [1.0] * 16
    store.add([node])
    got = store.query(VectorStoreQuery(query_embedding=[1.0] * 16, similarity_top_k=1))
    assert got.ids == ["fresh"]


def test_a_freed_store_takes_its_cached_matrix_with_it():
    import gc
    from llama_index.core.vector_stores.simple import SimpleVectorStore
    from llama_index.core.vector_stores.types import VectorStoreQuery
    from utils.core import kaia_rag_retriever as R
    R.install_fast_vector_query()
    store = SimpleVectorStore()
    store.data.embedding_dict.update({"a": [1.0, 0.0], "b": [0.0, 1.0]})
    store.query(VectorStoreQuery(query_embedding=[1.0, 0.0], similarity_top_k=1))
    key = id(store)
    assert key in R._VEC_CACHE
    del store
    gc.collect()
    assert key not in R._VEC_CACHE
