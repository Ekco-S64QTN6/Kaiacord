"""
RAG Query Mixin — Retrieval, Scoring & Search
===============================================

Extracted from kaia_rag.py (Phase 28 / CQ-01).

Contains:
- _route_retrieval_strategy: Strategy routing based on intent/category
- _get_summarization_nodes: Full-content retrieval for summarization  
- _target_indices: Index selection and count planning
- _execute_hybrid_retrieval: Vector + BM25 hybrid search
- _resolve_identity_mappings: Cross-platform identity resolution
- _score_and_filter_nodes: RRF scoring, boosting, and filtering
- get_context_for_hallucination_check: Context fetch for fact-checking
- retrieve: Main entry point for RAG queries
- get_recent_highlights: Log scanning for interesting events
- search_recent_events: Targeted event search
- detect_hallucination: Hallucination detection wrapper
"""

import os
import re
import asyncio
import time
import math
import heapq
import random
import traceback
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Set

from llama_index.core.schema import NodeWithScore

from utils.infrastructure.logging.kaia_logger import (
    log_success, log_info, log_warning, log_error, log_action, log_debug
)
from utils.infrastructure.system.yaml_config import config
from utils.core.hallucination_detector import HallucinationDetector
from utils.core.kaia_rag_retriever import (
    SimpleBM25Retriever, HybridRetriever, thread_safe_rag_operation
)
from utils.core.context_optimizer import Intent


