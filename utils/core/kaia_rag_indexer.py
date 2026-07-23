"""
RAG Indexer Mixin — Document Ingestion & Processing
=====================================================

Extracted from kaia_rag.py (Phase 28 / CQ-01).

Contains all document-related operations for KaiaRAG:
- NLTK pre-loading
- Node parsing and chunking
- File scanning and change detection
- PDF/DOCX conversion
- Document indexing (regular + log tail)
- Corrupt file handling
- Index persistence after updates
- Knowledge base refresh orchestration
"""

import os
import re
import asyncio
import time
import json
import copy
import threading
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Set

import pypdf
import docx2txt

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage, Document
from llama_index.core.node_parser import SentenceSplitter, CodeSplitter

from utils.infrastructure.logging.kaia_logger import (
    log_success, log_info, log_warning, log_error, log_critical, log_action, log_debug
)
from utils.infrastructure.system.shutdown_fixed import shutdown_manager


class ConversationTurnSplitter:
    """
    Splits structured conversation logs by turn groups.
    Avoids NLTK entirely — uses regex on [TIMESTAMP] Speaker: markers.
    Each chunk is N complete turns, preserving timestamps for accurate recall.
    """
    _TURN_PATTERN = re.compile(
        r'(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] (?:User|Kaia|Ekco|social|\w+): )',
        re.IGNORECASE
    )

    def __init__(self, turns_per_chunk: int = 6, overlap_turns: int = 1, max_chars: int = 4000):
        self.turns_per_chunk = turns_per_chunk
        self.overlap_turns = overlap_turns
        self.max_chars = max_chars

    def get_nodes_from_documents(self, documents: list) -> list:
        from llama_index.core.schema import TextNode
        nodes = []
        for doc in documents:
            text = doc.text
            metadata = doc.metadata.copy()

            parts = self._TURN_PATTERN.split(text)
            turns = []

            if len(parts) == 1:
                # No turn markers found
                turns = [text]
            else:
                if len(parts[0].strip()) > 50:
                    turns.append(parts[0].strip())
                    
                i = 1
                while i < len(parts) - 1:
                    header = parts[i]
                    body = parts[i + 1] if i + 1 < len(parts) else ""
                    turns.append(header + body.rstrip())
                    i += 2

            if not turns:
                continue

            def split_oversized_text(long_text, chunk_idx_base):
                sub_nodes = []
                overlap = 200
                chunk_size = max(500, self.max_chars)
                
                last_ts = metadata.get('timestamp')
                ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', long_text[:500])
                if ts_match:
                    try:
                        last_ts = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                    except Exception:
                        pass
                
                step_size = chunk_size - overlap
                count = 0
                for start_char in range(0, len(long_text), step_size):
                    sub_text = long_text[start_char:start_char + chunk_size]
                    sub_meta = metadata.copy()
                    sub_meta['chunk_index'] = chunk_idx_base + (count * 0.001)
                    if last_ts:
                        sub_meta['timestamp'] = last_ts
                    
                    n = TextNode(text=sub_text, metadata=sub_meta)
                    sub_nodes.append(n)
                    count += 1
                return sub_nodes

            step = max(1, self.turns_per_chunk - self.overlap_turns)
            for chunk_idx, start in enumerate(range(0, len(turns), step)):
                chunk_turns = turns[start:start + self.turns_per_chunk]
                chunk_text = "\n".join(chunk_turns)
                if not chunk_text.strip():
                    continue

                if len(chunk_text) > self.max_chars:
                    nodes.extend(split_oversized_text(chunk_text, chunk_idx))
                    continue

                chunk_meta = metadata.copy()
                chunk_meta['chunk_index'] = chunk_idx
                ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', chunk_text)
                if ts_match:
                    try:
                        chunk_meta['timestamp'] = datetime.strptime(
                            ts_match.group(1), "%Y-%m-%d %H:%M:%S"
                        ).timestamp()
                    except Exception:
                        pass
                elif 'timestamp' in metadata:
                    chunk_meta['timestamp'] = metadata['timestamp']
                    
                node = TextNode(text=chunk_text, metadata=chunk_meta)
                nodes.append(node)

        return nodes


