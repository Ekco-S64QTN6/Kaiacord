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
                return [{
                    "content": get_node_text(node),
                    "metadata": get_node_metadata(node),
                    "label": f"Full Content: {os.path.basename(target_file_path)}",
                    "score": 1.0
                } for node in file_nodes]
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

    async def _execute_hybrid_retrieval(self, itype: str, query: str, retrieve_count: int):
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
        strategy = routing["strategy"]
        is_casual = routing["is_casual"]
        is_dream_query = routing["is_dream_query"]
        is_social_identity = routing["is_social_identity"]

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
            
            # Fix 1: Differentiate "user-scoped" vs "topic-scoped" log retrieval
            if source_type == 'user_logs' and node_user_id:
                # For identity/personal queries: strict — only current user's logs
                if strict_identity or routing.get("is_social_identity"):
                    if node_user_id not in relevant_ids: continue
                # For general/casual queries: allow all users' logs (boosted below)
                
            # Fix 3: Add a casual query hard cap on general_knowledge
            if is_casual and source_type == 'general_knowledge' and not routing.get('is_entity_query'):
                continue  # Books have no business in casual chitchat

            if is_dream_query and not (source_type == 'dream' or "kaia_dreams" in file_path or "dream" in content.lower()): continue

            # SCORING
            basename_lower = os.path.basename(file_path).lower() if file_path else ""
            query_words = set(query_lower.split())
            filename_words = set(basename_lower.replace("_", " ").replace("-", " ").split())
            word_overlap = query_words & filename_words - {"for", "the", "a", "an", "to", "of", "kaia", "file", "doc", "document"}
            # Fix #2: use 'general_knowledge' (the actual assigned source_type) not 'knowledge'
            path_boost = 0.6 if len(word_overlap) >= 2 else (0.3 if len(word_overlap) == 1 and source_type == 'general_knowledge' else 0)
            # Fix #3: rely solely on yaml_config for type_boosts — no inline fallback with stale keys
            boost_key = 'knowledge' if source_type == 'general_knowledge' else source_type
            type_boost = config.rag_type_boosts.get(boost_key, 0.0)
            
            # Strong bonus for the actual persona file on identity queries
            persona_file_bonus = 0.0
            if routing.get("is_kaia_query") and basename_lower == "kaia_persona.md":
                persona_file_bonus = 0.60

            final_score = base_score + path_boost + type_boost + persona_file_bonus

            # Fix 1 (Scoring): Same-user boost for logs
            if source_type == 'user_logs':
                if node_user_id in relevant_ids:
                    final_score += 0.30  # Strong boost for current user's own logs
                else:
                    final_score += 0.10  # Weaker boost — still preferred over fiction

            # Fix 2: Add recency decay for user_logs
            if source_type == 'user_logs':
                try:
                    if file_path and os.path.exists(file_path):
                        file_mtime = os.path.getmtime(file_path)
                        days_old = (time.time() - file_mtime) / 86400
                        recency_boost = max(0.0, 0.20 * (1 - days_old / 30))  # fades to 0 over 30 days
                        final_score += recency_boost
                except Exception:
                    pass
                
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
        return scored_nodes[:top_k]

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
            
        try:
            query_lower = query.lower()
            routing = self._route_retrieval_strategy(category, query_lower, intent)
            if routing["strategy"] == "SUMMARIZATION":
                results = self._get_summarization_nodes(query_lower)
                if results: return results
            
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
                ts_val = node.metadata.get('timestamp')
                if ts_val:
                    if isinstance(ts_val, str):
                        try:
                            # Try custom format first, then ISO
                            if "_" in ts_val and len(ts_val) == 15:
                                dt = datetime.strptime(ts_val, "%Y%m%d_%H%M%S")
                                ts = dt.timestamp()
                            else:
                                ts = datetime.fromisoformat(ts_val).timestamp()
                        except Exception:
                            ts = 0
                    else:
                        ts = ts_val
                        
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

    def search_recent_events(self, query: str, hours: int = 24, limit: int = 5) -> List[str]:
        """
        Search for specific recent events in the logs.
        Similar to get_recent_highlights but targeted with a query.
        """
        if not self.indices or 'logs' not in self.indices:
            return []
            
        try:
            cutoff = time.time() - (hours * 3600)
            docstore = self.indices['logs'].storage_context.docstore
            all_nodes = list(docstore.docs.values())
            
            recent_nodes = []
            for node in all_nodes:
                ts_val = node.metadata.get('timestamp')
                ts = 0
                if ts_val:
                    if isinstance(ts_val, str):
                        try:
                            if "_" in ts_val and len(ts_val) == 15:
                                dt = datetime.strptime(ts_val, "%Y%m%d_%H%M%S")
                                ts = dt.timestamp()
                            else:
                                ts = datetime.fromisoformat(ts_val).timestamp()
                        except Exception: pass
                    else:
                        ts = ts_val
                
                if ts > cutoff:
                    recent_nodes.append(node)
            
            if not recent_nodes:
                return []

            # Simple keyword matching for "search" among recent nodes
            scored_events = []
            query_words = query.lower().split()
            
            from utils.core.rag_utils import get_node_text
            for node in recent_nodes:
                c_text = get_node_text(node)
                content = c_text.lower()
                matches = sum(1 for word in query_words if word in content)
                if matches > 0:
                    scored_events.append((matches, c_text.strip()))
            
            scored_events.sort(key=lambda x: x[0], reverse=True)
            return [text for score, text in scored_events[:limit]]
            
        except Exception as e:
            log_error(f"Failed to search recent events: {e}")
            return []