class RAGQueryMixin:
    """Mixin class providing retrieval and query methods for KaiaRAG."""

    # Pre-compiled filename reference patterns for the fast path in retrieve().
    # Hoisted to class level to avoid list reconstruction on every call.
    _FILENAME_REF_PATTERNS = [
        re.compile(r'(?:file\s+(?:called|named|is)\s+)([\w\-\.]+)'),
        re.compile(r'(?:check|read|look at|review|open)\s+(?:the\s+)?(?:file\s+)?([\w\-\.]{10,})'),
        re.compile(r'(?:called|named)\s+([\w\-\.]{10,})'),
        re.compile(r'([\w\-]{10,}\.(?:md|txt|pdf|docx))'),
        re.compile(r'\b((?:aquarium|setup|research|migration|report)\s+(?:research|setup|for|doc|file)?)\s*(?:for\s+kaia)?\b', re.IGNORECASE),
    ]

    def _route_retrieval_strategy(self, category: str, query_lower: str, intent: Optional[Intent]) -> Dict[str, Any]:
        """Determine the retrieval strategy and flags based on intent and category."""
        strategy = intent.suggested_strategy if intent else None
        
        is_kaia_query = (category == "identity")
        is_social_identity = (category == "social_identity")
        is_dream_query = (category == "dream")
        is_entity_query = (category == "entity")
        is_news_query = (category == "news")
        is_casual = (category == "casual" or category == "greeting" or len(query_lower.split()) <= 4)

        if strategy == "PRECISE_RECALL":
            if any(x in query_lower for x in ["who", "what", "kaia", "yourself"]):
                is_kaia_query = True
            else:
                is_entity_query = True
        elif strategy == "RELATIONAL_MIRROR":
            is_social_identity = True
        elif strategy == "DREAM_RECALL" or (strategy == "ASSOCIATIVE_WANDERING" and "dream" in query_lower):
            is_dream_query = True
        elif strategy == "SYNTHESIS_SCAN":
            is_news_query = True
        elif strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION"]:
            is_casual = True

        return {
            "strategy": strategy,
            "is_kaia_query": is_kaia_query,
            "is_social_identity": is_social_identity,
            "is_dream_query": is_dream_query,
            "is_entity_query": is_entity_query,
            "is_news_query": is_news_query,
            "is_casual": is_casual,
            "is_followup_query": (not intent and len(query_lower.split()) <= 6 and not is_kaia_query and not is_social_identity and not is_dream_query)
        }

    def _get_summarization_nodes(self, query_lower: str) -> List[Dict[str, Any]]:
        """Identify a target file for summarization and retrieve its full content."""
        # Guard: if the query is very long, it's conversational text, not a file reference.
        # Short-circuit immediately to prevent spurious document matches.
        if len(query_lower.split()) > 30:
            log_debug("_get_summarization_nodes: query too long for file reference — skipping")
            return []

        target_file_path = None
        best_match_score = 0
        
        # Strip all reference phrasing so only the filename tokens remain
        query_cleaned = query_lower
        for _strip in ["summarize", "summary of", "check the file called", "check the file named",
                       "check the file", "kaia check", "look at the file", "read the file",
                       "the file called", "the file named", "called", "named", "file"]:
            query_cleaned = query_cleaned.replace(_strip, " ")
        query_cleaned = re.sub(r'\s+', ' ', query_cleaned).strip()
        query_cleaned = re.sub(r"'s\b", "", query_cleaned)
        stopwords = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "for", "with", "on", "at", "by", "from", "you", "have", "kaia"}
        query_tokens = set(re.findall(r'\w+', query_cleaned)) - stopwords
        
        # Strip possessives from query tokens before matching
        stripped_query_tokens = {re.sub(r"'s$", "", t) for t in query_tokens}

        # Use fuzzy prefix matching — "solarsong" matches "solarsongs"
        def _tokens_match(qt, ft):
            return qt == ft or ft.startswith(qt) or qt.startswith(ft)

        for path in self.indexed_files:
            fname = os.path.basename(path).lower()
            fname_no_ext = os.path.splitext(fname)[0]
            fname_tokens = set(re.findall(r'\w+', fname_no_ext)) - stopwords
            
            if not fname_tokens: continue
            
            if query_cleaned and (query_cleaned in fname or fname_no_ext in query_cleaned):
                score = 1.0
                if score > best_match_score:
                    best_match_score = score
                    target_file_path = path
                    continue
            
            common_tokens = {
                qt for qt in stripped_query_tokens
                for ft in fname_tokens
                if _tokens_match(qt, ft)
            }
            if len(common_tokens) >= 2 or (len(common_tokens) >= 1 and any(len(t) >= 8 for t in common_tokens)):
                fname_coverage = len(common_tokens) / len(fname_tokens)
                
                # A single long distinctive token is enough to identify a specific file
                long_common = {t for t in common_tokens if len(t) >= 8}
                qualifies = (len(common_tokens) >= 2 and fname_coverage > 0.5) or \
                            (len(long_common) >= 1 and fname_coverage > 0.15)
                
                if qualifies:
                    score = fname_coverage + (0.3 if long_common else 0)
                    if score > best_match_score:
                        best_match_score = score
                        target_file_path = path

        if not target_file_path:
            return []

        log_action(f"Summarization target identified: {target_file_path}")
        from utils.core.rag_utils import get_node_text, get_node_metadata
        for itype, index in self.indices.items():
            all_docs = list(index.storage_context.docstore.docs.values())
            file_nodes = [
                n for n in all_docs 
                if n.metadata.get('file_path') == target_file_path or 
                   os.path.abspath(n.metadata.get('file_path', '')) == os.path.abspath(target_file_path)
            ]
            if file_nodes:
                file_nodes.sort(key=lambda x: x.metadata.get('chunk_index', 0))
                result_nodes = []
                for node in file_nodes:
                    meta = get_node_metadata(node)
                    meta["retrieval_method"] = "summarization"
                    result_nodes.append({
                        "content": get_node_text(node),
                        "metadata": meta,
                        "label": f"Full Content: {os.path.basename(target_file_path)}",
                        "score": 1.0
                    })
                return result_nodes
        return []


    def _target_indices(self, routing: Dict[str, Any], base_top_k: int) -> Tuple[List[str], int]:
        """Determine which indices to search and the target retrieval count."""
        strategy = routing["strategy"]
        is_kaia_query = routing["is_kaia_query"]
        is_social_identity = routing["is_social_identity"]
        is_dream_query = routing["is_dream_query"]
        is_entity_query = routing["is_entity_query"]
        is_news_query = routing["is_news_query"]
        is_casual = routing["is_casual"]
        
        target_itypes = ['knowledge', 'logs'] # Default
        retrieve_count = base_top_k

        if is_kaia_query or strategy == "PRECISE_RECALL" or is_entity_query:
            target_itypes = ['persona', 'knowledge', 'logs', 'user_profiles']
        elif strategy == "DIAGNOSTIC_DEEP_DIVE":
            target_itypes = ['logs']
            retrieve_count = 15
        elif strategy == "DREAM_RECALL" or is_dream_query:
            target_itypes = ['dreams']
            retrieve_count = 10
        elif strategy == "CREATIVE_ASSOCIATION":
            target_itypes = ['knowledge']
        elif strategy == "SOCIAL_GREETING" or is_casual:
            target_itypes = ['user_profiles', 'logs']
            retrieve_count = 10
        elif strategy == "RELATIONAL_MIRROR" or is_social_identity:
            target_itypes = ['user_profiles', 'logs']

        if is_casual and strategy != "SOCIAL_GREETING":
            retrieve_count = max(5, int(base_top_k * 0.6))

        return target_itypes, retrieve_count

    async def _execute_hybrid_retrieval(self, itype: str, query: str, retrieve_count: int, _retry_count: int = 0):
        """Perform hybrid (Vector + BM25) retrieval for a specific index type."""
        try:
            index = self.indices[itype]
            # 1. Load or Build BM25
            bm25_retriever = self.bm25_cache.get(itype)
            if not bm25_retriever:
                # Try loading from disk first
                bm25_retriever = await asyncio.to_thread(self._load_bm25_cache, itype)
                if bm25_retriever:
                    # Update cache (Protected by RLock if called from sync, but parallel-safe for async reads)
                    self.bm25_cache[itype] = bm25_retriever
                else:
                    # Cold start rebuild
                    index_nodes = list(index.storage_context.docstore.docs.values())
                    if index_nodes:
                        # Offload the potentially heavy BM25 initialization (tokenization of all nodes)
                        bm25_retriever = await asyncio.to_thread(SimpleBM25Retriever, index_nodes)
                        # Re-entrant lock check or just direct set if we assume read-only is parallel safe
                        self.bm25_cache[itype] = bm25_retriever
                        # Trigger save for next time
                        await asyncio.to_thread(self._save_bm25_cache, itype)
            
            if bm25_retriever:
                from utils.infrastructure.system.yaml_config import config
                hybrid = HybridRetriever(self.indices[itype], bm25_retriever, multiplier=config.rag_base_score_multiplier)
                return await hybrid.retrieve(query, top_k=retrieve_count)
            else:
                retriever = self.indices[itype].as_retriever(similarity_top_k=retrieve_count)
                vector_results = await retriever.aretrieve(query)
                for res in vector_results:
                    if hasattr(res, 'node'):
                        if not isinstance(res.node.metadata, dict):
                            res.node.metadata = {}
                        res.node.metadata["_retrieval_method"] = "vector"
                return vector_results
        except Exception as e:
            err_msg = str(e)
            if ("not found in fetched nodes" in err_msg or "not found in index" in err_msg) and _retry_count < 50:
                import re
                match = re.search(r"Node ID ([a-zA-Z0-9\-]+) not found", err_msg)
                if match:
                    stale_node_id = match.group(1)
                    log_warning(f"Detected stale Node ID {stale_node_id} in {itype} index. Repairing automatically...")
                    try:
                        with self._data_lock:
                            self.indices[itype].delete_nodes([stale_node_id])
                            
                            # Clean BM25 cache since index changed
                            bm25_cache_path = self._get_bm25_cache_path(itype)
                            if os.path.exists(bm25_cache_path):
                                try: os.remove(bm25_cache_path)
                                except: pass
                            self.bm25_cache.pop(itype, None)
                            self.persist_needed = True
                            
                        log_success(f"Repaired {itype} index by removing stale Node {stale_node_id} in-memory. Retrying retrieval...")
                        
                        # Defer slow disk persistence to a background thread to prevent query lag
                        asyncio.create_task(asyncio.to_thread(self.persist, force=True))
                        
                        return await self._execute_hybrid_retrieval(itype, query, retrieve_count, _retry_count + 1)
                    except Exception as repair_err:
                        log_error(f"Failed to repair {itype} index: {repair_err}")
            
            log_error(f"Retrieval failed for {itype}: {e}")
            return []

    def _resolve_identity_mappings(self, user_id: Any) -> Set[str]:
        """Resolve all linked identities (Discord/Forum) for a given user ID."""
        try:
            from utils.social.kaia_identities import registry
        except ImportError:
            return {str(user_id)} if user_id else set()
            
        u_id_str = str(user_id) if user_id else None
        relevant_ids = {u_id_str} if u_id_str else set()
        
        if u_id_str:
            for fid in registry.get_forum_ids(u_id_str):
                relevant_ids.add(str(fid))
                
            if u_id_str.startswith("forum_"):
                parts = u_id_str.rsplit("_", 1)
                if len(parts) > 1 and parts[1].isdigit():
                    did = registry.get_discord_id(int(parts[1]))
                    if did: relevant_ids.add(did)
            elif u_id_str.isdigit() and len(u_id_str) < 15:
                did = registry.get_discord_id(int(u_id_str))
                if did: relevant_ids.add(did)
        return relevant_ids

    def _score_and_filter_nodes(self, all_node_results: List[Any], query_lower: str, 
                               relevant_ids: Set[str], routing: Dict[str, Any], 
                               top_k: int, include_news: bool, strict_identity: bool) -> List[Dict[str, Any]]:
        """Rank, boost, and filter retrieved nodes based on context and strategy."""
        from utils.core.rag_utils import get_node_text, get_node_metadata
        from utils.infrastructure.system.yaml_config import config
        
        scored_nodes = []
        seen_content_hashes: set = set()  # Fix #1: deduplicate cross-index duplicate chunks
        query_words = set(re.findall(r'\w+', query_lower))
        strategy = routing["strategy"]
        is_casual = routing["is_casual"]
        is_dream_query = routing["is_dream_query"]
        is_social_identity = routing["is_social_identity"]

        # Pre-compute current time for recency decay calculations
        _now_ts = time.time()

        def _recency_decay(file_path: str, source_type: str, metadata: dict = None) -> float:
            """Returns a 0.2–1.0 multiplier. Recent = 1.0. Old = 0.2 floor.
            
            Half-life is configurable. Default: 90 days.
            Only applied to user_logs, news, and dreams — knowledge docs and persona are timeless.
            """
            if source_type not in ('user_logs', 'news', 'dream', 'kaia_reflection'):
                return 1.0  # Timeless content: no decay
            try:
                ts = 0
                # Check metadata timestamp first (accurate after indexer fix)
                if metadata:
                    ts_val = metadata.get('timestamp', 0)
                    if isinstance(ts_val, (int, float)) and ts_val > 0:
                        ts = float(ts_val)
                    elif isinstance(ts_val, str):
                        try: ts = datetime.fromisoformat(ts_val).timestamp()
                        except: pass
                # Fall back to filesystem mtime
                if not ts and file_path and os.path.exists(file_path):
                    ts = os.path.getmtime(file_path)
                if ts:
                    age_days = (_now_ts - ts) / 86400.0
                    half_life = getattr(config, 'rag_recency_half_life_days', 90)
                    decay = math.exp(-age_days * math.log(2) / half_life)
                    return max(0.2, decay)
            except Exception:
                pass
            return 1.0


        # Fix #5: Compute pool-size ratio ONCE before the per-node loop (O(1) not O(N))
        _pool_deflation_factor = 1.0
        if 'logs' in self.indices and 'knowledge' in self.indices:
            _logs_size = len(self.indices['logs'].storage_context.docstore.docs)
            _knowledge_size = len(self.indices['knowledge'].storage_context.docstore.docs)
            if _logs_size > 0 and _knowledge_size > 0:
                _ratio = _logs_size / max(_knowledge_size, 1)
                if _ratio < 0.3:  # Logs pool is less than 30% the size of knowledge
                    _pool_deflation_factor = 0.7 + 0.3 * _ratio / 0.3

        for node_result in all_node_results:
            node = node_result.node if hasattr(node_result, 'node') else node_result
            base_score = node_result.score if hasattr(node_result, 'score') else 0.5
            
            content = get_node_text(node)
            if not content: continue

            # Fix #1: Deduplicate chunks that appear in multiple index pools
            content_hash = hash(content[:200])
            if content_hash in seen_content_hashes:
                continue
            seen_content_hashes.add(content_hash)

            metadata = get_node_metadata(node)
            retrieval_method = metadata.get('_retrieval_method', 'unknown')
            
            source_type = metadata.get('source_type', 'general')
            file_path = metadata.get('file_path', '')
            node_user_id = str(metadata.get('user_id', ''))
            
            # FILTERS
            if not include_news and (source_type == 'news' or "news" in file_path.lower()): continue
            if source_type == 'user_profile' and (not (is_social_identity or strict_identity) or (node_user_id and node_user_id not in relevant_ids)): continue
            
            if source_type == 'user_logs' and file_path and strict_identity:
                try:
                    # Robust path-based isolation for user_logs
                    path_normalized = file_path.replace('\\', '/')
                    if '/user_logs/' in path_normalized:
                        user_dir = path_normalized.split('/user_logs/')[1].split('/')[0]
                        if not any(str(rid) in user_dir for rid in relevant_ids):
                            log_debug(f"RAG isolation: skipping foreign user logs path (Identity-Scoped): {file_path}")
                            continue
                except Exception as e:
                    log_debug(f"RAG isolation: path parse failed for node: {file_path} — {e}")

            # Fix #2: Path-based relevance boosting
            basename_lower = os.path.basename(file_path).lower()
            filename_words = set(re.findall(r'\w+', basename_lower))
            word_overlap = query_words & filename_words - {"for", "the", "a", "an", "to", "of", "kaia", "file", "doc", "document"}
            path_boost = 0  # Safe default — overridden below when overlap qualifies
            if len(word_overlap) >= 1:
                path_boost = 0.6 if len(word_overlap) >= 2 else (0.3 if len(word_overlap) == 1 and source_type == 'general_knowledge' else 0)

            # Fix 1: Differentiate "user-scoped" vs "topic-scoped" log retrieval
            if source_type == 'user_logs' and node_user_id:
                # For identity/personal queries: strict — only current user's logs
                if strict_identity or routing.get("is_social_identity"):
                    if node_user_id not in relevant_ids: continue
                # For general/casual queries: allow all users' logs (boosted below)
                
            # Soft dampening for general knowledge on casual queries (allows highly relevant knowledge to surface instead of blanket suppression)
            casual_knowledge_factor = 1.0
            if is_casual and source_type == 'general_knowledge' and not routing.get('is_entity_query'):
                casual_knowledge_factor = 0.75

            # Fix 3: rely solely on yaml_config for type_boosts — no inline fallback with stale keys
            boost_key = 'knowledge' if source_type == 'general_knowledge' else source_type
            type_boost = config.rag_type_boosts.get(boost_key, 0.0)
            
            # Strong bonus for the actual persona file on identity queries
            persona_file_bonus = 0.0
            if routing.get("is_kaia_query") and basename_lower == "kaia_persona.md":
                persona_file_bonus = 0.60

            final_score = (base_score + path_boost + type_boost + persona_file_bonus) * casual_knowledge_factor

            # Soft dampening for literary prose documents for non-synthesis queries (avoid total erasure)
            if source_type == 'general_knowledge' and not routing.get('is_entity_query') and not routing.get('is_news_query'):
                fname_lower = os.path.basename(file_path).lower()
                LITERARY_MARKERS = ('neuromancer', 'gibson', 'dickens', 'novel', 'fiction')
                if any(m in fname_lower for m in LITERARY_MARKERS):
                    final_score *= 0.75  # Soft dampening — allows literature to surface when relevant

            # Apply recency decay (only affects user_logs, news, dreams)
            final_score *= _recency_decay(file_path, source_type, metadata)

            # Balanced same-user boost for logs (0.15 instead of 0.30 to avoid drowning out curated documentation)
            if source_type == 'user_logs':
                if node_user_id in relevant_ids:
                    final_score += 0.15  # Moderate boost for current user's own logs
                else:
                    final_score += 0.05  # Weaker boost for other users' logs

            # Fix 2: user_logs recency is already handled by _recency_decay above
            if source_type == 'user_logs':
                
                # Echo-Dampening: Prevent conversation logs from outranking the original source files
                # by detecting when a log chunk is merely repeating the query's own terms back.
                # Fix #7: tokenize content properly (word-boundary split) instead of substring search
                # to avoid false matches like "an" matching inside "aquarium" or "plan".
                query_words_significant = [w for w in query_lower.split() 
                                           if w not in SimpleBM25Retriever.CONVERSATIONAL_STOPWORDS]
                if len(query_words_significant) > 0:
                    content_tokens = set(re.sub(r"[^\w\s]", " ", content.lower()).split())
                    words_found = sum(1 for w in query_words_significant if w in content_tokens)
                    echo_ratio = words_found / len(query_words_significant)
                    if echo_ratio > 0.7:  # Log is mostly just repeating the query back verbatim
                        final_score *= 0.6  # 40% dampening


            # AUDIT FLAG PENALTY: reduce score for nodes flagged with Data Rot constructs
            audit_flags = metadata.get('audit_flags', [])
            if audit_flags:
                flag_penalty = getattr(config, 'rag_audit_flag_penalty', 0.15)
                # Cap at 3 flags worth of penalty to avoid complete suppression
                total_penalty = min(len(audit_flags) * flag_penalty, flag_penalty * 3)
                final_score -= total_penalty

            if strategy == "PRECISE_RECALL":
                if source_type in ['knowledge', 'user_profile']: final_score += 0.15
                if source_type == 'dream': final_score -= 0.1
            elif strategy == "DIAGNOSTIC_DEEP_DIVE" and source_type == 'user_logs':
                final_score += 0.4 if any(w in content.lower() for w in ['error', 'exception', 'traceback', 'fail']) else 0.1
            elif strategy == "DREAM_RECALL":
                final_score += 0.5 if source_type == 'dream' else -0.1
            elif strategy == "RELATIONAL_MIRROR":
                if source_type == 'user_profile': final_score += 0.4
                elif source_type == 'user_logs' and node_user_id in relevant_ids: final_score += 0.25

            # Fix #5: Apply Pool Normalization using ratio pre-computed before the loop.
            if source_type == 'user_logs':
                final_score *= _pool_deflation_factor

            # THRESHOLDING
            # Priority 3: Per-strategy threshold differentiation
            if strategy == "DREAM_RECALL":
                min_threshold = 0.40
            elif strategy == "PRECISE_RECALL":
                min_threshold = config.rag_threshold_knowledge - 0.10  # Accept more candidates for specific requests
            elif strategy == "SOCIAL_GREETING":
                min_threshold = config.rag_threshold_knowledge + 0.10  # Be very strict
            else:
                min_threshold = config.rag_threshold_knowledge + (config.rag_threshold_casual_penalty if is_casual else 0)
            
            if final_score < min_threshold: continue

            # LABELING
            label = f"Knowledge [{os.path.basename(file_path)}]"
            if source_type == "persona": label = "Kaia Persona Fragment"
            elif source_type == "user_profile": label = f"Profile: {metadata.get('user_name', 'Unknown')}"
            elif source_type == "user_logs": label = f"Log: {metadata.get('user_name', 'Unknown')}"
            
            # Store retrieval method in metadata to make it accessible to !explain
            metadata["retrieval_method"] = retrieval_method
            
            scored_nodes.append({"content": content, "metadata": metadata, "label": label, "score": final_score})

        scored_nodes.sort(key=lambda x: x["score"], reverse=True)

        # Compute aggregate confidence for this result set
        top_results = scored_nodes[:top_k]
        if top_results:
            avg_score = sum(n["score"] for n in top_results) / len(top_results)
            # Normalize: scores typically 0.3–2.0 after boosting; practical ceiling 1.5
            retrieval_confidence = min(1.0, max(0.0, avg_score / 1.5))
        else:
            retrieval_confidence = 0.0

        # Store confidence as instance attributes so message_processor can read them
        # Safe because retrieve() is protected by thread_safe_rag_operation which serializes access.
        self._last_retrieval_confidence = retrieval_confidence
        self._last_retrieval_node_count = len(top_results)

        return top_results

    @thread_safe_rag_operation
    async def get_context_for_hallucination_check(self, query: str) -> str:
        """Fetch raw RAG nodes related to a query for factual verification."""
        # We bypass the complex routing and just grab raw knowledge
        return await self.retrieve(query, top_k=5, strict_identity=False, include_news=False, category="knowledge")

    @thread_safe_rag_operation
    async def retrieve(self, query: str, user_id: Any = None, user_name: str = None, top_k: int = 5, 
                strict_identity: bool = False, include_news: bool = False,
                category: str = "general", intent: Optional[Intent] = None) -> List[Dict[str, Any]]:
        if not self.indices or not query or not query.strip(): return []

        # Reset per-call retrieval metrics
        self._last_retrieval_confidence = 0.0
        self._last_retrieval_node_count = 0
        self._last_retrieval_time = time.time()
            
        try:
            query_lower = query.lower()
            routing = self._route_retrieval_strategy(category, query_lower, intent)
            
            

            if routing["strategy"] == "SUMMARIZATION":
                results = self._get_summarization_nodes(query_lower)
                if results:
                    self._last_retrieval_results = results
                    self._last_retrieval_node_ids = []
                    self._last_retrieval_confidence = 1.0
                    self._last_retrieval_node_count = len(results)
                    return results
            
            # Manifest title fast path: match query words against indexed filenames directly.
            # SAFETY GUARDS (2026-04-03 incident):
            #   - Skipped for casual/social/greeting/dream/recap queries
            #   - Requires at least one distinctive word (>= 6 chars) in the overlap
            #   - Requires minimum 30% filename coverage
            #   - Comprehensive stopword lists to prevent spurious matches on
            #     common words like "what", "why", "work", "does" appearing in titles
            _FAST_PATH_QUERY_STOPS = {
                # Articles, prepositions, conjunctions
                "the", "a", "an", "of", "and", "or", "to", "in", "is", "for",
                "with", "on", "at", "by", "from", "not", "but", "so", "if",
                # Pronouns
                "i", "me", "my", "you", "your", "he", "she", "it", "its",
                "we", "our", "they", "them", "their", "this", "that", "who",
                # Common verbs (prevent spurious matches on titles like
                # "What is ChatGPT doing and why does it work")
                "do", "does", "doing", "did", "done", "have", "has", "had",
                "am", "are", "was", "were", "been", "being",
                "can", "could", "will", "would", "should", "may", "might",
                "get", "got", "go", "going", "gone", "come", "came",
                "make", "made", "take", "took", "give", "say", "said",
                "know", "think", "want", "need", "like", "feel", "seem",
                "work", "working", "use", "try", "find", "tell", "ask",
                # Question words (critical — appear in many document titles)
                "what", "why", "how", "when", "where", "which",
                # Common adverbs/adjectives
                "just", "about", "also", "still", "even", "very", "really",
                "much", "more", "well", "now", "then", "here", "there",
                "only", "some", "any", "all", "no", "yes", "up", "out",
                # Bot-specific
                "kaia", "file", "doc", "document", "check", "look", "read",
                "chance",
            }
            _FAST_PATH_FNAME_STOPS = {
                "the", "a", "an", "for", "and", "or", "of", "to", "in", "is",
                "what", "why", "how", "when", "where", "which", "who",
                "do", "does", "doing", "did", "it", "its", "not",
                "are", "was", "were", "been", "being", "has", "have", "had",
            }
            _skip_fast_path = (
                routing.get("is_casual") or
                routing.get("is_social_identity") or
                routing.get("strategy") in (
                    "SOCIAL_GREETING", "RELATIONAL_MIRROR",
                    "DREAM_RECALL", "RECAP_QUERY",
                )
            )
            _query_words = set(re.findall(r'\w+', query_lower)) - _FAST_PATH_QUERY_STOPS
            if len(_query_words) >= 2 and not _skip_fast_path:
                _best_path = None
                _best_score = 0
                _best_overlap = set()
                for _mpath in self.indexed_files:
                    _fname = os.path.splitext(os.path.basename(_mpath))[0].lower()
                    _fname_words = set(re.findall(r'\w+', _fname)) - _FAST_PATH_FNAME_STOPS
                    if not _fname_words:
                        continue
                    _overlap = _query_words & _fname_words
                    # Require at least one distinctive word (>= 6 chars) to avoid
                    # spurious matches on short common words like "work", "does".
                    _has_distinctive = any(len(w) >= 6 for w in _overlap)
                    _score = len(_overlap) / len(_fname_words)
                    if (len(_overlap) >= 2 and _has_distinctive
                            and _score >= 0.3 and _score > _best_score):
                        _best_score = _score
                        _best_path = _mpath
                        _best_overlap = _overlap
                if _best_path:
                    log_info(f"[manifest fast path] matched '{_best_path}' with words {_best_overlap}")
                    log_debug(f"Manifest title fast path: '{_best_path}'")
                    _fname_results = self._get_summarization_nodes(
                        os.path.splitext(os.path.basename(_best_path))[0].lower()
                    )
                    if _fname_results:
                        self._last_retrieval_results = _fname_results
                        self._last_retrieval_node_ids = []
                        self._last_retrieval_confidence = 1.0
                        self._last_retrieval_node_count = len(_fname_results)
                        log_success(f"Manifest title fast path resolved {len(_fname_results)} nodes")
                        return _fname_results

            # Filename-reference fast path — runs regardless of routing strategy.
            # Catches: "check the file called X", "the file named X", "look at X.md",
            # "kaia check X", explicit filename pastes with dashes/underscores.
            for _pat in self._FILENAME_REF_PATTERNS:
                _match = _pat.search(query_lower)
                if _match:
                    _hint = _match.group(1).strip()
                    if len(_hint) >= 6:  # Ignore short accidental matches
                        log_debug(f"Filename-reference fast path triggered: '{_hint}'")
                        _fname_results = self._get_summarization_nodes(_hint)
                        if _fname_results:
                            self._last_retrieval_results = _fname_results
                            self._last_retrieval_node_ids = []
                            self._last_retrieval_confidence = 1.0
                            self._last_retrieval_node_count = len(_fname_results)
                            log_success(f"Filename fast path resolved {len(_fname_results)} nodes for '{_hint}'")
                            return _fname_results
                    break
            
            # Update user cache
            if time.time() - self._last_user_scan > self._user_scan_interval:
                def _scan():
                    path = os.path.join(self.knowledge_base_dir, "user_logs")
                    return [d.name.rsplit("_", 1)[0].replace("_", " ") for d in os.scandir(path) if d.is_dir() and "_" in d.name] if os.path.exists(path) else []
                self._known_users_cache = await asyncio.to_thread(_scan)
                self._last_user_scan = time.time()

            enriched_query = query
            detected_user = next((u for u in self._known_users_cache if u.lower() in query_lower), None)
            if detected_user: enriched_query += f" user:{detected_user} {detected_user}"
            if user_name and (routing["is_casual"] or routing["is_social_identity"]):
                enriched_query += f" user:{user_name} {user_name}"

            # Map identities
            relevant_ids = self._resolve_identity_mappings(user_id)

            # Retrieval
            target_itypes, retrieve_count = self._target_indices(routing, top_k)
            tasks = [self._execute_hybrid_retrieval(itype, enriched_query, retrieve_count) for itype in target_itypes if itype in self.indices]
            all_results_raw = await asyncio.gather(*tasks, return_exceptions=True)
            all_node_results = []
            for i, sublist in enumerate(all_results_raw):
                if isinstance(sublist, Exception):
                    log_warning(f"Retrieval task {i} failed: {sublist}")
                    continue
                all_node_results.extend(sublist)
            # Cache raw results BEFORE filtering for !explain
            self._last_raw_results = all_node_results
            
            # Scoring & Filtering
            results = self._score_and_filter_nodes(all_node_results, query_lower, relevant_ids, routing, top_k, include_news, strict_identity)
            if results: log_success(f"RAG retrieved {len(results)} nodes")

            # Cache results for !flag and !explain commands
            self._last_retrieval_results = results
            self._last_retrieval_node_ids = []
            for node_result in all_node_results[:top_k * 2]:
                node = node_result.node if hasattr(node_result, 'node') else node_result
                node_id = getattr(node, 'node_id', None) or getattr(node, 'id_', None)
                if node_id:
                    self._last_retrieval_node_ids.append(node_id)

            return results

            
        except Exception as e:
            log_error(f"Error during retrieval: {e}")
            traceback.print_exc()
            return []

    def get_recent_highlights(self, hours: int = 24, limit: int = 5) -> List[str]:
        """
        Scan logs for interesting or unique recent events.
        
        Returns a list of text snippets from recent high-priority or unique logs.
        """
        if not self.indices or 'logs' not in self.indices:
            return []
            
        from utils.core.rag_utils import get_node_text
        try:
            cutoff = time.time() - (hours * 3600)
            
            # Get nodes from logs index
            # This is a bit expensive but necessary for a true "history scan"
            docstore = self.indices['logs'].storage_context.docstore
            all_nodes = list(docstore.docs.values())
            
            recent_nodes = []
            for node in all_nodes:
                ts = 0
                file_path = node.metadata.get('file_path', '')
                
                # 1. Try metadata fields: explicit timestamp, last_modified_at, mtime
                for field in ('timestamp', 'last_modified_at', 'mtime'):
                    ts_val = node.metadata.get(field)
                    if ts_val:
                        if isinstance(ts_val, (int, float)):
                            ts = float(ts_val)
                        elif isinstance(ts_val, str):
                            try:
                                if "_" in ts_val and len(ts_val) == 15:
                                    ts = datetime.strptime(ts_val, "%Y%m%d_%H%M%S").timestamp()
                                else:
                                    ts = datetime.fromisoformat(ts_val).timestamp()
                            except Exception:
                                pass
                        if ts > 0:
                            break  # Found a valid timestamp, stop trying

                # 2. Extract date from file_path (e.g. interactions_20260311.md)
                if ts == 0 and file_path:
                    m = re.search(r'(\d{8})', os.path.basename(file_path))
                    if m:
                        try:
                            # Add 23h 59m 59s to make it the END of that day, not midnight
                            dt = datetime.strptime(m.group(1), "%Y%m%d")
                            dt = dt.replace(hour=23, minute=59, second=59)
                            ts = dt.timestamp()
                        except Exception:
                            pass

                # 3. Last resort: Real file system mtime
                if ts == 0 and file_path and os.path.exists(file_path):
                    ts = os.path.getmtime(file_path)

                if ts > cutoff:
                    recent_nodes.append(node)
            
            if not recent_nodes:
                return []
                
            # Score nodes by "interest" (heuristic)
            scored_highlights = []
            for node in recent_nodes:
                content = get_node_text(node).strip()
                if len(content) < 10: continue
                
                # Base score + jitter for variety
                score = 1.0 + (random.random() * 0.5)
                
                # Boost if contains "kaia" or bot interaction
                if "kaia" in content.lower():
                    score += 0.5
                
                # Boost if error-like (dry observation fodder)
                if any(word in content.lower() for word in ["failed", "error", "timeout", "re-warming", "nuke"]):
                    score += 1.2
                    
                # Small boost for memories
                if node.metadata.get('source') == 'memory':
                    score += 0.8
                
                # Specific keyword boosts for variety
                if any(word in content.lower() for word in ["ekco", "coffee", "stale"]):
                    score -= 0.3 # Penalize the "overused" topics slightly to favor others
                    
                scored_highlights.append((score, content))
            
            # Sort by score and take top N
            scored_highlights.sort(key=lambda x: x[0], reverse=True)
            results = [text for score, text in scored_highlights[:limit]]
            
            # Shuffle final results slightly so they aren't always in the same order
            random.shuffle(results)
            return results
            
        except Exception as e:
            log_error(f"Failed to get highlights: {e}")
            return []

    def search_recent_events(self, query: str, hours: int = 24, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for specific recent events in the logs.
        Similar to get_recent_highlights but targeted with a query.
        """
        self._last_retrieval_confidence = 0.5 # Prevent EMA corruption if no nodes found
        if not self.indices or 'logs' not in self.indices:
            return []
            
        try:
            cutoff = time.time() - (hours * 3600)
            docstore = self.indices['logs'].storage_context.docstore
            all_nodes = list(docstore.docs.values())
            
            recent_nodes = []
            for node in all_nodes:
                ts = 0
                file_path = node.metadata.get('file_path', '')
                
                # Priority 1: metadata fields
                for field in ('timestamp', 'last_modified_at', 'mtime'):
                    ts_val = node.metadata.get(field)
                    if ts_val:
                        if isinstance(ts_val, (int, float)):
                            ts = float(ts_val)
                        elif isinstance(ts_val, str):
                            try:
                                if "_" in ts_val and len(ts_val) == 15:
                                    ts = datetime.strptime(ts_val, "%Y%m%d_%H%M%S").timestamp()
                                else:
                                    ts = datetime.fromisoformat(ts_val).timestamp()
                            except Exception:
                                pass
                        if ts > 0:
                            break  # Found a valid timestamp, stop trying

                # Priority 2: filename date
                if ts == 0 and file_path:
                    m = re.search(r'(\d{8})', os.path.basename(file_path))
                    if m:
                        try:
                            # Add 23h 59m 59s to make it the END of that day, not midnight
                            dt = datetime.strptime(m.group(1), "%Y%m%d")
                            dt = dt.replace(hour=23, minute=59, second=59)
                            ts = dt.timestamp()
                        except Exception:
                            pass

                # Priority 3: filesystem mtime (fallback)
                if ts == 0 and file_path and os.path.exists(file_path):
                    ts = os.path.getmtime(file_path)

                if ts > cutoff:
                    recent_nodes.append(node)
            
            if not recent_nodes:
                return []

            # Simple keyword matching for "search" among recent nodes
            scored_events = []
            
            from utils.core.kaia_rag_retriever import SimpleBM25Retriever
            stopwords = set(SimpleBM25Retriever.CONVERSATIONAL_STOPWORDS)
            query_words = [w for w in query.lower().split() if w not in stopwords and len(w) > 2]
            
            from utils.core.rag_utils import get_node_text
            
            if query_words:
                for node in recent_nodes:
                    c_text = get_node_text(node)
                    content = c_text.lower()
                    matches = sum(1 for word in query_words if word in content)
                    if matches > 0:
                        scored_events.append((matches, c_text.strip(), node.metadata))
            
            if not scored_events:
                # Fall back: return all recent nodes sorted by recency
                fallback = []
                for node in recent_nodes:
                    c_text = get_node_text(node).strip()
                    if len(c_text) < 10:
                        continue
                    ts = node.metadata.get('timestamp', 0)
                    if isinstance(ts, str):
                        try: ts = datetime.fromisoformat(ts).timestamp()
                        except: ts = 0
                    if not ts:
                        # Fallback for recency computation
                        f_path = node.metadata.get('file_path', '')
                        if f_path and os.path.exists(f_path):
                            ts = os.path.getmtime(f_path)
                    fallback.append((ts, c_text, node.metadata))
                fallback.sort(key=lambda x: x[0], reverse=True)
                
                top_fallback = [
                    {
                        "content": text,
                        "metadata": {
                            "source_type": "user_logs", 
                            "file_path": meta.get("file_path", "") or meta.get("doc_id", "unknown"), 
                            "retrieval_method": "fallback"
                        },
                        "label": f"Recent Log: {os.path.basename(meta.get('file_path') or 'unknown')}",
                        "score": 0.3,
                    }
                    for _, text, meta in fallback[:limit]
                ]
                self._last_retrieval_results = top_fallback
                self._last_retrieval_confidence = 0.3
                self._last_retrieval_node_count = len(fallback)
                return top_fallback

            # Set retrieval confidence for observational queries (Bug fix: neutral 0.5 floor)
            self._last_retrieval_confidence = 0.5
            self._last_retrieval_node_count = len(scored_events)

            scored_events.sort(key=lambda x: x[0], reverse=True)

            max_matches = scored_events[0][0] if scored_events else 1

            # Keep the structured format for both internal caching and returning, mirroring `retrieve()`
            top_results = [
                {
                    "content": text,
                    "metadata": {
                        "source_type": "user_logs",
                        "file_path": meta.get("file_path", "") or meta.get("doc_id", "unknown"),
                        "retrieval_method": "search"
                    },
                    "label": f"Recent Log: {os.path.basename(meta.get('file_path') or 'unknown')}",
                    "score": round(0.3 + (0.5 * (matches / max(max_matches, 1))), 3),
                }
                for matches, text, meta in scored_events[:limit]
            ]
            self._last_retrieval_results = top_results
            self._last_retrieval_confidence = 0.5
            self._last_retrieval_node_count = len(scored_events)

            return top_results
            
        except Exception as e:
            log_error(f"Failed to search recent events: {e}")
            return []


