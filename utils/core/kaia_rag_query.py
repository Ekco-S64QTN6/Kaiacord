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
import random
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Set

from llama_index.core.schema import NodeWithScore

from utils.infrastructure.logging.kaia_logger import (
    log_success, log_info, log_warning, log_error, log_action, log_debug
)
from utils.infrastructure.system.yaml_config import config
from utils.core.kaia_rag_retriever import (
    SimpleBM25Retriever, HybridRetriever, thread_safe_rag_operation
)
from utils.core.context_optimizer import Intent


# Knowledge candidates fetched for a news turn, so recency has a field to rank.
NEWS_CANDIDATE_POOL = 30
# The newest briefs offered to a news turn regardless of similarity.
LATEST_NEWS_FILES = 3
# A news turn asking for what is current, not for a period it names.
_FRESH_NEWS = re.compile(r"\b(?:latest|today|tonight|recent(?:ly)?|current|this week|now|new|yesterday|breaking)\b", re.I)
# A question that names when, so age is not a reason to rank news down.
_NAMED_PERIOD = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"last (?:week|month|year|spring|summer|autumn|fall|winter)|20\d\d|\d+ (?:days|weeks|months) ago)\b", re.I)
_QUESTION_OPENER = re.compile(r"\s*(?:kaia[,\s]+)?(?:who|what|when|where|why|how|which|tell me|explain|define|describe)\b")
# Words of five letters or more that are small talk, not a topic.
_CHATTER = frozenset("""
hello there thanks thank sorry night morning evening today tonight doing going
really right sleep tired about think where which whats what's still again maybe
anyone anybody someone thoughts okay sounds guess
""".split())
# How much a chat log counts on a news turn, and the cue that restores it.
NEWS_TURN_LOG_WEIGHT = 0.6
_CONVERSATION_CUE = re.compile(r"\b(?:we|us|our|you said|i said|remember|talked|told)\b", re.I)
# Words in a news question that are not its topic.
_NEWS_FILLER = frozenset("""
news headlines headline latest today tonight recent recently current events this week now new
yesterday breaking what what's whats about any anything happening happened going with the
tell give show and for are there has have been kaia you your me some from over
""".split())


def _trace_whole_document(query: str, results, channel=None) -> None:
    """Record a whole-document retrieval in the !explain trace.

    These paths return before the ordinary record, so `!explain` showed the
    previous retrieval under the next reply, with no question attached.
    """
    try:
        from utils.infrastructure.monitoring.retrieval_trace import record
        record(query, 1.0, results, channel=channel)
    except Exception:
        pass


# Days for a source's weight to halve with age. A news brief is stale in
# weeks, a conversation in months, a dream's reflection slower still.
# `performance.rag_recency_half_life_days` sets the chat-log value;
# `performance.rag_recency_half_life_by_type` overrides any type.
RECENCY_HALF_LIFE_DAYS = {"user_logs": 90, "news": 30, "dream": 180, "kaia_reflection": 180}


def recency_half_lives(config) -> dict:
    lives = dict(RECENCY_HALF_LIFE_DAYS)
    number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
    try:
        logs = config.get("performance.rag_recency_half_life_days", None)
        if number(logs):
            lives["user_logs"] = float(logs)
        by_type = config.get("performance.rag_recency_half_life_by_type", None)
        if isinstance(by_type, dict):
            lives.update({str(k): float(v) for k, v in by_type.items() if number(v)})
    except Exception:
        pass
    return lives


