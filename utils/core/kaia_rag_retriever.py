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


def sanitize_log_content(text: str) -> str:
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
    
    # Strip hallucinated bracket placeholders (e.g. [LINK_TO_ARCHIVE], [IMAGE_HERE])
    # Requires underscore OR 4+ uppercase chars to avoid stripping legitimate [NOTE], [EDIT], [TIP]
    clean = re.sub(r'\[\s*[A-Z][A-Z_]*_[A-Z_]*\s*\]', '', clean)  # Must contain underscore
    clean = re.sub(r'\[\s*[A-Z]{4,}\s*\]', '', clean)  # Or 4+ consecutive uppercase chars
    
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
