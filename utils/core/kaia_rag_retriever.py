"""
RAG Retrieval Components
=========================

Extracted from kaia_rag.py (Phase 28 / CQ-01).

Contains:
- CircuitOpenError: Exception for circuit breaker state
- sanitize_log_content: Strip system tags from text before logging
- SimpleBM25Retriever: BM25 retriever with async initialization
- HybridRetriever: Vector + BM25 retriever with RRF scoring
- thread_safe_rag_operation: Decorator for thread-safe RAG operations
"""

import os
import re
import asyncio
import heapq
import threading
from functools import wraps
from typing import List

from rank_bm25 import BM25Okapi
from llama_index.core.schema import NodeWithScore

from utils.infrastructure.logging.kaia_logger import (
    log_info, log_warning, log_debug
)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open"""
    pass


def sanitize_log_content(text: str, users_words: bool = False) -> str:
    """Strip internal system tags and dev metadata from text before logging.
    
    Prevents RAG pollution from internal tags like [AUTO_QUIP], [REMEMBER_COMMAND],
    dev metadata like [RAG Component]/[MODIFY], and hallucinated placeholders.
    """
    if not text:
        return text
    
    clean = text
    
    # Replace internal action tags with human-readable descriptions
    clean = clean.replace('[AUTO_QUIP]', '(autonomous broadcast)')
    clean = clean.replace('[AUTO_THREAD_PART]', '(thread continuation)')
    
    # Strip [REMEMBER_COMMAND]: prefix but keep the actual content
    clean = re.sub(r'\[REMEMBER_COMMAND\]:\s*', '', clean)
    
    # Strip dev metadata tokens
    clean = re.sub(r'\[(?:RAG Component|MODIFY|NEW|DELETE|INSERT)\]', '', clean)
    
    # Pipeline markers ([USER_MESSAGE], [LINKED_WEB_CONTENT]) always contain an
    # underscore.
    clean = re.sub(r'\[\s*[A-Z][A-Z_]*_[A-Z_]*\s*\]', '', clean)
    # Her hallucinated placeholders ([IMAGE], [LINK]) — in her replies only. A
    # person who typed "[EDIT]" or "[WHISKEY]" keeps their words: user turns
    # are never rewritten.
    if not users_words:
        clean = re.sub(r'\[\s*[A-Z]{4,}\s*\]', '', clean)
    
    # Strip <think>...</think> reasoning blocks (defensive strip — no-op for current models)
    clean = re.sub(r'<think>.{0,5000}?</think>', '', clean, flags=re.DOTALL)
    clean = re.sub(r'</?think>', '', clean)  # Strip orphaned tags that weren't in complete pairs
    
    # Clean up resulting double spaces
    clean = re.sub(r'  +', ' ', clean)
    
    return clean.strip()


class SimpleBM25Retriever:
    """BM25 retriever with async initialization and lazy tokenization."""
    
    CONVERSATIONAL_STOPWORDS = {
        "hey", "kaia", "have", "you", "had", "chance", "take", "look",
        "at", "the", "a", "an", "to", "of", "for", "and", "is", "it",
        "can", "could", "would", "just", "going", "think", "know",
        "yeah", "ok", "okay", "sure", "actually", "really", "kind",
        "file", "doc", "document"
    }

    def __init__(self, nodes: List[NodeWithScore]):
        self.nodes = nodes
        self.bm25 = None
        self._tokenized_docs = None
        self._lock = threading.Lock()

    async def initialize_async(self):
        """Tokenize nodes and build BM25 in a background thread."""
        from utils.core.rag_utils import get_node_text
        
        def _build_bm25():
            # Process in thread to avoid blocking event loop
            tokenized = [self._tokenize_node(node) for node in self.nodes]
            bm25 = BM25Okapi(tokenized) if tokenized else None
            return tokenized, bm25

        self._tokenized_docs, self.bm25 = await asyncio.to_thread(_build_bm25)
        # We KEEP self.nodes because we need to return them in retrieve()
        # but we no longer need to perform the heavy tokenization in the main thread.
        log_debug(f"BM25 initialized in background with {len(self.nodes)} nodes.")

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.sub(r"[^\w\s]", " ", text.lower()).split()
        return [t for t in tokens if t not in self.CONVERSATIONAL_STOPWORDS and len(t) >= 2]

    def _tokenize_node(self, node) -> List[str]:
        from utils.core.rag_utils import get_node_text, get_node_metadata
        text = get_node_text(node)
        meta = get_node_metadata(node)
        fp = meta.get('file_path', '') if isinstance(meta, dict) else ''
        fn = os.path.splitext(os.path.basename(fp))[0].replace('-', ' ').replace('_', ' ') if fp else ''
        title = meta.get('title', '') if isinstance(meta, dict) else ''
        combined = f"{fn} {title} {text}" if (fn or title) else text
        return self._tokenize(combined)

    def retrieve(self, query: str, top_k: int = 10):
        """Retrieve top_k nodes using BM25, building synchronously if not yet initialized."""
        if self.bm25 is None:
            with self._lock:
                if self.bm25 is None:
                    tokenized = [self._tokenize_node(node) for node in self.nodes]
                    self._tokenized_docs = tokenized
                    self.bm25 = BM25Okapi(tokenized) if tokenized else None

        if not self.bm25 or self.nodes is None:
            return []

        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        
        # Use nlargest for better efficiency than sorting the whole array O(N log k)
        top_indices = heapq.nlargest(top_k, range(len(scores)), key=lambda i: scores[i])

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.nodes[idx], float(scores[idx])))
        return results

class HybridRetriever:
    """Vector + BM25 retriever optimized for memory and async execution."""
    def __init__(self, vector_index, bm25_retriever: SimpleBM25Retriever, multiplier: float = 60.0):
        self.vector_index = vector_index
        self.bm25 = bm25_retriever
        self.multiplier = multiplier

    async def retrieve(self, query: str, top_k: int = 5, alpha: float = 0.5, query_bundle=None):
        """Hybrid retrieval using RRF and efficient top-k selection."""
        bundle = query_bundle if query_bundle else query

        # 1. Vector retrieval
        vector_nodes = await self.vector_index.as_retriever(similarity_top_k=top_k*2).aretrieve(bundle)

        # 2. BM25 retrieval (offloaded to thread)
        bm25_results = await asyncio.to_thread(self.bm25.retrieve, query, top_k=top_k*2)

        # 3. Reciprocal Rank Fusion
        combined_scores = {}
        node_map = {}

        # Vector RRF
        for rank, node_with_score in enumerate(vector_nodes):
            node = node_with_score.node
            node_id = node.node_id
            node_map[node_id] = node
            q_score = node.metadata.get("quality_score", 0.5) if isinstance(node.metadata, dict) else 0.5
            boost = 1.0 + 0.15 * q_score
            combined_scores[node_id] = combined_scores.get(node_id, 0) + (alpha / (rank + 60)) * boost

        # BM25 RRF
        for rank, (node, _) in enumerate(bm25_results):
            node_id = node.node_id
            node_map[node_id] = node
            q_score = node.metadata.get("quality_score", 0.5) if isinstance(node.metadata, dict) else 0.5
            boost = 1.0 + 0.15 * q_score
            combined_scores[node_id] = combined_scores.get(node_id, 0) + ((1 - alpha) / (rank + 60)) * boost

        # 4. Efficient top_k selection via heapq
        top_items = heapq.nlargest(top_k, combined_scores.items(), key=lambda x: x[1])
        
        results = []
        for nid, score in top_items:
            # Determine if this was primarily a BM25 or Vector match based on presence
            in_bm25 = any(n.node_id == nid for n, _ in bm25_results)
            in_vector = any(n.node.node_id == nid for n in vector_nodes)
            method = "hybrid" if (in_bm25 and in_vector) else ("bm25" if in_bm25 else "vector")
            
            node = node_map[nid]
            if not isinstance(node.metadata, dict):
                node.metadata = {}
            node.metadata["_retrieval_method"] = method
            
            node_with_score = NodeWithScore(node=node, score=float(score * self.multiplier))
            results.append(node_with_score)
            
        return results


def thread_safe_rag_operation(func):
    """Decorator to ensure thread safety for RAG operations without stalling the event loop."""
    import inspect
    is_async = inspect.iscoroutinefunction(func)

    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        lock_timeout = getattr(config, 'rag_lock_seconds', 10.0)
        
        # [CONCURRENCY OPTIMIZATION]: Retrieval is safe for parallel execution.
        if func.__name__ in ['retrieve', 'get_context_for_hallucination_check', 'detect_hallucination']:
            return await func(self, *args, **kwargs)
            
        acquired = False
        try:
            # Use a non-blocking lock acquisition in a thread to keep the event loop responsive
            acquired = await asyncio.to_thread(self._data_lock.acquire, timeout=lock_timeout)
            if not acquired:
                log_warning(f"RAG operation {func.__name__} timed out waiting for data lock")
                return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
            
            return await func(self, *args, **kwargs)
        finally:
            if acquired:
                self._data_lock.release()

    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        lock_timeout = getattr(config, 'rag_lock_seconds', 10.0)
        
        if func.__name__ in ['retrieve', 'get_context_for_hallucination_check', 'detect_hallucination']:
            return func(self, *args, **kwargs)
            
        acquired = False
        try:
            acquired = self._data_lock.acquire(timeout=lock_timeout)
            if not acquired:
                log_warning(f"RAG sync operation {func.__name__} timed out waiting for data lock")
                return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
            return func(self, *args, **kwargs)
        finally:
            if acquired:
                self._data_lock.release()

    return async_wrapper if is_async else sync_wrapper


# ── Vector search without stalling the process ───────────────────────
#
# llama_index's SimpleVectorStore.query rebuilds a numpy array from every
# stored embedding (thousands of 768-float Python lists) on each query, in one
# C call that holds the GIL for 100–200 ms, then scores row by row in Python.
# Inside the bot that froze discord.py's voice thread, which must send a frame
# every 20 ms: `!music records` dropped out whenever a reply searched memory.
# The matrix is built once per store change, in small slices that let other
# threads in, and a query is one matrix product.

_VEC_CACHE: dict = {}
_VEC_VERSION: dict = {}
_VEC_SLICE = 256


def _store_matrix(store):
    import time as _time
    import numpy as np
    data = store.data.embedding_dict
    key = id(store)
    version = _VEC_VERSION.get(key, 0)
    cached = _VEC_CACHE.get(key)
    if cached and cached[0] == version and cached[1] == len(data):
        return cached[2], cached[3]
    ids = list(data.keys())
    rows = []
    for i in range(0, len(ids), _VEC_SLICE):
        rows.append(np.asarray([data[k] for k in ids[i:i + _VEC_SLICE]], dtype=np.float32))
        _time.sleep(0)                                   # let the voice thread run
    matrix = np.concatenate(rows) if rows else np.zeros((0, 0), dtype=np.float32)
    if len(matrix):
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.where(norms == 0, 1.0, norms)
    _VEC_CACHE[key] = (version, len(data), ids, matrix)
    return ids, matrix


def install_fast_vector_query() -> None:
    """Route SimpleVectorStore's top-k queries — filtered and node-restricted
    ones included — through the cached matrix. Non-default modes keep
    llama_index's path."""
    try:
        import numpy as np
        from llama_index.core.vector_stores.simple import SimpleVectorStore, build_metadata_filter_fn
        from llama_index.core.vector_stores.types import VectorStoreQueryMode, VectorStoreQueryResult
    except Exception:
        return
    if getattr(SimpleVectorStore, "_kaia_fast", False):
        return
    original_query = SimpleVectorStore.query
    original_add = SimpleVectorStore.add
    original_delete = SimpleVectorStore.delete
    original_delete_nodes = getattr(SimpleVectorStore, "delete_nodes", None)

    def bump(self):
        _VEC_VERSION[id(self)] = _VEC_VERSION.get(id(self), 0) + 1

    def query(self, query, **kwargs):
        if query.mode != VectorStoreQueryMode.DEFAULT or query.query_embedding is None:
            return original_query(self, query, **kwargs)
        if query.filters is not None and self.data.embedding_dict and not self.data.metadata_dict:
            return original_query(self, query, **kwargs)     # raises, as llama_index does
        ids, matrix = _store_matrix(self)
        if not ids:
            return VectorStoreQueryResult(similarities=[], ids=[])
        # Filtered and node-restricted queries are most of them (identity
        # scoping, type filters), and llama_index answers those by building a
        # fresh array of every candidate embedding in one GIL-holding call. The
        # candidates are picked here in Python, which yields, and scored as rows
        # of the cached matrix.
        rows = None
        if query.filters is not None or query.node_ids is not None:
            keep_meta = build_metadata_filter_fn(lambda nid: self.data.metadata_dict[nid], query.filters)
            allowed = set(query.node_ids) if query.node_ids is not None else None
            rows = np.fromiter((i for i, nid in enumerate(ids)
                                if (allowed is None or nid in allowed) and keep_meta(nid)), dtype=np.intp)
            if not len(rows):
                return VectorStoreQueryResult(similarities=[], ids=[])
        q = np.asarray(query.query_embedding, dtype=np.float32)
        qn = np.linalg.norm(q)
        q = q / qn if qn else q
        sims = (matrix if rows is None else matrix[rows]) @ q
        k = min(int(query.similarity_top_k or len(sims)), len(sims))
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        pick = top if rows is None else rows[top]
        return VectorStoreQueryResult(similarities=[float(sims[i]) for i in top], ids=[ids[i] for i in pick])

    def add(self, *a, **kw):
        out = original_add(self, *a, **kw)
        bump(self)
        return out

    def delete(self, *a, **kw):
        out = original_delete(self, *a, **kw)
        bump(self)
        return out

    SimpleVectorStore.query = query
    SimpleVectorStore.add = add
    SimpleVectorStore.delete = delete
    if original_delete_nodes:
        def delete_nodes(self, *a, **kw):
            out = original_delete_nodes(self, *a, **kw)
            bump(self)
            return out
        SimpleVectorStore.delete_nodes = delete_nodes
    SimpleVectorStore._kaia_fast = True