class RAGQueryMixin:
    """Mixin class providing retrieval and query methods for KaiaRAG."""

    # Pre-compiled filename reference patterns for the fast path in retrieve().
    # Hoisted to class level to avoid list reconstruction on every call.
    _FILENAME_REF_PATTERNS = [
        # Explicit file mentions: "the file X", "file called X", "article named X"
        re.compile(r'\b(?:the\s+)?(?:file|doc|document|article|whitepaper|paper)\s+(?:called\s+|named\s+|is\s+|labeled\s+)?["\']?([\w\-\.]{4,})["\']?', re.IGNORECASE),
        # Action cues: "summarize/check/read/explain/review/look at/tell me about the file X"
        re.compile(r'(?:summarize|summary\s+of|tell\s+me\s+about|what\s+is\s+in|what\s+does\s+.*?\s+say|explain|review|check|read|look\s+at|open|breakdown\s+of|browse)\s+(?:the\s+)?(?:file\s+|doc\s+|document\s+|article\s+|paper\s+|whitepaper\s+)?(?:called\s+|named\s+)?["\']?([\w\-\.]{4,})["\']?', re.IGNORECASE),
        # Explicit filename with standard extension (.md, .txt, .pdf, .docx, .json, .yaml)
        re.compile(r'\b([\w\-]{4,}\.(?:md|txt|pdf|docx|json|yaml|yml))\b', re.IGNORECASE),
        # Date-prefixed slugs: "2026-09-01_apollo-ai-labor-market-impact"
        re.compile(r'\b(\d{4}-\d{2}-\d{2}[-_][\w\-]{4,})\b', re.IGNORECASE),
        # Multi-hyphenated or multi-underscore slugs: "the-rise-and-fall-of-agent-civilizations"
        re.compile(r'\b([a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+){2,})\b'),
        # Specific named research documents
        re.compile(r'\b((?:aquarium|setup|research|migration|report|apollo|backsliding|agent-civilizations|agent\s+civilizations)\s+(?:research|setup|for|doc|file|whitepaper|article|report)?)\s*(?:for\s+kaia)?\b', re.IGNORECASE),
    ]

    # Does this turn ask about a document at all? The filename patterns above
    # are loose on their own — "explain this", "state-of-the-art" and the bare
    # word "research" all match — and both shortcuts below replace retrieval
    # with one whole document at full confidence. On their own they fired on
    # idle quips ("ai" and "international" shared with a report title) and on
    # ordinary conversation. A turn has to name a document, or carry an
    # explicit filename, before either shortcut or summarisation routing runs.
    _DOC_CUE = re.compile(
        r"\b(?:documents?|docs?|reports?|articles?|papers?|whitepapers?|files?|"
        r"transcripts?|essays?|books?|pdfs?|summar(?:y|ies|i[sz]e))\b"
        r"|\b[\w\-]{4,}\.(?:md|txt|pdf|docx|json|ya?ml)\b"
        r"|\b\d{4}-\d{2}-\d{2}[-_][\w\-]{4,}\b",
        re.IGNORECASE)

    @classmethod
    def _is_document_request(cls, query_lower: str) -> bool:
        return bool(cls._DOC_CUE.search(query_lower))

    @staticmethod
    def _own_words(query: str) -> str:
        """What the user typed, lowercased: no reply context, fetched page or URL.

        Whether a turn asks for a stored document is a question about the
        user's words. Asked of the whole enriched turn, a pasted link whose
        page said "document" and "memory systems" was routed as a request to
        summarise the HyMem paper, and its sixteen chunks became the context
        for a reply about something else.
        """
        from utils.core.sanitizer import user_authored_text
        own = user_authored_text(query or "")
        return re.sub(r"\S+://\S+", " ", own).lower()

    def _route_retrieval_strategy(self, category: str, query_lower: str, intent: Optional[Intent],
                                  own_lower: Optional[str] = None) -> Dict[str, Any]:
        """Determine the retrieval strategy and flags based on intent and category."""
        strategy = intent.suggested_strategy if intent else None
        
        is_kaia_query = (category == "identity")
        is_social_identity = (category == "social_identity")
        is_dream_query = (category == "dream")
        is_entity_query = (category == "entity")
        is_news_query = (category == "news")
        is_casual = (category == "casual" or category == "greeting"
                     or (len(query_lower.split()) <= 4 and not self._is_short_question(query_lower)))

        # Detect explicit document/file review or summarization requests
        is_doc_query = False
        is_code_or_log = (
            "```" in query_lower or
            "traceback" in query_lower or
            "calling ollama" in query_lower or
            "action:" in query_lower or
            "error:" in query_lower or
            "log_info" in query_lower
        )
        own = query_lower if own_lower is None else own_lower
        if not is_code_or_log and self._is_document_request(own):
            for pat in self._FILENAME_REF_PATTERNS:
                if pat.search(own):
                    is_doc_query = True
                    break

        if is_doc_query and (strategy in [None, "EXPLORATORY_DIALOGUE", "PRECISE_RECALL", "CREATIVE_ASSOCIATION"] or any(w in own for w in ["summarize", "summary", "overview", "breakdown", "what is in", "what does", "about", "read", "check"])):
            strategy = "SUMMARIZATION"

        if strategy == "PRECISE_RECALL":
            # About her only when she is the subject. Nearly every message
            # opens by addressing her, so "kaia" at the start says nothing, and
            # "who"/"what" as substrings matched "whole" and "whatever": "kaia,
            # tell me about Neuromancer" was routed as a question about Kaia,
            # which damps book prose.
            subject = re.sub(r"^\W*kaia\b\W*", "", own)
            if re.search(r"\b(you|your|yours|yourself|kaia)\b", subject):
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

    def _get_summarization_nodes(self, query_lower: str, target_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Identify a target file for summarization and retrieve its content."""
        # Stopword set and query token set are needed on BOTH branches below: the fast
        # path skips filename matching entirely but still feeds query_words into the
        # relevance scoring for middle-chunk selection further down. Bind them up front
        # so query_words can never be referenced before assignment.
        stopwords = {
            "the", "a", "an", "of", "and", "or", "to", "in", "is", "for", "with",
            "on", "at", "by", "from", "you", "have", "kaia", "about", "what", "how"
        }
        query_words = {
            re.sub(r"'s$", "", t)
            for t in (set(re.findall(r'\w+', query_lower)) - stopwords)
            if not t.isdigit()
        }

        # Fast path if explicit target_path was already resolved by caller
        if target_path and target_path in self.indexed_files:
            target_file_path = target_path
            best_match_score = 100.0
        else:
            # Guard: if the query is very long, it's conversational text, not a file reference.
            if len(query_lower.split()) > 35:
                log_debug("_get_summarization_nodes: query too long for file reference — skipping")
                return []

            target_file_path = None
            best_match_score = 0
            
            # Strip all reference phrasing and bot name so only filename/title tokens remain
            query_cleaned = query_lower
            for _strip in [
                "summarize", "summary of", "check the file called", "check the file named",
                "check the file", "kaia check", "look at the file", "read the file",
                "the file called", "the file named", "called", "named", "file", "doc",
                "document", "article", "whitepaper", "paper", "tell me about", "what is in",
                "what does", "say", "explain", "review", "can you", "please", "give me a",
                "overview of", "breakdown of"
            ]:
                query_cleaned = query_cleaned.replace(_strip, " ")
            query_cleaned = re.sub(r'\bkaia\b', ' ', query_cleaned, flags=re.IGNORECASE)
            query_cleaned = re.sub(r'\s+', ' ', query_cleaned).strip()
            query_cleaned = re.sub(r"'s\b", "", query_cleaned)
            
            # Refine the pre-bound token set using the phrase-stripped query, which is a
            # better signal for filename matching than the raw query.
            raw_query_tokens = set(re.findall(r'\w+', query_cleaned)) - stopwords
            query_words = {re.sub(r"'s$", "", t) for t in raw_query_tokens if not t.isdigit()}
            
            def _tokens_match(qt, ft):
                return qt == ft or ft.startswith(qt) or qt.startswith(ft)

            # Snapshot: background indexing mutates this dict concurrently, which
            # raised "dictionary changed size during iteration" and aborted the
            # whole retrieval (kaiacord.log, 00:34:54).
            for path, meta in list(self.indexed_files.items()):
                fname = os.path.basename(path).lower()
                fname_no_ext = os.path.splitext(fname)[0]
                clean_slug = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}[-_]', '', fname_no_ext)
                doc_title = (meta.get("title", "") if isinstance(meta, dict) else "").lower()

                score = 0.0
                # 1. Hierarchical exact and substring matches (highest priority)
                if query_cleaned:
                    if fname == query_cleaned or fname_no_ext == query_cleaned:
                        score = 100.0 + len(fname_no_ext)
                    elif fname in query_cleaned or fname_no_ext in query_cleaned:
                        score = 80.0 + len(fname_no_ext)
                    elif clean_slug and clean_slug == query_cleaned:
                        score = 60.0 + len(clean_slug)
                    elif clean_slug and clean_slug in query_cleaned:
                        score = 40.0 + len(clean_slug)
                    elif doc_title:
                        if doc_title == query_cleaned:
                            score = 50.0 + len(doc_title)
                        elif len(doc_title) >= 4 and re.search(rf'\b{re.escape(doc_title)}\b', query_cleaned):
                            score = 20.0 + len(doc_title)
                
                # 2. Token overlap matching (fallback if no direct filename or title match)
                if score < 20.0:
                    fname_words = {w for w in re.findall(r'\w+', clean_slug) if not w.isdigit()} - stopwords
                    if not fname_words:
                        fname_words = {w for w in re.findall(r'\w+', fname_no_ext) if not w.isdigit()} - stopwords
                    if fname_words:
                        common_tokens = {
                            qt for qt in query_words
                            for ft in fname_words
                            if _tokens_match(qt, ft)
                        }
                        if len(common_tokens) >= 2 or (len(common_tokens) >= 1 and any(len(t) >= 8 for t in common_tokens)):
                            fname_coverage = len(common_tokens) / len(fname_words)
                            long_common = {t for t in common_tokens if len(t) >= 8}
                            qualifies = (len(common_tokens) >= 2 and fname_coverage > 0.4) or \
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
        
        # Fast direct lookup via indexed_files manifest
        target_meta = self.indexed_files.get(target_file_path, {})
        target_itype = target_meta.get("itype") if isinstance(target_meta, dict) else None
        node_ids = target_meta.get("nodes", []) if isinstance(target_meta, dict) else []
        
        file_nodes = []
        if target_itype and target_itype in self.indices and node_ids:
            docstore = self.indices[target_itype].storage_context.docstore
            for nid in node_ids:
                try:
                    node = docstore.get_document(nid)
                    if node:
                        file_nodes.append(node)
                except Exception:
                    pass

        # Fallback: scan indices if direct lookup produced no nodes
        if not file_nodes:
            for itype, index in self.indices.items():
                all_docs = list(index.storage_context.docstore.docs.values())
                matching = [
                    n for n in all_docs 
                    if n.metadata.get('file_path') == target_file_path or 
                       os.path.abspath(n.metadata.get('file_path', '')) == os.path.abspath(target_file_path)
                ]
                if matching:
                    file_nodes = matching
                    break

        if not file_nodes:
            return []

        file_nodes.sort(key=lambda x: x.metadata.get('chunk_index', 0))

        # Smart chunk budgeting for large documents (>16 chunks)
        # Keeps initial executive overview, query-relevant middle chunks, and final conclusions
        selected_nodes = file_nodes
        if len(file_nodes) > 16:
            head_nodes = file_nodes[:8]
            tail_nodes = file_nodes[-4:]
            
            # Find query-relevant middle chunks if specific query terms exist
            middle_candidates = file_nodes[8:-4]
            selected_middle = []
            if query_words and middle_candidates:
                def _node_relevance(n):
                    txt = get_node_text(n).lower()
                    return sum(1 for w in query_words if w in txt)
                middle_candidates_scored = sorted(middle_candidates, key=_node_relevance, reverse=True)
                selected_middle = [n for n in middle_candidates_scored[:4] if _node_relevance(n) > 0]
            if not selected_middle:
                selected_middle = middle_candidates[:4]
                
            combined = {getattr(n, 'node_id', getattr(n, 'id_', str(idx))): n for idx, n in enumerate(head_nodes + selected_middle + tail_nodes)}
            selected_nodes = sorted(combined.values(), key=lambda x: x.metadata.get('chunk_index', 0))

        result_nodes = []
        for node in selected_nodes:
            meta = get_node_metadata(node)
            meta["retrieval_method"] = "summarization"
            result_nodes.append({
                "content": get_node_text(node),
                "metadata": meta,
                "label": f"Full Content: {os.path.basename(target_file_path)}",
                "score": 1.0
            })
        return result_nodes



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
            target_itypes = ['knowledge', 'logs', 'user_profiles']
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
            # Built in memory after each index change: 0.6 s for ~5,800
            # knowledge nodes, off the loop. There is no disk cache — the pickle
            # this replaced was never once written (it was saved before it was
            # built) and a rebuild costs about what loading one would.
            bm25_retriever = self.bm25_cache.get(itype)
            if not bm25_retriever:
                index_nodes = list(index.storage_context.docstore.docs.values())
                if index_nodes:
                    bm25_retriever = SimpleBM25Retriever(index_nodes)
                    await bm25_retriever.initialize_async()
                    self.bm25_cache[itype] = bm25_retriever
            
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
                            self._delete_nodes(itype, [stale_node_id])
                            
                            # The index changed; BM25 rebuilds on next use
                            self.bm25_cache.pop(itype, None)
                            self.persist_needed = True
                            
                        log_success(f"Repaired {itype} index by removing stale Node {stale_node_id} in-memory. Retrying retrieval...")
                        
                        # Persist off the query path — once. A retrieval can repair
                        # up to 50 stale nodes, and one full persist per repair put
                        # several threads writing the same index files at once.
                        # persist_needed is set above, so a repair made while a
                        # persist is already running is written by the next one.
                        if not getattr(self, "_repair_persist_running", False):
                            self._repair_persist_running = True

                            def _persist_once():
                                try:
                                    self.persist(force=True)
                                finally:
                                    self._repair_persist_running = False

                            from utils.infrastructure.monitoring.async_task_registry import task_registry
                            task_registry.register(
                                f"rag_repair_persist_{itype}",
                                asyncio.create_task(asyncio.to_thread(_persist_once)))
                        
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
        _half_lives = recency_half_lives(config)

        def _recency_decay(file_path: str, source_type: str, metadata: dict = None) -> float:
            """Returns a 0.2–1.0 multiplier. Recent = 1.0. Old = 0.2 floor.
            
            Half-life per source type (RECENCY_HALF_LIFE_DAYS).
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
                        # Bare `except` here also caught KeyboardInterrupt and
                        # SystemExit, in a loop that runs over every node of every
                        # retrieval — so a Ctrl-C landing inside it was silently
                        # discarded and the shutdown ignored.
                        try: ts = datetime.fromisoformat(ts_val).timestamp()
                        except (ValueError, TypeError): pass
                # Fall back to filesystem mtime
                if not ts and file_path and os.path.exists(file_path):
                    ts = os.path.getmtime(file_path)
                if ts:
                    age_days = (_now_ts - ts) / 86400.0
                    half_life = _half_lives.get(source_type, _half_lives['user_logs'])
                    decay = math.exp(-age_days * math.log(2) / half_life)
                    return max(0.2, decay)
            except Exception:
                pass
            return 1.0


        # Fix #5: Compute pool-size ratio ONCE before the per-node loop (O(1) not O(N))
        _pool_deflation_factor = 1.0
        if 'logs' in self.indices and 'knowledge' in self.indices:
            # nodes_dict, not docstore.docs: the latter deserialises every
            # node to count them, ~160 ms on every retrieval.
            _logs_size = len(self.indices['logs'].index_struct.nodes_dict)
            _knowledge_size = len(self.indices['knowledge'].index_struct.nodes_dict)
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

            final_score = (base_score + path_boost + type_boost) * casual_knowledge_factor

            # Soft dampening of literary prose on non-synthesis queries, to stop
            # novel prose bleeding into unrelated conversation. Damped, not
            # erased.
            #
            # `path_boost` exempts it: that flag means the query's own words are
            # in the filename, and a query naming a work is the most relevant that
            # work will ever be. Without the exemption, asking for a book ranks
            # everyone who mentioned it above the book itself.
            if (source_type == 'general_knowledge' and not path_boost
                    and not routing.get('is_entity_query') and not routing.get('is_news_query')):
                fname_lower = os.path.basename(file_path).lower()
                LITERARY_MARKERS = ('neuromancer', 'gibson', 'dickens', 'novel', 'fiction')
                if any(m in fname_lower for m in LITERARY_MARKERS):
                    final_score *= 0.75  # Soft dampening — allows literature to surface when relevant

            # Apply recency decay (only affects user_logs, news, dreams) —
            # except to news when the question names its own period ("in
            # June"): decaying by age then buries exactly what was asked for.
            if not (source_type == 'news' and routing.get('names_period')):
                final_score *= _recency_decay(file_path, source_type, metadata)

            # On a news turn the news answers it. A chat log that shares the
            # topic ranked above the digests, and a remark of Ekco's about
            # finding exploits in P99 with AI came back as a Hacker News story.
            # Asked about the conversation itself, logs keep their weight.
            if (routing.get('is_news_query') and source_type == 'user_logs'
                    and not _CONVERSATION_CUE.search(query_lower)):
                final_score *= NEWS_TURN_LOG_WEIGHT

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
            
            scored_nodes.append({"content": content, "metadata": metadata, "label": label,
                                 "score": final_score,
                                 "node_id": getattr(node, 'node_id', None) or getattr(node, 'id_', None)})

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
    def _latest_news_candidates(self, pool, query_lower: str = "", n_files: int = LATEST_NEWS_FILES):
        """The newest briefs' chunks on the question's topic, at the pool's median score.

        Similarity cannot see "latest": in a year of coverage the best match
        for a topic is whichever month covered it most, and this week's brief
        never reached the pool. Offering the newest few at a middling score
        lets recency and relevance decide, rather than forcing them in. A chunk
        must name one of the question's topic words; a question with none
        ("any news today?") takes them all.
        """
        topic = [w for w in re.findall(r"[a-z][a-z0-9'-]{2,}", query_lower)
                 if w not in _NEWS_FILLER]
        topic_re = re.compile(r"\b(?:" + "|".join(map(re.escape, topic)) + r")\b", re.I) if topic else None
        from llama_index.core.schema import NodeWithScore
        index = self.indices.get('knowledge')
        if index is None:
            return []
        dated = []
        for path, entry in self.indexed_files.items():
            if '/news/' in path.replace('\\', '/') and entry.get('nodes'):
                ts = self._dated_filename_ts(path)
                if ts:
                    dated.append((ts, path))
        dated.sort(reverse=True)

        scores = sorted(float(getattr(n, 'score', 0) or 0) for n in pool)
        base = scores[len(scores) // 2] if scores else 0.5
        held = {getattr(getattr(n, 'node', n), 'node_id', None) for n in pool}
        out = []
        for _, path in dated[:n_files]:
            for node_id in self.indexed_files[path]['nodes']:
                if node_id in held:
                    continue
                node = index.docstore.get_node(node_id, raise_error=False)
                if node is not None and (topic_re is None or topic_re.search(node.text or "")):
                    node.metadata['_retrieval_method'] = 'recent'
                    out.append(NodeWithScore(node=node, score=base))
        return out

    @staticmethod
    def _is_short_question(query_lower: str) -> bool:
        """A short turn that asks about something, rather than small talk.

        Four words or fewer used to mean casual, and casual searches only
        profiles and logs — so "who wrote Neuromancer?" never reached the book
        it names. A question with a topic word (five letters or more, not
        chatter) is searched like any other.
        """
        query_lower = re.sub(r"\S+://\S+", " ", query_lower)
        asks = "?" in query_lower or bool(_QUESTION_OPENER.match(query_lower))
        return asks and any(len(w) >= 5 and w not in _CHATTER
                            for w in re.findall(r"[a-z]+", query_lower))

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
            own_lower = self._own_words(query)
            routing = self._route_retrieval_strategy(category, query_lower, intent, own_lower)
            if include_news:
                # A news turn is not small talk, however short: "any news
                # today?" routed as casual searched profiles and logs only.
                routing["is_news_query"] = True
                routing["is_casual"] = False
                routing["names_period"] = bool(_NAMED_PERIOD.search(query_lower))

            if routing["strategy"] == "SUMMARIZATION":
                results = self._get_summarization_nodes(own_lower)
                if results:
                    self._last_retrieval_results = results
                    self._last_retrieval_confidence = 1.0
                    self._last_retrieval_node_count = len(results)
                    _trace_whole_document(query, results, self._get_channel_key())
                    return results
            
            # Manifest title fast path: match query words against indexed
            # filenames directly. It bypasses scoring, so it is deliberately hard
            # to enter — skipped for casual, social, greeting, dream and recap
            # queries, and requiring a distinctive word (>= 6 chars) in the
            # overlap plus 30% filename coverage. The stopword lists keep common
            # words ("what", "why", "work", "does") from matching titles.
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
                ) or
                "```" in query_lower or
                "traceback" in query_lower or
                "error:" in query_lower or
                "calling ollama" in query_lower or
                "action:" in query_lower or
                "log_info" in query_lower
            )
            _skip_fast_path = _skip_fast_path or not self._is_document_request(own_lower)
            _query_words = set(re.findall(r'\w+', own_lower)) - _FAST_PATH_QUERY_STOPS
            if len(_query_words) >= 2 and not _skip_fast_path:
                _best_path = None
                _best_score = 0
                _best_overlap = set()
                for _mpath in list(self.indexed_files):   # same concurrent-mutation risk
                    _fname = os.path.splitext(os.path.basename(_mpath))[0].lower()
                    # Strip date prefix from filename before tokenizing so dates don't dilute score
                    _fname_clean = re.sub(r'^\d{4}[-_]\d{2}[-_]\d{2}[-_]', '', _fname)
                    _fname_words = {w for w in re.findall(r'\w+', _fname_clean) if not w.isdigit()} - _FAST_PATH_FNAME_STOPS
                    if not _fname_words:
                        _fname_words = {w for w in re.findall(r'\w+', _fname) if not w.isdigit()} - _FAST_PATH_FNAME_STOPS
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
                        os.path.splitext(os.path.basename(_best_path))[0].lower(),
                        target_path=_best_path,
                    )
                    if _fname_results:
                        self._last_retrieval_results = _fname_results
                        self._last_retrieval_confidence = 1.0
                        self._last_retrieval_node_count = len(_fname_results)
                        log_success(f"Manifest title fast path resolved {len(_fname_results)} nodes")
                        _trace_whole_document(query, _fname_results, self._get_channel_key())
                        return _fname_results

            # Filename-reference fast path — runs regardless of routing strategy, but skipped on raw logs/code.
            # Catches: "check the file called X", "the file named X", "look at X.md",
            # "kaia check X", explicit filename pastes with dashes/underscores.
            if not _skip_fast_path:
                for _pat in self._FILENAME_REF_PATTERNS:
                    _match = _pat.search(own_lower)
                    if _match:
                        _hint = _match.group(1).strip()
                        if len(_hint) >= 6:  # Ignore short accidental matches
                            log_debug(f"Filename-reference fast path triggered: '{_hint}'")
                            _fname_results = self._get_summarization_nodes(_hint)
                            if _fname_results:
                                self._last_retrieval_results = _fname_results
                                self._last_retrieval_confidence = 1.0
                                self._last_retrieval_node_count = len(_fname_results)
                                log_success(f"Filename fast path resolved {len(_fname_results)} nodes for '{_hint}'")
                                _trace_whole_document(query, _fname_results, self._get_channel_key())
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
            if include_news and 'knowledge' not in target_itypes:
                target_itypes = target_itypes + ['knowledge']
            # A news turn wants the *latest* briefs, but candidates are chosen
            # by similarity alone and recency only re-ranks what came back. A
            # pool of eight held June's briefs and none from this week.
            counts = {itype: (max(retrieve_count, NEWS_CANDIDATE_POOL)
                              if include_news and itype == 'knowledge' else retrieve_count)
                      for itype in target_itypes}
            tasks = [self._execute_hybrid_retrieval(itype, enriched_query, counts[itype]) for itype in target_itypes if itype in self.indices]
            all_results_raw = await asyncio.gather(*tasks, return_exceptions=True)
            all_node_results = []
            for i, sublist in enumerate(all_results_raw):
                if isinstance(sublist, Exception):
                    log_warning(f"Retrieval task {i} failed: {sublist}")
                    continue
                all_node_results.extend(sublist)
            if include_news and _FRESH_NEWS.search(query_lower):
                all_node_results.extend(self._latest_news_candidates(all_node_results, query_lower))
            # Cache raw results BEFORE filtering for !explain
            self._last_raw_results = all_node_results
            
            # Scoring & Filtering
            results = self._score_and_filter_nodes(all_node_results, query_lower, relevant_ids, routing, top_k, include_news, strict_identity)
            if results: log_success(f"RAG retrieved {len(results)} nodes")

            # Cache results for !flag and !explain commands
            self._last_retrieval_results = results

            # And append to the trace `!explain N` reads. The cache above holds
            # one retrieval per channel, so without this the turn someone wants
            # to investigate is overwritten by the next thing anyone says.
            try:
                from utils.infrastructure.monitoring.retrieval_trace import record
                record(query, self._last_retrieval_confidence, results,
                       channel=self._get_channel_key())
            except Exception:
                pass

            return results

            
        except Exception as e:
            log_error(f"Error during retrieval: {e}")
            log_debug(traceback.format_exc())
            return []

    @staticmethod
    def _node_timestamp(node) -> float:
        """When a log chunk's conversation happened, as best the metadata says.

        The chunk's own `timestamp` (its first turn) first, then the date in the
        filename, and only then when the file was last written. A file's
        modification time says when it was last touched: a monthly archive the
        weekly rollup just rewrote would otherwise count every chunk in it as
        happening today.
        """
        meta = getattr(node, "metadata", None) or {}
        ts_val = meta.get("timestamp")
        if isinstance(ts_val, (int, float)) and ts_val > 0:
            return float(ts_val)
        if isinstance(ts_val, str) and ts_val:
            try:
                if "_" in ts_val and len(ts_val) == 15:
                    return datetime.strptime(ts_val, "%Y%m%d_%H%M%S").timestamp()
                return datetime.fromisoformat(ts_val).timestamp()
            except (ValueError, TypeError):
                pass

        base = os.path.basename(meta.get("file_path", "") or "")
        m = re.search(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)", base)
        if m:
            try:
                # The end of that day, not its midnight.
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                23, 59, 59).timestamp()
            except ValueError:
                pass
        # A monthly rollup (`interactions_202608_archive.md`): the end of that month.
        m = re.search(r"(?<!\d)(20\d{2})(\d{2})(?!\d)", base)
        if m and 1 <= int(m.group(2)) <= 12:
            year, month = int(m.group(1)), int(m.group(2))
            nxt = datetime(year + (month == 12), month % 12 + 1, 1)
            return nxt.timestamp() - 1

        for field in ("last_modified_at", "mtime"):
            val = meta.get(field)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
        path = meta.get("file_path", "")
        if path and os.path.exists(path):
            return os.path.getmtime(path)
        return 0.0

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
                ts = self._node_timestamp(node)
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
                ts = self._node_timestamp(node)
                if ts > cutoff:
                    recent_nodes.append(node)
            
            if not recent_nodes:
                return []

            # Simple keyword matching for "search" among recent nodes
            scored_events = []
            
            from utils.core.kaia_rag_retriever import SimpleBM25Retriever
            stopwords = set(SimpleBM25Retriever.CONVERSATIONAL_STOPWORDS)
            query_words = [w for w in query.lower().split() if w not in stopwords and len(w) > 2]
            
            from utils.core.rag_utils import get_node_text, speaker_from_log_path
            
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
                        except (ValueError, TypeError): ts = 0
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
                            # Carry the speaker through. Rebuilding metadata from
                            # scratch dropped the `user_name` the indexer set, and
                            # that field is what context_optimizer turns into the
                            # "CONVERSATION HISTORY: <who>" attribution line — so
                            # every node a recap injected arrived anonymous.
                            "user_name": (meta.get("user_name")
                                          or speaker_from_log_path(meta.get("file_path", ""))),
                            "retrieval_method": "fallback"
                        },
                        "label": ("Recent Log: "
                                  + (speaker_from_log_path(meta.get("file_path", "")) or "unknown")
                                  + f" ({os.path.basename(meta.get('file_path') or 'unknown')})"),
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
                        "user_name": (meta.get("user_name")
                                      or speaker_from_log_path(meta.get("file_path", ""))),
                        "retrieval_method": "search"
                    },
                    "label": ("Recent Log: "
                              + (speaker_from_log_path(meta.get("file_path", "")) or "unknown")
                              + f" ({os.path.basename(meta.get('file_path') or 'unknown')})"),
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


