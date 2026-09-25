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
import traceback
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Set

import pypdf
import docx2txt

from llama_index.core import (
    VectorStoreIndex, SimpleDirectoryReader, StorageContext, load_index_from_storage, Document,
)
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
        # Any speaker name up to 40 characters: "Tenno Henka" and
        # "Kaia-Autonomous channel" are single speakers, and a one-word pattern
        # glued their turns onto whoever spoke before them.
        r'(\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] [^\]:\n]{1,40}: )',
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


    def _initialize_indices(self):
        """Initialize hierarchical indices from storage or create new ones."""
        with self._data_lock:
            index_types = ['persona', 'user_profiles', 'knowledge', 'logs', 'dreams']
            for itype in index_types:
                itype_dir = os.path.join(self.persist_dir, itype)
                # A persist killed between its two renames leaves the last good
                # copy in <itype>_old and no <itype>: restore it rather than
                # start an empty index and re-embed everything.
                old_dir = f"{itype_dir}_old"
                if not os.path.exists(itype_dir) and os.path.isdir(old_dir):
                    os.rename(old_dir, itype_dir)
                    log_warning(f"Restored {itype} index from {old_dir} (an interrupted persist).")
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
                        
                    self.bm25_cache.pop(itype, None)
                    
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
        """Break a large document into sections before node parsing.

        Cuts at a paragraph break (or failing that a sentence end) inside the
        last quarter of each window. A fixed character stride cut mid-word, so
        most chunks of a book began and ended on half a word.
        """
        text = doc.text
        if len(text) <= chunk_size:
            return [doc]

        chunks = []
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            if end < len(text):
                window = text[start + chunk_size * 3 // 4:end]
                for sep in ("\n\n", "\n", ". "):
                    cut = window.rfind(sep)
                    if cut != -1:
                        end = start + chunk_size * 3 // 4 + cut + len(sep)
                        break
            piece = Document(text=text[start:end], metadata=doc.metadata.copy())
            piece.metadata['chunk_index'] = len(chunks)
            chunks.append(piece)
            start = end
        return chunks

    # Metadata that describes what a chunk is about. Everything else on a node
    # (absolute path, byte offsets, epoch timestamps, priority, quality score)
    # was being embedded with it: fifteen lines of plumbing ahead of the text
    # in every vector, which pulls unrelated chunks toward each other.
    EMBED_METADATA_KEYS = frozenset({"title", "user_name"})

    @classmethod
    def _prepare_nodes(cls, nodes):
        for n in nodes:
            n.excluded_embed_metadata_keys = [k for k in n.metadata if k not in cls.EMBED_METADATA_KEYS]
            n.excluded_llm_metadata_keys = list(n.metadata)
        return nodes

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
        elif ("news_brief" in file_path or "news_summary" in file_path
                or "/news/" in file_path.replace("\\", "/")):
            # Keyed on the directory as well as the filename. Filename alone
            # misses `tech_digest_*` under news/tech_updates/: prompt routing is
            # unaffected (`context_optimizer` falls back to `"news" in path`),
            # but the node's own metadata then disagrees with where it went, and
            # `!explain` reports it as general_knowledge.
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
            
        # Extract title and metadata from frontmatter or top H1 header for knowledge documents
        if hasattr(doc, 'text') and doc.text:
            raw_text = doc.text[:1500]
            if raw_text.startswith('---'):
                parts = raw_text.split('---', 2)
                if len(parts) >= 3:
                    fm = parts[1]
                    title_m = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', fm, re.MULTILINE)
                    if title_m and title_m.group(1).strip():
                        doc.metadata["title"] = title_m.group(1).strip()
                    author_m = re.search(r'^author:\s*["\']?(.*?)["\']?\s*$', fm, re.MULTILINE)
                    if author_m and author_m.group(1).strip():
                        doc.metadata["author"] = author_m.group(1).strip()
                    summary_m = re.search(r'^summary:\s*["\']?(.*?)["\']?\s*$', fm, re.MULTILINE)
                    if summary_m and summary_m.group(1).strip():
                        doc.metadata["summary"] = summary_m.group(1).strip()
            if not doc.metadata.get("title"):
                h1_m = re.search(r'^#\s+(.+)$', raw_text, re.MULTILINE)
                if h1_m:
                    doc.metadata["title"] = h1_m.group(1).strip()
            
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
                # Look for the last set of digits in the user_logs path fragment
                # Example: user_logs/Ekco_177011971818782721/interactions...
                match = re.search(r'user_logs/[^/]+?_(\d{15,20})', doc.text[:500])
                if match:
                    doc.metadata['user_id'] = match.group(1)
                    # Also try to get the name
                    name_match = re.search(r'user_logs/([^/]+?)_\d{15,20}', doc.text[:500])
                    if name_match:
                        doc.metadata['user_name'] = name_match.group(1).replace("_", " ")

        # Compute quality score.
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

            # Try to extract title from file content if markdown
            doc_title = ""
            if abs_path.endswith(('.md', '.txt')) and os.path.exists(abs_path):
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f_in:
                        head = f_in.read(1500)
                        if head.startswith('---'):
                            tm = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', head, re.MULTILINE)
                            if tm: doc_title = tm.group(1).strip()
                        if not doc_title:
                            hm = re.search(r'^#\s+(.+)$', head, re.MULTILINE)
                            if hm: doc_title = hm.group(1).strip()
                except Exception:
                    pass

            if abs_path not in self.indexed_files:
                if os.path.exists(abs_path):
                    mtime = os.path.getmtime(abs_path)
                    size = os.path.getsize(abs_path)
                    self.indexed_files[abs_path] = {
                        "mtime": mtime,
                        "size": size,
                        "nodes": node_ids,
                        "itype": resolved_itype,  # Fix #4: inject itype so BM25 cache invalidation works on boot
                        "title": doc_title
                    }
                    count_added += 1
            else:
                # Sync nodes in manifest, and backfill itype/title if missing
                self.indexed_files[abs_path]["nodes"] = node_ids
                if not self.indexed_files[abs_path].get("itype") and resolved_itype:
                    self.indexed_files[abs_path]["itype"] = resolved_itype
                if not self.indexed_files[abs_path].get("title") and doc_title:
                    self.indexed_files[abs_path]["title"] = doc_title

        log_success(f"RAG State: {len(self.indexed_files)} files in manifest ({count_added} newly discovered).")
        self._save_indexed_files()

    @staticmethod
    def _is_excluded_path(p: str) -> bool:
        """True if this path must not be in an index, whatever put it there.

        Scan-time exclusions only stop a file being *added*. Everything already
        indexed before a rule existed stays until something removes it, and the
        only removal condition here was "the file is gone from disk" — which
        these files are not. Adding the dot-directory rule to the scan left 475
        `.compacted_backup` entries sitting in the manifest: the raw forum post
        histories that compaction had replaced, still retrievable, still beside
        the profiles that superseded them.

        So the same predicate governs both ends. A rule added here takes effect
        on the next sweep instead of only on files that have yet to appear.
        """
        n = p.replace('\\', '/')
        return (RAGIndexerMixin._is_excluded_dir(n)
                or ("/user_logs/forum_" in n
                    and os.path.basename(n) != "user_profile.md")
                # The !news quick reference: a condensed copy of the same
                # day's brief, with no title or date of its own, so indexing it
                # retrieved each day's news twice and once undated.
                or os.path.basename(n).startswith("news_summary_"))

    @staticmethod
    def _is_excluded_dir(p: str) -> bool:
        """True for a directory nothing under which is ever indexed.

        Separate from the file rule because a forum user's folder is not
        excluded — its `user_profile.md` is indexed. Asking the file rule about
        the folder (basename "") excluded all of it, so a profile was indexed
        once and never refreshed again: 219 of them were three days stale.
        """
        n = p.replace('\\', '/').rstrip('/') + '/'
        if any(part.startswith(".") and part not in (".", "..")
               for part in n.split("/")):
            return True
        return "forum_posts" in n or "/_quarantine/" in n or "/_ingress/" in n

    _FILENAME_DATE = re.compile(r"(?:^|_)(20\d{2})(\d{2})(\d{2})(?=[_.])")

    @classmethod
    def _dated_filename_ts(cls, file_path: str) -> Optional[float]:
        """Noon on the date a news brief or dream names, or None.

        Recency scoring reads `timestamp`, which was the file's mtime — and
        enrichment rewrites old briefs, so a February brief scored as today's
        news. The first date in the name is the document's own: a dream about
        a dream names its own night first and its source second.
        """
        name = os.path.basename(file_path)
        if not (name.startswith(("news_", "tech_digest_", "dream_"))):
            return None
        m = cls._FILENAME_DATE.search(name)
        if not m:
            return None
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12).timestamp()
        except ValueError:
            return None

    @staticmethod
    def _vector_ids(index) -> Set[str]:
        """Ids that have an embedding in this index's vector store."""
        store = getattr(index, "vector_store", None)
        data = getattr(store, "data", None) or getattr(store, "_data", None)
        return set(getattr(data, "embedding_dict", {}) or {})

    def _delete_nodes(self, itype: str, node_ids) -> int:
        """Remove nodes from one index completely. Returns how many it held.

        `VectorStoreIndex.delete_nodes` defaults to `delete_from_docstore=False`:
        the embedding goes and the node stays, in the docstore that BM25 is
        built from and the manifest is rebuilt from at boot. Every deletion
        here had gone through that default, so every re-indexed file left its
        previous version searchable by keyword — 70% of the knowledge docstore
        by September 2026. Ids the index does not hold are skipped.
        """
        index = self.indices.get(itype)
        if index is None or not node_ids:
            return 0
        docstore = index.docstore
        vectors = self._vector_ids(index)
        held = [n for n in dict.fromkeys(node_ids)
                if n in vectors or docstore.document_exists(n)]
        if not held:
            return 0
        index.delete_nodes(held, delete_from_docstore=True)
        self.bm25_cache.pop(itype, None)
        return len(held)

    def _reconcile_indices(self) -> Set[str]:
        """Remove every node that should not be retrievable. Returns the itypes changed.

        Works from the indexes themselves, not the manifest, because the
        manifest is what lost track of them. A node goes if it has no
        embedding (a leftover of an earlier deletion), if it has no source
        file (synthetic feedback documents), if its file is gone, if
        its path is excluded, or if it is the persona, which is injected whole
        and never indexed. Manifest entries are brought into line; an existing
        file left with no live nodes is dropped from the manifest so the next
        scan indexes it again.
        """
        changed: Set[str] = set()
        report = []
        exists_cache: Dict[str, bool] = {}
        with self._data_lock:
            for itype, index in self.indices.items():
                vectors = self._vector_ids(index)
                doomed = []
                for node_id, node in index.docstore.docs.items():
                    path = (node.metadata or {}).get("file_path") or ""
                    ap = os.path.abspath(path) if path else ""
                    if ap and ap not in exists_cache:
                        exists_cache[ap] = os.path.exists(ap)
                    if (node_id not in vectors
                            or not ap
                            or not exists_cache[ap]
                            or (ap and self._is_excluded_path(ap))
                            or os.path.basename(ap) == "kaia_persona.md"):
                        doomed.append(node_id)
                # Embeddings whose node is already gone from the docstore.
                doomed.extend(v for v in vectors if not index.docstore.document_exists(v))
                if doomed:
                    removed = self._delete_nodes(itype, doomed)
                    if removed:
                        changed.add(itype)
                        report.append(f"{itype} {removed}")

            if changed:
                live = set()
                for index in self.indices.values():
                    live |= self._vector_ids(index)
                for path in list(self.indexed_files):
                    entry = self.indexed_files[path]
                    nodes = [n for n in entry.get("nodes", []) if n in live]
                    if len(nodes) != len(entry.get("nodes", [])):
                        if nodes:
                            entry["nodes"] = nodes
                            self._file_to_nodes[path] = nodes
                        else:
                            self.indexed_files.pop(path, None)
                            self._file_to_nodes.pop(path, None)

        if changed:
            log_action(f"RAG reconcile removed stale nodes: {', '.join(report)}")
        return changed

    def _prune_deleted_files(self) -> Set[str]:
        """Remove index entries for files that are gone, or must not be indexed."""
        updated_itypes = set()
        deleted_files = [
            p for p in list(self.indexed_files.keys())
            if not os.path.exists(p)
            or os.path.basename(p) == "kaia_persona.md"
            or self._is_excluded_path(p)
        ]
        if not deleted_files:
            return updated_itypes
            
        log_action(f"Detected {len(deleted_files)} deleted files. Pruning index O(k)...")
        with self._data_lock:
            node_ids = []
            for file_path in deleted_files:
                node_ids.extend(self.indexed_files[file_path].get("nodes", []))
                self.indexed_files.pop(file_path, None)
                self._file_to_nodes.pop(file_path, None)

            # Every index is offered every id; _delete_nodes removes only the
            # ones it holds. The manifest's itype has been missing or wrong on
            # old entries, and a wrong guess left the nodes retrievable.
            for itype in self.indices:
                if self._delete_nodes(itype, node_ids):
                    updated_itypes.add(itype)

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
            norm_root = root.replace('\\', '/')
            # Two exclusion rules, both structural rather than by name.
            #
            # A leading underscore means staging or quarantine: `_ingress` holds
            # raw downloads that have not been normalised or given metadata, and
            # indexing them puts unvetted web content into retrieval where it is
            # presented as grounded fact. `process_ingress.py` moves them into
            # the corpus once cleaned.
            #
            # A leading dot means working data: test fixtures (`corpus_dir()`,
            # test_telemetry_isolation) and the backup directories written by
            # compaction and dream consolidation. Those hold content those tools
            # have deliberately superseded, so indexing them returns the summary
            # *and* everything it summarised.
            #
            # Both ends must use `_is_excluded_path`. A rule applied only to the
            # scan stops new files being added and never removes the ones indexed
            # before it existed — see `_prune_deleted_files`.
            if self._is_excluded_dir(norm_root):
                continue
            # A forum user's *profile* is worth retrieving; their complete post
            # history is not. Raw histories and interaction dumps outweigh the
            # profiles by an order of magnitude and land in the `logs` index
            # alongside Discord conversation history, where a years-old thread
            # competes on volume with what someone said yesterday.
            #
            # `user_profile.md` is untouched — it goes to the separate
            # `user_profiles` index. The excluded files stay on disk; forum
            # drafting reads them directly rather than through RAG.
            for file in files:
                # The file rule as well as the directory rule: without it a
                # file-level exclusion (a forum post history, the news quick
                # reference) was indexed by the scan and only removed by the
                # next refresh's prune.
                if self._is_excluded_path(os.path.join(norm_root, file)):
                    continue
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, file)
                    norm_path = os.path.abspath(full_path)
                    mtime = os.path.getmtime(norm_path)
                    
                    itype = 'knowledge'
                    if file == "kaia_persona.md":
                        # Injected into every prompt in full; a retrieved
                        # chunk of it only displaces real context.
                        continue
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

        # The persona file is deliberately not indexed: it is injected into every
        # prompt in full, so a retrieved chunk of it only displaces real context.
        
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
                    self._delete_nodes(itype, nodes_to_delete)
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
        """Index what was appended to a log since the last pass.

        Offsets are in bytes. They were character counts from `f.read()`,
        compared against the byte size and handed to a text-mode `seek()`; on
        any file with a curly quote the seek landed early and the next pass
        indexed the end of the conversation a second time.

        The entry keeps a hash of the bytes already indexed. A log rewritten in
        place (a corrected turn, a sanitising pass) no longer matches it, and is
        re-indexed from the start instead of from an offset into different text.
        """
        import hashlib
        target_index = self.indices[itype]
        entry = self.indexed_files.get(abs_path) or {}

        with open(file_path, 'rb') as f:
            data = f.read()

        indexed = entry.get("indexed_bytes")
        if indexed is None and entry.get("nodes"):
            # An entry written before byte offsets: its nodes carry character
            # offsets into the file as it is now. Convert once.
            chars = 0
            for node_id in entry["nodes"]:
                node = target_index.docstore.get_node(node_id, raise_error=False)
                if node:
                    chars = max(chars, node.metadata.get('file_offset', 0) + node.metadata.get('content_length', 0))
            indexed = len(data.decode('utf-8', errors='replace')[:chars].encode('utf-8'))
            entry["indexed_prefix_sha1"] = hashlib.sha1(data[:indexed]).hexdigest()
        indexed = indexed or 0

        rewritten = indexed and (
            len(data) < indexed
            or entry.get("indexed_prefix_sha1") not in (None, hashlib.sha1(data[:indexed]).hexdigest())
        )
        if rewritten:
            log_action(f"Log rewritten since it was indexed; re-indexing in full: {file_path}")
            with self._data_lock:
                self._delete_nodes(itype, entry.get("nodes", []))
            entry = {}
            indexed = 0

        mtime = os.path.getmtime(file_path)
        new_bytes = data[indexed:]

        def _record(node_ids):
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": len(data),
                "nodes": node_ids,
                "itype": itype,
                "indexed_bytes": len(data),
                "indexed_prefix_sha1": hashlib.sha1(data).hexdigest(),
            }
            self._file_to_nodes[abs_path] = node_ids

        existing_nodes = list(entry.get("nodes", []))
        new_content = new_bytes.decode('utf-8', errors='replace')
        if not new_content.strip():
            with self._data_lock:
                _record(existing_nodes)
            return bool(rewritten)

        conversation_ts = self._extract_log_conversation_ts(new_content, mtime)
        from llama_index.core import Document as LlamaDocument
        doc = LlamaDocument(text=new_content, metadata={
            'file_path': abs_path,
            'file_offset': indexed,
            'content_length': len(new_bytes),
            'last_modified_at': mtime,
            'timestamp': conversation_ts,
            'itype': itype
        })
        self._apply_priority_metadata(doc, itype, file_path)

        parser = self._get_node_parser_for_doc(itype, file_path)
        nodes = parser.get_nodes_from_documents([doc])

        with self._data_lock: # Lock only for the final insertion and manifest update
            target_index.insert_nodes(self._prepare_nodes(nodes))
            _record(list(dict.fromkeys(existing_nodes + [n.node_id for n in nodes])))
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
                conversation_ts = self._dated_filename_ts(file_path) or mtime
            doc.metadata.update({'last_modified_at': mtime, 'timestamp': conversation_ts, 'file_path': abs_path, 'itype': itype})
            self._apply_priority_metadata(doc, itype, file_path)
            if itype == 'persona': doc.metadata['user_id'] = "KAIA_SYSTEM"
            
            for sub_doc in self._pre_chunk_document(doc):
                # self._apply_priority_metadata(sub_doc, itype, file_path) # Duplicate call removed
                nodes = parser.get_nodes_from_documents([sub_doc])
                processed_nodes_batch.append(nodes)
        
        with self._data_lock: # Lock only for the final insertion and manifest update
            for nodes in processed_nodes_batch:
                self.indices[itype].insert_nodes(self._prepare_nodes(nodes))
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
                # The converted Markdown sits beside the original and is
                # indexed by the next scan like any other document, with its
                # own manifest entry — indexing it here as well put it in twice.
                # The original is recorded as seen so it is not retried.
                with self._data_lock:
                    self.indexed_files[os.path.abspath(file_path)] = {
                        "mtime": os.path.getmtime(file_path), "size": 0, "nodes": [], "itype": itype}
                return False
        
        # Logged, not moved. A file that fails to index stays where it is;
        # relocating it hides the fault and breaks anything referencing the path.
        log_critical(f"UNABLE TO INDEX CORRUPT FILE: {file_path}. Keeping in original location.")
        return False


    def _persist_updated_indices(self, updated_itypes: Set[str]) -> Set[str]:
        """Save indices to disk and invalidate/save BM25 cache.

        Returns the set that actually reached disk. Per-index failures are
        caught and execution continues, so without this the caller announced
        "Batch persistence complete for: logs, dreams, knowledge, persona"
        naming every type it *attempted* — including any that had just logged
        "Failed to persist". The summary line contradicted the error above it,
        and the summary is the one that surfaces in the dashboard.
        """
        self.persist_needed = True
        
        # 1. Drop the changed indices' BM25; it rebuilds on next use.
        with self._data_lock:
            for itype in updated_itypes:
                self.bm25_cache.pop(itype, None)

        # 2. Heavy Disk I/O (NO LOCK HELD)
        # We don't hold the global data lock during storage_context.persist()
        # because it performs slow filesystem writes. The index objects 
        # themselves are thread-safe for persistence.
        persisted: Set[str] = set()
        for itype in updated_itypes:
            try:
                persist_path = os.path.join(self.persist_dir, itype)
                self.indices[itype].storage_context.persist(persist_dir=persist_path)
                log_success(f"Index '{itype}' persisted.")
                persisted.add(itype)
            except Exception as e: 
                log_error(f"Failed to persist {itype}: {e}")
                
        self._save_indexed_files()
        return persisted

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
                
            corrupt_dir = os.path.join(self.knowledge_base_dir, "_quarantine", "corrupt_files")
            if not os.path.exists(corrupt_dir): os.makedirs(corrupt_dir)

            updated_itypes = await asyncio.to_thread(self._prune_deleted_files)
            updated_itypes |= await asyncio.to_thread(self._reconcile_indices)
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
                persisted = await asyncio.to_thread(
                    self._persist_updated_indices, updated_itypes)
                failed = updated_itypes - (persisted or set())
                if failed:
                    log_warning(
                        f"Batch persistence partial: {', '.join(sorted(persisted))} saved; "
                        f"FAILED {', '.join(sorted(failed))}."
                    )
                else:
                    log_success(f"Batch persistence complete for: {', '.join(sorted(persisted))}")
            elif new_file_paths:
                # Still save the manifest if we scanned files
                await asyncio.to_thread(self._save_indexed_files)
                
        except Exception as e:
            log_error(f"Error in parallel RAG refresh: {e}")
            log_debug(traceback.format_exc())
        finally:
            self._indexing_in_progress = False
            self._index_lock.release()
            if self._refresh_pending:
                log_info("Triggering pending RAG refresh...")
                
                async def trigger_refresh():
                    await asyncio.sleep(2.0)
                    await self.refresh_knowledge_base(max_concurrent_files)
                    
                from utils.infrastructure.monitoring.async_task_registry import task_registry
                task_registry.register("rag_trigger_refresh", asyncio.create_task(trigger_refresh()))

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