class RAGIndexerMixin:
    """Mixin class providing document ingestion and indexing methods for KaiaRAG."""
    
    import re as _re
    _LOG_TS_PATTERN = _re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]')

    @staticmethod
    def _extract_log_conversation_ts(content: str, fallback: float) -> float:
        """Extract the first inline [YYYY-MM-DD HH:MM:SS] timestamp from log content.
        Falls back to file mtime if none found (non-timestamped legacy content)."""
        m = RAGIndexerMixin._LOG_TS_PATTERN.search(content)
        if m:
            try:
                from datetime import datetime
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                log_debug(f"Extracted conversation ts: {m.group(1)} → {ts}")
                return ts
            except Exception:
                pass
        return fallback

    def _preload_nltk(self):
        """Worker thread: Pre-load NLTK data without redundant network calls."""
        try:
            import nltk
            from nltk.corpus import stopwords, words as nltk_words
            # Only download if not already present — avoids network checks at startup
            for resource, path in [
                ('stopwords', 'corpora/stopwords'),
                ('punkt', 'tokenizers/punkt'),
                ('punkt_tab', 'tokenizers/punkt_tab'),
                ('words', 'corpora/words'),          # Prevents lazy-load thread bug in SentenceSplitter
            ]:
                try:
                    nltk.data.find(path)
                except LookupError:
                    nltk.download(resource, quiet=True)
            stopwords.ensure_loaded()
            nltk_words.ensure_loaded()               # Force eager load — NLTK lazy loader is not thread-safe
        except Exception as e:
            log_warning(f"NLTK pre-load failed: {e}")

    async def get_recent_files_async(self, limit: int = 5) -> List[Dict[str, str]]:
        """Async wrapper for get_recent_files utilizing cache."""
        now = time.time()
        # Refresh cache if stale (60s)
        if now - self._last_recent_scan > 60:
            await asyncio.to_thread(self.get_recent_files, limit)
        return self._recent_files_cache[:limit]

    def get_recent_files(self, limit: int = 5) -> List[Dict[str, str]]:
        """Get recently modified files, using manifest to avoid full disk scan."""
        # 1. Sort manifest entries by mtime/boost
        from utils.infrastructure.system.yaml_config import config
        daily_news_boost = getattr(config, 'rag_boost_daily_news', 172800)
        dream_boost = getattr(config, 'rag_boost_dreams', 64800)
        
        weighted_files = []
        for path, meta in self.indexed_files.items():
            mtime = meta.get("mtime", 0)
            weight = mtime
            
            # Application-specific boosting
            if "daily" in path and "news_brief" in path:
                weight += daily_news_boost
            elif "kaia_dreams" in path:
                weight += dream_boost
                
            weighted_files.append((path, mtime, weight))
            
        # 2. Sort by weight descending
        weighted_files.sort(key=lambda x: x[2], reverse=True)
        
        # 3. Build snippets for top entries
        recent_with_snippets = []
        for path, mtime, weight in weighted_files[:limit * 2]: # Get extra to account for filters
            filename = os.path.basename(path)
            snippet = ""
            context_prefix = ""
            
            # Guess context from path
            if "user_logs" in path:
                parts = path.split(os.sep)
                try:
                    folder = parts[parts.index("user_logs") + 1]
                    username = folder.split("_")[0] if "_" in folder else folder
                    context_prefix = f"Log ({username}): "
                except Exception: pass
            elif "news" in path:
                context_prefix = "News: "
            
            try:
                if path.endswith(('.txt', '.md')):
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(500)
                        if "User Log" in content or "Interaction" in content:
                           snippet = content[-300:].strip().replace("\n", " ") + "..."
                        else:
                           snippet = content[:300].strip().replace("\n", " ") + "..."
                elif path.endswith('.pdf'): snippet = "[PDF Content Indexed]"
                else: snippet = "[Document Indexed]"
            except Exception: continue
                
            recent_with_snippets.append({
                "filename": context_prefix + filename,
                "snippet": snippet
            })
            
        self._recent_files_cache = recent_with_snippets
        self._last_recent_scan = time.time()
        return self._recent_files_cache[:limit]

    async def get_stats_async(self) -> Dict[str, Any]:
        """Async wrapper for get_stats."""
        return await asyncio.to_thread(self.get_stats)

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG statistics for dashboard"""
        total_docs = 0
        for index in self.indices.values():
            total_docs += len(index.docstore.docs)
            
        # Calculate total size of persist_dir
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(self.persist_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        
        size_str = f"{total_size / 1024 / 1024:.1f} MB"
        
        return {
            "total_documents": total_docs,
            "index_size": size_str,
            "last_refresh": datetime.now()
        }

    def _get_bm25_cache_path(self, itype: str) -> str:
        """Get the file path for the pickled BM25 retriever of a specific index type."""
        return os.path.join(self.persist_dir, itype, "bm25_cache.pkl")

    def _save_bm25_cache(self, itype: str, skip_lock: bool = False):
        """Persists the SimpleBM25Retriever to disk using pickle."""
        import pickle
        
        def _do_save():
            retriever = self.bm25_cache.get(itype)
            if not retriever or getattr(retriever, 'bm25', None) is None:
                return # Nothing to save
        
            cache_path = self._get_bm25_cache_path(itype)
            itype_dir = os.path.dirname(cache_path)
            
            try:
                if not os.path.exists(itype_dir):
                    os.makedirs(itype_dir)
                temp_path = f"{cache_path}.tmp"
                
                # We don't want to pickle the lock object inside SimpleBM25Retriever
                # So we create a shallow copy and remove the lock before pickling
                retriever_copy = copy.copy(retriever)
                if hasattr(retriever_copy, '_lock'):
                    delattr(retriever_copy, '_lock')
                    
                with open(temp_path, 'wb') as f:
                    pickle.dump(retriever_copy, f, protocol=pickle.HIGHEST_PROTOCOL)
                    
                os.replace(temp_path, cache_path)
                log_debug(f"Saved BM25 cache for '{itype}' to disk.")
            except Exception as e:
                log_error(f"Failed to save BM25 cache for '{itype}': {e}")

        if skip_lock:
            _do_save()
        else:
            with self._data_lock:
                _do_save()

    def _load_bm25_cache(self, itype: str):
        """Loads the SimpleBM25Retriever from disk. Returns None if invalid or missing."""
        import pickle
        cache_path = self._get_bm25_cache_path(itype)
        
        if not os.path.exists(cache_path):
            return None
            
        # Verify if the cache is still valid based on mtime of the index directory
        # (If the index was updated, the vector store files will have newer mtimes)
        try:
            cache_mtime = os.path.getmtime(cache_path)
            
            # Check if any indexed file for this itype has changed since the cache was created
            with self._data_lock:
                for path, meta in self.indexed_files.items():
                    # Only invalidate if a file belonging to THIS index type changed
                    node_itype = meta.get("itype", "")
                    if node_itype and node_itype != itype:
                        continue
                    file_mtime = meta.get("mtime", 0)
                    if file_mtime > cache_mtime:
                         log_debug(f"BM25 cache for '{itype}' is stale (file updated).")
                         return None
            
            # Index manifest is older than cache, we can load it
            with open(cache_path, 'rb') as f:
                retriever = pickle.load(f)
                
                # Restore the lock that was removed during pickling
                retriever._lock = threading.Lock()
                log_debug(f"Loaded BM25 cache for '{itype}' from disk.")
                return retriever
        except Exception as e:
            log_error(f"Failed to load BM25 cache for '{itype}', falling back to rebuild: {e}")
            return None

    def _initialize_indices(self):
        """Initialize hierarchical indices from storage or create new ones."""
        with self._data_lock:
            index_types = ['persona', 'user_profiles', 'knowledge', 'logs', 'dreams']
            for itype in index_types:
                itype_dir = os.path.join(self.persist_dir, itype)
                try:
                    if os.path.exists(itype_dir) and os.listdir(itype_dir):
                        log_debug(f"Loading {itype} index...")
                        storage_context = StorageContext.from_defaults(persist_dir=itype_dir)
                        self.indices[itype] = load_index_from_storage(storage_context)
                    else:
                        log_debug(f"Initializing {itype} index...")
                        self.indices[itype] = VectorStoreIndex.from_documents([])
                        if not os.path.exists(itype_dir):
                            os.makedirs(itype_dir)
                        self.indices[itype].storage_context.persist(persist_dir=itype_dir)
                except Exception as e:
                    log_error(f"Error initializing {itype} index (corruption suspected): {e}")
                    # Auto-repair corrupted storage
                    try:
                        import shutil
                        if os.path.exists(itype_dir):
                            shutil.rmtree(itype_dir)
                        os.makedirs(itype_dir, exist_ok=True)
                    except Exception as rmtree_err:
                        log_error(f"Failed to clear corrupted directory {itype_dir}: {rmtree_err}")
                    
                    self.indices[itype] = VectorStoreIndex.from_documents([])
                    try:
                        self.indices[itype].storage_context.persist(persist_dir=itype_dir)
                    except Exception as persist_err:
                        log_error(f"Failed to persist fresh index for {itype}: {persist_err}")
                        
                    # Remove BM25 cache
                    bm25_cache_path = self._get_bm25_cache_path(itype)
                    if os.path.exists(bm25_cache_path):
                        try:
                            os.remove(bm25_cache_path)
                        except Exception:
                            pass
                    
                    # Remove files of this index type from manifest so they are re-scanned/re-indexed
                    if hasattr(self, 'indexed_files') and isinstance(self.indexed_files, dict):
                        paths_to_remove = []
                        for path, meta in self.indexed_files.items():
                            if meta.get("itype") == itype:
                                paths_to_remove.append(path)
                            elif itype == 'dreams' and 'kaia_dreams' in path:
                                paths_to_remove.append(path)
                            elif itype == 'logs' and 'user_logs' in path and 'user_profile.md' not in path:
                                paths_to_remove.append(path)
                            elif itype == 'user_profiles' and 'user_profile.md' in path:
                                paths_to_remove.append(path)
                            elif itype == 'persona' and 'kaia_persona.md' in path:
                                paths_to_remove.append(path)
                        
                        if paths_to_remove:
                            log_info(f"Removing {len(paths_to_remove)} entries from manifest to trigger re-indexing of {itype}.")
                            for p in paths_to_remove:
                                self.indexed_files.pop(p, None)
                            self._save_indexed_files()
            
            # Populate indexed files from all indices
            self._populate_indexed_files()
            log_debug("All hierarchical indices initialized.")

    def _get_node_parser_for_doc(self, itype: str, file_path: str):
        """Dynamic chunking based on content type and index target"""
        if itype == 'logs' or itype == 'conversations':
            # Use turn-based splitter for structured logs — avoids NLTK entirely
            # and preserves per-chunk timestamps for accurate time-window recall
            return ConversationTurnSplitter(turns_per_chunk=6, overlap_turns=1)
        elif "news_brief" in file_path or "news_summary" in file_path:
            # News briefs: smaller chunks, split by headings
            return SentenceSplitter(chunk_size=1000, chunk_overlap=200, paragraph_separator="\n## ")
        elif file_path.endswith(('.py', '.js', '.html', '.css', '.go', '.rs')):
            # Code files: preserve structure
            lang = file_path.split('.')[-1]
            if lang == 'py': lang = 'python'
            elif lang == 'js': lang = 'javascript'
            try:
                return CodeSplitter(language=lang, chunk_lines=100, chunk_overlap=10)
            except Exception as e:
                log_debug(f"CodeSplitter failed for {lang}, falling back to SentenceSplitter: {e}")
                return SentenceSplitter(chunk_size=1024, chunk_overlap=200)
        elif itype == 'knowledge':
            # SentenceSplitter for better reliability and lower RAM usage.
            # SemanticSplitter was causing 30GB+ RAM spikes on large documents.
            return SentenceSplitter(chunk_size=1024, chunk_overlap=200)
        else:
            return SentenceSplitter(chunk_size=1024, chunk_overlap=200)

    def _pre_chunk_document(self, doc: Document, chunk_size: int = 4000) -> List[Document]:
        """Break a giant document into smaller documents before node parsing."""
        if len(doc.text) <= chunk_size:
            return [doc]
            
        log_action(f"Pre-chunking large document ({len(doc.text)} chars)...")
        chunks = []
        # Simple character-based split with overlap for efficiency
        overlap = 200
        for i in range(0, len(doc.text), chunk_size - overlap):
            chunk_text = doc.text[i:i + chunk_size]
            new_doc = Document(
                text=chunk_text,
                metadata=doc.metadata.copy()
            )
            # Add chunk info to metadata
            new_doc.metadata['chunk_index'] = len(chunks)
            chunks.append(new_doc)
        return chunks



    def _apply_priority_metadata(self, doc: Document, itype: str, file_path: str):
        """Apply neutral priority and source type metadata"""
        # Neutralize all priorities to let search relevance decide
        doc.metadata["priority"] = 0.5
        
        if itype == 'persona' or "kaia_persona" in file_path:
            doc.metadata["source_type"] = "persona"
            doc.metadata["user_id"] = "KAIA_SYSTEM"
        elif itype == 'logs' or "user_logs" in file_path:
            doc.metadata["source_type"] = "user_logs"
        elif itype == 'user_profiles' or "user_profile" in file_path:
            doc.metadata["source_type"] = "user_profile"
        elif "news_brief" in file_path or "news_summary" in file_path:
            doc.metadata["source_type"] = "news"
        elif itype == 'dreams' or "kaia_dreams" in file_path:
            # Check for kaia_reflection frontmatter or path indicator
            if hasattr(doc, 'text') and 'source_type: kaia_reflection' in doc.text[:200]:
                doc.metadata["source_type"] = "kaia_reflection"
            else:
                doc.metadata["source_type"] = "dream"
        elif "snapshots" in file_path:
            doc.metadata["source_type"] = "snapshot"
        else:
            doc.metadata["source_type"] = "general_knowledge"
            
        # Extract user metadata from path or content
        if "user_logs" in file_path:
            parts = file_path.split(os.sep)
            try:
                ul_idx = parts.index("user_logs")
                user_folder = parts[ul_idx + 1]
                if "_" in user_folder:
                    u_name, u_id = user_folder.rsplit("_", 1)
                    doc.metadata['user_id'] = u_id
                    doc.metadata['user_name'] = u_name
            except Exception: pass
        elif doc.metadata.get("source_type") == "dream":
        # Check if this dream is derived from user interaction logs
            if "interactions" in file_path or "interactions" in doc.text[:200]:
                # Extract from content header: Source: user_logs/Name_ID/interactions_YYYYMMDD.txt
                import re
                # Look for the last set of digits in the user_logs path fragment
                # Example: user_logs/Ekco_177011971818782721/interactions...
                match = re.search(r'user_logs/[^/]+?_(\d{15,20})', doc.text[:500])
                if match:
                    doc.metadata['user_id'] = match.group(1)
                    # Also try to get the name
                    name_match = re.search(r'user_logs/([^/]+?)_\d{15,20}', doc.text[:500])
                    if name_match:
                        doc.metadata['user_name'] = name_match.group(1).replace("_", " ")

        # Compute Quality Score (P54-18)
        quality = 0.5  # default baseline
        try:
            score = 0.0
            # 1. Source density (up to 0.4 points)
            text_len = len(doc.text)
            score += min(0.4, (text_len / 1500.0) * 0.4)
            
            # Structure cues (up to 0.1 points)
            if any(marker in doc.text for marker in ["###", "\n- ", "\n* ", "\n> ", "```"]):
                score += 0.1
                
            # 2. Metadata completeness (up to 0.3 points)
            if doc.metadata.get("user_id") and doc.metadata.get("user_name"):
                score += 0.2
            if doc.metadata.get("keywords") or "summary:" in doc.text[:200].lower():
                score += 0.1
                
            # 3. Detailed Kaia response presence (up to 0.2 points)
            kaia_matches = re.findall(r'\]\s*Kaia:\s*(.+)', doc.text)
            if kaia_matches:
                # Check if at least one response is non-trivial (e.g. >15 chars)
                if any(len(m.strip()) > 15 for m in kaia_matches):
                    score += 0.2
            
            # Clamp quality between 0.1 and 1.0
            quality = round(max(0.1, min(1.0, score)), 2)
        except Exception:
            pass
        doc.metadata["quality_score"] = quality



    def _populate_indexed_files(self):
        """Populate the set of indexed files from all hierarchical indices without overwriting loaded state."""
        # Caller (_initialize_indices) already holds self._lock
        # Rebuild _file_to_nodes mapping from indices
        new_file_to_nodes = {}
        for itype, index in self.indices.items():
            for node_id, node in index.docstore.docs.items():
                file_path = node.metadata.get('file_path')
                if file_path:
                    abs_path = os.path.abspath(file_path)
                    if abs_path not in new_file_to_nodes:
                        new_file_to_nodes[abs_path] = []
                    new_file_to_nodes[abs_path].append(node_id)
        
        self._file_to_nodes = new_file_to_nodes
        
        # Update manifest based on current disk + index state
        # Build a quick reverse-map: node_id -> itype, so we can inject itype into each entry.
        node_id_to_itype: dict = {}
        for itype, index in self.indices.items():
            for node_id in index.docstore.docs:
                node_id_to_itype[node_id] = itype

        count_added = 0
        for abs_path, node_ids in self._file_to_nodes.items():
            # Resolve itype from any of this file's known node IDs
            resolved_itype = ""
            for nid in node_ids:
                resolved_itype = node_id_to_itype.get(nid, "")
                if resolved_itype:
                    break

            if abs_path not in self.indexed_files:
                if os.path.exists(abs_path):
                    mtime = os.path.getmtime(abs_path)
                    size = os.path.getsize(abs_path)
                    self.indexed_files[abs_path] = {
                        "mtime": mtime,
                        "size": size,
                        "nodes": node_ids,
                        "itype": resolved_itype  # Fix #4: inject itype so BM25 cache invalidation works on boot
                    }
                    count_added += 1
            else:
                # Sync nodes in manifest, and backfill itype if it was missing from a legacy entry
                self.indexed_files[abs_path]["nodes"] = node_ids
                if not self.indexed_files[abs_path].get("itype") and resolved_itype:
                    self.indexed_files[abs_path]["itype"] = resolved_itype

        log_success(f"RAG State: {len(self.indexed_files)} files in manifest ({count_added} newly discovered).")
        self._save_indexed_files()

    def _prune_deleted_files(self) -> Set[str]:
        """Detect and remove files from indices that no longer exist on disk using manifest."""
        updated_itypes = set()
        deleted_files = [
            p for p in list(self.indexed_files.keys()) 
            if not os.path.exists(p) or os.path.basename(p) == "kaia_persona.md" or "forum_posts" in p.replace('\\', '/')
        ]
        if not deleted_files:
            return updated_itypes
            
        log_action(f"Detected {len(deleted_files)} deleted files. Pruning index O(k)...")
        to_prune = {} # itype -> list of node_ids
        
        with self._data_lock:
            for file_path in deleted_files:
                node_ids = self.indexed_files[file_path].get("nodes", [])
                if not node_ids:
                    self.indexed_files.pop(file_path, None)
                    continue
                    
                for itype in self.indices:
                    if itype not in to_prune:
                        to_prune[itype] = []
                    to_prune[itype].extend(node_ids)
                
                self.indexed_files.pop(file_path, None)
                self._file_to_nodes.pop(file_path, None)
            
            # Deletion happens inside the same lock scope
            for itype, node_ids in to_prune.items():
                if not node_ids:
                    continue
                try:
                    self.indices[itype].delete_nodes(node_ids)
                    updated_itypes.add(itype)
                except Exception:
                    pass

        self._save_indexed_files()
        return updated_itypes

    def _save_indexed_files(self):
        """Persist the mapping of indexed files to disk."""
        try:
            if not os.path.exists(self.persist_dir):
                os.makedirs(self.persist_dir)
            tmp_path = self.state_file + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.indexed_files, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.state_file)
            log_debug(f"Saved {len(self.indexed_files)} entries to {self.state_file}")
        except Exception as e:
            log_error(f"Failed to save indexed files state: {e}")

    def _load_indexed_files(self):
        """Load the mapping of indexed files from disk and fall back to legacy if needed."""
        try:
            legacy_file = os.path.join(self.persist_dir, "indexed_files.json")
            
            # 1. Try to load primary manifest
            manifest_data = {}
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    manifest_data = json.load(f)
            
            # 2. If primary is empty/missing, try legacy
            if not manifest_data and os.path.exists(legacy_file):
                with open(legacy_file, 'r', encoding='utf-8') as f:
                    legacy_data = json.load(f)
                
                # Check if it's the NEW format (dict of dicts) or OLD format (dict of mtimes)
                first_val = next(iter(legacy_data.values())) if legacy_data else None
                if isinstance(first_val, dict):
                    manifest_data = legacy_data
                    log_info(f"Loaded {len(manifest_data)} entries from indexed_files.json")
                else:
                    for path, mtime in legacy_data.items():
                        manifest_data[path] = {"mtime": mtime, "size": 0, "nodes": []}
                    log_info(f"Migrated {len(manifest_data)} files from old legacy format.")
            
            self.indexed_files = manifest_data
            if self.indexed_files:
                log_success(f"Loaded {len(self.indexed_files)} manifest entries.")
            else:
                log_info("No existing RAG manifest found; will perform initial population.")
                
        except Exception as e:
            log_error(f"Failed to load indexed files state: {e}")
            self.indexed_files = {}

    def _find_changed_files(self) -> List[Tuple[str, bool, bool, str]]:
        """Scan directory to find new or modified files."""
        new_file_paths = []
        supported_exts = [".pdf", ".txt", ".md", ".docx"]
        
        for root, _, files in os.walk(self.knowledge_base_dir):
            if "corrupt_files" in root or "forum_posts" in root.replace('\\', '/'): continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, file)
                    norm_path = os.path.abspath(full_path)
                    mtime = os.path.getmtime(norm_path)
                    
                    itype = 'knowledge'
                    if file == "kaia_persona.md":
                        itype = 'persona'
                    elif "user_logs" in full_path:
                        itype = 'user_profiles' if "user_profile.md" in file else 'logs'
                    elif "kaia_dreams" in full_path:
                        itype = 'dreams'
                    
                    entry = self.indexed_files.get(norm_path)
                    is_new = entry is None
                    is_modified = not is_new and (
                        mtime > entry.get("mtime", 0) or 
                        os.path.getsize(norm_path) != entry.get("size", 0)
                    )
                    
                    if (is_new or is_modified) and "user_memories.txt" not in file:
                        new_file_paths.append((full_path, is_modified, itype == 'logs', itype))

        # Check persona file
        # Check persona file - EXCLUDED per Bug 1
        # persona_file = "knowledge_base/kaia_persona.md"
        # if os.path.exists(persona_file):
        #     norm_path = os.path.abspath(persona_file)
        #     mtime = os.path.getmtime(norm_path)
        #     entry = self.indexed_files.get(norm_path)
        #     if entry is None or mtime > entry.get("mtime", 0):
        #         new_file_paths.append((persona_file, entry is not None, False, 'persona'))
        
        return new_file_paths

    def _index_single_file(self, file_path: str, is_modified: bool, is_log: bool, itype: str, corrupt_dir: str) -> bool:
        """Process a single file: load, parse, and insert into the target index."""
        target_index = self.indices[itype]
        abs_path = os.path.abspath(file_path)
        
        if is_modified and not is_log:
            log_action(f"Detected update in {itype} file. Re-indexing O(k): {file_path}")
            entry = self.indexed_files.get(abs_path)
            nodes_to_delete = entry.get("nodes", []) if entry else []
            
            if nodes_to_delete:
                log_success(f"  Removing {len(nodes_to_delete)} old nodes to prepare for update.")
                with self._data_lock: # Lock for modifying indices
                    target_index.delete_nodes(nodes_to_delete)
                    # Clear from manifest to avoid stale references if indexing fails midway
                    if entry: entry["nodes"] = []

        try:
            if is_log:
                return self._index_log_tail(file_path, abs_path, itype)
            else:
                return self._index_regular_file(file_path, abs_path, itype)
        except Exception as e:
            # NLTK lazy-corpus thread bug — not a corrupt file.
            # Occurs when SentenceSplitter hits a corpus that wasn't pre-loaded.
            if 'WordListCorpusReader' in str(e) or 'LazyCorpusLoader' in str(e):
                log_warning(f"NLTK lazy-load error indexing {file_path} — skipping this cycle (not corrupt): {e}")
                return False   # Skip, don't quarantine, will retry next refresh

            # Bug 2 Fix: Handle transient Ollama server-busy errors (400) or loading state
            if "status code: 400" in str(e) or "loading model" in str(e).lower():
                log_warning(f"Ollama server busy while indexing {file_path}. Skipping for this cycle: {e}")
                return False

            if 'skipping' in str(e).lower():
                return False
                
            log_error(f"Failed to load file {file_path}: {e}")
            return self._handle_corrupt_file(file_path, itype, corrupt_dir)

    def _index_log_tail(self, file_path: str, abs_path: str, itype: str) -> bool:
        """Perform tail-indexing for log files using O(k) offset detection."""
        target_index = self.indices[itype]
        last_offset = 0
        
        entry = self.indexed_files.get(abs_path)
        if entry and entry.get("nodes"):
            # Get only nodes belonging to this file from docstore
            for node_id in entry["nodes"]:
                node = target_index.docstore.get_node(node_id)
                if node:
                    last_offset = max(last_offset, node.metadata.get('file_offset', 0) + node.metadata.get('content_length', 0))
        
        if os.path.getsize(file_path) <= last_offset:
            # Update manifest even if no new content to avoid re-scanning
            mtime = os.path.getmtime(file_path)
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": os.path.getsize(file_path),
                "nodes": entry.get("nodes", []) if entry else [],
                "itype": itype
            }
            return False
            
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(last_offset)
            new_content = f.read()
            
        if not new_content.strip():
            return False
            
        # Parse nodes and apply metadata outside the lock
        mtime = os.path.getmtime(file_path)
        conversation_ts = self._extract_log_conversation_ts(new_content, mtime)
        from llama_index.core import Document as LlamaDocument
        doc = LlamaDocument(text=new_content, metadata={
            'file_path': abs_path,
            'file_offset': last_offset,
            'content_length': len(new_content),
            'last_modified_at': mtime,
            'timestamp': conversation_ts,
            'itype': itype
        })
        self._apply_priority_metadata(doc, itype, file_path)
        
        parser = self._get_node_parser_for_doc(itype, file_path)
        nodes = parser.get_nodes_from_documents([doc])
        
        with self._data_lock: # Lock only for the final insertion and manifest update
            target_index.insert_nodes(nodes)
            
            # Update manifest
            node_ids = [n.node_id for n in nodes]
            existing_nodes = entry.get("nodes", []) if entry else []
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": os.path.getsize(file_path),
                "nodes": list(set(existing_nodes + node_ids)),
                "itype": itype
            }
            self._file_to_nodes[abs_path] = self.indexed_files[abs_path]["nodes"]
        return True

    def _index_regular_file(self, file_path: str, abs_path: str, itype: str) -> bool:
        """Load and index a standard document file."""
        from llama_index.core import SimpleDirectoryReader, Document as LlamaDocument
        docs = None
        try:
            docs = SimpleDirectoryReader(input_files=[file_path]).load_data()
        except Exception:
            for enc in ['latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    with open(file_path, 'r', encoding=enc, errors='replace') as f:
                        docs = [LlamaDocument(text=f.read())]
                    break
                except Exception: continue
        
        if not docs:
            with open(file_path, 'rb') as f:
                docs = [LlamaDocument(text=f.read().decode('utf-8', errors='replace'))]
        
        mtime = os.path.getmtime(file_path)
        parser = self._get_node_parser_for_doc(itype, file_path)
        all_node_ids = []
        
        processed_nodes_batch = []
        for doc in docs:
            if itype == 'logs':
                conversation_ts = self._extract_log_conversation_ts(doc.text, mtime)
            else:
                conversation_ts = mtime
            doc.metadata.update({'last_modified_at': mtime, 'timestamp': conversation_ts, 'file_path': abs_path, 'itype': itype})
            self._apply_priority_metadata(doc, itype, file_path)
            if itype == 'persona': doc.metadata['user_id'] = "KAIA_SYSTEM"
            
            for sub_doc in self._pre_chunk_document(doc):
                # self._apply_priority_metadata(sub_doc, itype, file_path) # Duplicate call removed
                nodes = parser.get_nodes_from_documents([sub_doc])
                processed_nodes_batch.append(nodes)
        
        with self._data_lock: # Lock only for the final insertion and manifest update
            for nodes in processed_nodes_batch:
                self.indices[itype].insert_nodes(nodes)
                all_node_ids.extend([n.node_id for n in nodes])
            
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": os.path.getsize(file_path),
                "nodes": all_node_ids,
                "itype": itype
            }
            self._file_to_nodes[abs_path] = self.indexed_files[abs_path]["nodes"]
        if itype != 'logs':
            snippet = docs[0].text[:300].replace("\n", " ") + "..." if docs else ""
            from utils.infrastructure.system.bot_state import bot_state
            bot_state.add_ingestion(os.path.basename(file_path), snippet=snippet)
        return True

    def _handle_corrupt_file(self, file_path: str, itype: str, corrupt_dir: str) -> bool:
        """Attempt recovery or move file to corrupt directory."""
        # CRITICAL SAFEGUARD: Never move the core persona file
        if "kaia_persona.md" in os.path.basename(file_path):
            log_critical(f"CRITICAL: kaia_persona.md failed to load but will NOT be moved to corrupt_files. Please check formatting manually.")
            return False

        if file_path.lower().endswith((".pdf", ".docx")):
            md_path = self._convert_pdf_to_md(file_path) if file_path.lower().endswith(".pdf") else self._convert_docx_to_md(file_path)
            if md_path:
                try:
                    from llama_index.core import SimpleDirectoryReader
                    md_docs = SimpleDirectoryReader(input_files=[md_path]).load_data()
                    if md_docs:
                        mtime = os.path.getmtime(md_path)
                        parser = self._get_node_parser_for_doc(itype, md_path)
                        with self._data_lock: # Lock for modifying indices and manifest
                            for doc in md_docs:
                                doc.metadata.update({'last_modified_at': mtime, 'itype': itype})
                                self.indices[itype].insert_nodes(parser.get_nodes_from_documents([doc]))
                            # NOTE: nodes for the converted file live under the .md path entry;
                            # the original .pdf/.docx entry intentionally has nodes=[] — it acts
                            # as a "file seen" sentinel so _prune_deleted_files won't try to prune it.
                            self.indexed_files[os.path.abspath(md_path)] = {"mtime": mtime, "size": os.path.getsize(md_path), "nodes": [], "itype": itype}
                            self.indexed_files[os.path.abspath(file_path)] = {"mtime": os.path.getmtime(file_path), "size": 0, "nodes": [], "itype": itype}
                        return True
                except Exception: pass
        
        # Move to corrupt (DISABLED - Files should stay where they are)
        # dest = os.path.join(corrupt_dir, os.path.basename(file_path))
        # if os.path.exists(dest): dest = f"{dest}_{int(time.time())}"
        # import shutil
        # shutil.move(file_path, dest)
        log_critical(f"UNABLE TO INDEX CORRUPT FILE: {file_path}. Keeping in original location.")
        return False


    def _persist_updated_indices(self, updated_itypes: Set[str]):
        """Save indices to disk and invalidate/save BM25 cache."""
        self.persist_needed = True
        
        # 1. Invalidate BM25 caches (Quick internal state update)
        with self._data_lock:
            for itype in updated_itypes:
                if itype in self.bm25_cache:
                    log_info(f"Invalidating memory BM25 cache for '{itype}' to trigger re-save")
                    del self.bm25_cache[itype]

        # 2. Heavy Disk I/O (NO LOCK HELD)
        # We don't hold the global data lock during storage_context.persist()
        # because it performs slow filesystem writes. The index objects 
        # themselves are thread-safe for persistence.
        for itype in updated_itypes:
            try:
                persist_path = os.path.join(self.persist_dir, itype)
                self.indices[itype].storage_context.persist(persist_dir=persist_path)
                log_success(f"Index '{itype}' persisted.")
                
                # 3. Persist BM25 if already in memory (re-acquires lock internally)
                if itype in self.bm25_cache and self.bm25_cache[itype]:
                    self._save_bm25_cache(itype)
            except Exception as e: 
                log_error(f"Failed to persist {itype}: {e}")
                
        self._save_indexed_files()

    async def refresh_knowledge_base(self, max_concurrent_files: int = 2):
        """Refresh knowledge base with concurrent file processing and batch persistence."""
        if not self._index_lock.acquire(blocking=False):
            log_info("RAG refresh already in progress, marking as pending.")
            self._refresh_pending = True
            return

        try:
            self._indexing_in_progress = True
            self._refresh_pending = False
            
            if not os.path.exists(self.knowledge_base_dir):
                os.makedirs(self.knowledge_base_dir)
                return

            log_action(f"Refreshing knowledge base (Parallel, max={max_concurrent_files})...")
            
            # 0. Safety Guard: Ensure indices are initialized
            if not self.indices:
                log_info("Indices not initialized. Running initialization...")
                await asyncio.to_thread(self._initialize_indices)
                
            corrupt_dir = os.path.join(self.knowledge_base_dir, "corrupt_files")
            if not os.path.exists(corrupt_dir): os.makedirs(corrupt_dir)

            updated_itypes = await asyncio.to_thread(self._prune_deleted_files)
            new_file_paths = await asyncio.to_thread(self._find_changed_files)

            if not new_file_paths:
                log_debug("No new documents to index.")
            else:
                log_action(f"Found {len(new_file_paths)} new/modified documents. Processing concurrently...")
                
                # Semaphore to avoid overloading CPU/GPU
                semaphore = asyncio.Semaphore(max_concurrent_files)
                result_itypes = set()

                async def process_file(file_info):
                    # Abort if shutdown started mid-refresh
                    try:
                        if shutdown_manager.shutting_down:
                            return None
                    except Exception:
                        pass
                    file_path, is_modified, is_log, itype = file_info
                    async with semaphore:
                        try:
                            # Index file in a separate thread to avoid blocking event loop
                            if await asyncio.to_thread(self._index_single_file, file_path, is_modified, is_log, itype, corrupt_dir):
                                return itype
                        except Exception as e:
                            log_error(f"Error indexing {file_path}: {e}")
                        return None

                tasks = [process_file(finfo) for finfo in new_file_paths]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Track updated types
                for i, itype in enumerate(results):
                    if isinstance(itype, Exception):
                        log_error(f"Parallel indexing task {i} failed: {itype}")
                        continue
                    if itype:
                        result_itypes.add(itype)
                        updated_itypes.add(itype)

                if result_itypes:
                    log_success(f"Parallel indexing complete. Updated types: {', '.join(result_itypes)}")
                else:
                    log_info("All detected files were already up-to-date or failed.")

            if updated_itypes:
                # Batch persist all updated indices at the end
                await asyncio.to_thread(self._persist_updated_indices, updated_itypes)
                log_success(f"Batch persistence complete for: {', '.join(updated_itypes)}")
            elif new_file_paths:
                # Still save the manifest if we scanned files
                await asyncio.to_thread(self._save_indexed_files)
                
        except Exception as e:
            log_error(f"Error in parallel RAG refresh: {e}")
            traceback.print_exc()
        finally:
            self._indexing_in_progress = False
            self._index_lock.release()
            if self._refresh_pending:
                log_info("Triggering pending RAG refresh...")
                
                async def trigger_refresh():
                    await asyncio.sleep(2.0)
                    await self.refresh_knowledge_base(max_concurrent_files)
                    
                asyncio.create_task(trigger_refresh())

    def _convert_pdf_to_md(self, pdf_path: str) -> Optional[str]:
        """Convert a PDF file to a Markdown file by extracting text."""
        if not hasattr(self, '_pdf_breaker'):
            from utils.infrastructure.circuit_breaker import CircuitBreaker
            self._pdf_breaker = CircuitBreaker("pdf_conversion", failure_threshold=3, recovery_timeout=60)
        if not self._pdf_breaker.can_proceed():
            log_warning(f"Circuit breaker open for PDF conversion")
            return None
        
        try:
            # Strip .pdf extension before adding .md for cleaner filenames
            base_path = pdf_path[:-4] if pdf_path.lower().endswith('.pdf') else pdf_path
            md_path = base_path + ".md"
            log_action(f"Extracting text from PDF...")
            log_info(pdf_path)
            
            reader = pypdf.PdfReader(pdf_path)
            basename = os.path.basename(pdf_path)
            title = basename[:-4] if basename.lower().endswith('.pdf') else basename
            
            extracted_pages = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    extracted_pages.append(f"## Page {i+1}\n\n{page_text}")
            
            if extracted_pages:
                text = f"# {title}\n\n" + "\n\n".join(extracted_pages)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(text)
                log_success(f"Successfully converted to Markdown")
                log_info(md_path)
                self._pdf_breaker.record_success()
                return md_path
            else:
                log_warning(f"No text extracted from PDF")
                self._pdf_breaker.record_success()
                return None
        except Exception as e:
            self._pdf_breaker.record_failure()
            log_error(f"Error converting PDF to MD: {e}")
            return None

    def _convert_docx_to_md(self, docx_path: str) -> Optional[str]:
        """Convert a DOCX file to a Markdown file by extracting text."""
        if not hasattr(self, '_docx_breaker'):
            from utils.infrastructure.circuit_breaker import CircuitBreaker
            self._docx_breaker = CircuitBreaker("docx_convert", failure_threshold=3, recovery_timeout=60)
        if not self._docx_breaker.can_proceed():
            log_warning(f"Circuit breaker open for DOCX conversion")
            return None
            
        try:
            # Strip .docx extension before adding .md
            base_path = docx_path[:-5] if docx_path.lower().endswith('.docx') else docx_path
            md_path = base_path + ".md"
            log_action(f"Extracting text from DOCX...")
            log_info(docx_path)
            
            text = docx2txt.process(docx_path)
            
            if text and text.strip():
                basename = os.path.basename(docx_path)
                title = basename[:-5] if basename.lower().endswith('.docx') else basename
                
                md_content = f"# {title}\n\n{text}"
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                log_success(f"Successfully converted to Markdown")
                log_info(md_path)
                self._docx_breaker.record_success()
                return md_path
            else:
                log_warning(f"No text extracted from DOCX")
                self._docx_breaker.record_success()
                return None
        except Exception as e:
            self._docx_breaker.record_failure()
            log_error(f"Error converting DOCX to MD: {e}")
            return None

