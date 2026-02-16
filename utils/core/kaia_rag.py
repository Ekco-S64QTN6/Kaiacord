import os
import re
import asyncio
import time
import shutil
import logging
import warnings
import pypdf
import glob
import docx2txt
import threading
import random
import traceback
import concurrent.futures

# Suppress noisy logs from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("llama_index").setLevel(logging.WARNING)
logging.getLogger("pypdf").setLevel(logging.ERROR)  # Suppress PDF warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)
# More aggressive suppression
logging.getLogger("httpx").propagate = False
logging.getLogger("httpcore").propagate = False
logging.getLogger("llama_index").propagate = False
logging.getLogger("pypdf").propagate = False
logging.getLogger("pdfminer").propagate = False

# Suppress all warnings
warnings.filterwarnings("ignore")
from datetime import datetime
from functools import wraps
from typing import List, Dict, Optional, Any, Tuple, Set
import numpy as np
from rank_bm25 import BM25Okapi
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage, Document, QueryBundle
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter, SemanticSplitterNodeParser, CodeSplitter
from llama_index.core.schema import NodeWithScore
from utils.infrastructure.logging.kaia_logger import log_success, log_info, log_warning, log_error, log_critical, log_action, log_debug
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config
from utils.core.kaia_intelligence import Intent
from utils.social.kaia_identities import registry

class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open"""
    pass

# HallucinationDetector has been moved to utils/core/response_filter.py
from utils.core.response_filter import HallucinationDetector



class SimpleBM25Retriever:
    """Simple BM25 retriever for hybrid search."""
    def __init__(self, nodes):
        from utils.core.rag_utils import get_node_text
        self.nodes = nodes
        self.tokenized_docs = [self._tokenize(get_node_text(node)) for node in nodes]
        self.bm25 = BM25Okapi(self.tokenized_docs) if self.tokenized_docs else None
        
        # MEMORY OPTIMIZATION: Clear tokenized_docs after BM25 initialization
        # The BM25Okapi object internally stores the stats it needs (doc_freqs, etc.)
        # so we don't need the raw token lists in RAM unless we plan to add more docs later.
        self.tokenized_docs = None
        import gc
        gc.collect()
    
    def _tokenize(self, text):
        return re.sub(r'[^\w\s]', ' ', text.lower()).split()
    
    def retrieve(self, query, top_k=10):
        if not self.bm25: return []
        tokenized_query = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.nodes[idx], float(scores[idx])))
        return results

class HybridRetriever:
    """Combines Vector and BM25 retrieval using RRF."""
    def __init__(self, vector_index, bm25_retriever, multiplier=60.0):
        self.vector_index = vector_index
        self.bm25 = bm25_retriever
        self.multiplier = multiplier
        
    async def retrieve(self, query, top_k=5, alpha=0.5, query_bundle=None):
        # 1. Vector Retrieval
        vector_retriever = self.vector_index.as_retriever(similarity_top_k=top_k*2)
        
        # Use provided query_bundle if available
        bundle = query_bundle if query_bundle is not None else query
        vector_nodes = await vector_retriever.aretrieve(bundle)
        
        # 2. BM25 Retrieval (Offload to thread)
        bm25_results = await asyncio.to_thread(self.bm25.retrieve, query, top_k=top_k*2)
        
        # 3. Reciprocal Rank Fusion (RRF)
        combined_scores = {} # node_id -> score
        node_map = {} # node_id -> node
        
        # Vector RRF
        for rank, node_with_score in enumerate(vector_nodes):
            node = node_with_score.node
            node_id = node.node_id
            node_map[node_id] = node
            combined_scores[node_id] = combined_scores.get(node_id, 0) + alpha * (1.0 / (rank + 60))
            
        # BM25 RRF
        for rank, (node, score) in enumerate(bm25_results):
            node_id = node.node_id
            node_map[node_id] = node
            combined_scores[node_id] = combined_scores.get(node_id, 0) + (1.0 - alpha) * (1.0 / (rank + 60))
            
        # Sort and return top_k as NodeWithScore objects
        sorted_nodes = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        # Scale score to normalized RRF scores (approx 0-1 range) for consistent thresholding with cosine similarity
        return [NodeWithScore(node=node_map[node_id], score=score * self.multiplier) for node_id, score in sorted_nodes[:top_k]]

class CircuitBreaker:
    """Circuit breaker for external services (thread-safe)"""
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failures = 0
        self.last_failure = 0.0
        self.threshold = failure_threshold
        self.timeout = reset_timeout
        self._lock = threading.Lock()
        
    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if self.is_open():
                log_warning(f"Circuit breaker open for {func.__name__}")
                raise CircuitOpenError(f"Service {func.__name__} unavailable")
            try:
                result = func(*args, **kwargs)
                self._reset()
                return result
            except Exception as e:
                with self._lock:
                    self.failures += 1
                    self.last_failure = time.time()
                raise
        return wrapper
        
    def is_open(self) -> bool:
        with self._lock:
            return (self.failures >= self.threshold and 
                    time.time() - self.last_failure < self.timeout)
                
    def _reset(self):
        with self._lock:
            self.failures = 0

def thread_safe_rag_operation(func):
    """Decorator to ensure thread safety for RAG operations."""
    import inspect
    is_async = inspect.iscoroutinefunction(func)

    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        lock_timeout = getattr(config, 'rag_lock_seconds', 10.0)
        
        if func.__name__ == 'retrieve':
            acquired = self._lock.acquire(timeout=0.5)
            try:
                return await func(self, *args, **kwargs)
            finally:
                if acquired: self._lock.release()
        else:
            if not self._lock.acquire(timeout=lock_timeout):
                log_warning(f"RAG operation {func.__name__} timed out")
                return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
            try:
                if getattr(self, '_indexing_in_progress', False) and func.__name__ not in ['refresh_knowledge_base']:
                    return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
                return await func(self, *args, **kwargs)
            finally:
                self._lock.release()

    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        lock_timeout = getattr(config, 'rag_lock_seconds', 10.0)
        
        if func.__name__ == 'retrieve':
            acquired = self._lock.acquire(timeout=0.5)
            try:
                return func(self, *args, **kwargs)
            finally:
                if acquired: self._lock.release()
        else:
            if not self._lock.acquire(timeout=lock_timeout):
                return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
            try:
                return func(self, *args, **kwargs)
            finally:
                self._lock.release()

    return async_wrapper if is_async else sync_wrapper

class KaiaRAG:
    def __init__(self, knowledge_base_dir="./knowledge_base", persist_dir="./storage"):
        self.knowledge_base_dir = knowledge_base_dir
        self.persist_dir = persist_dir
        self.indexed_files = {}  # Track indexed files {path: mtime} to detect updates
        
        # Configure Ollama Embedding
        # Force CPU for embeddings to save VRAM for the main 12b model
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434",
            query_prefix="search_query: ",
            text_prefix="search_document: ",
            request_timeout=config.embedding_request_seconds,
            # Force CPU for embeddings to save VRAM for the main 12b model
            # Ollama requires these to be in an 'options' dict
            additional_kwargs={"options": {"num_gpu": 0}} 
        )
        
        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.node_parser = SentenceSplitter(
            chunk_size=config.rag_node_chunk_size, 
            chunk_overlap=config.rag_node_chunk_overlap
        )
        
        # Use GPU Manager for LLM settings
        from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
        gpu_manager = OllamaGPUManager("gemma3:12b")
        gpu_options = gpu_manager.get_gpu_options(for_chat=True)
        
        # Ensure num_gpu is passed correctly to Ollama LLM
        # LlamaIndex passes additional_kwargs to the API options
        llm_timeout = getattr(config, 'llm_request_seconds', 360.0)
        Settings.llm = Ollama(
            model="gemma3:12b", 
            request_timeout=llm_timeout, 
            additional_kwargs=gpu_options
        )
        
        # Lazy load indices for faster startup
        self.indices = {} # Hierarchical indices
        self.bm25_cache = {} # Cache for BM25 retrievers {itype: (timestamp, retriever)}
        self.persist_needed = False
        self._lock = threading.RLock()
        
        # Performance Cache: Known Users (避免每次检索都扫描目录)
        self._known_users_cache = []
        self._last_user_scan = 0

        self._user_scan_interval = getattr(config, 'rag_user_scan_interval', 300)
        self._refresh_lock = threading.Lock() # Exclusive lock for the refresh process
        self._indexing_in_progress = False
        self._refresh_pending = False # Single-flight "dirty" flag
        self._bot_user_id = None # Set by Discord bot on startup
        self._initialized = False

    async def initialize_async(self):
        """Asynchronously initialize hierarchical indices."""
        if self._initialized: return
        log_action("Initializing RAG indices in background...")
        await asyncio.to_thread(self._initialize_indices)
        self._initialized = True
        log_success("RAG indices initialized.")

    async def get_recent_files_async(self, limit: int = 5) -> List[Dict[str, str]]:
        """Async wrapper for get_recent_files."""
        return await asyncio.to_thread(self.get_recent_files, limit)

    def get_recent_files(self, limit: int = 5) -> List[Dict[str, str]]:
        """Get the most recently modified files in the knowledge base, including logs and news with context"""
        files = []
        for root, _, filenames in os.walk(self.knowledge_base_dir):
            # Special handling for directories to provide context
            context_prefix = ""
            is_log = "user_logs" in root
            is_news = "news" in root
            
            if is_log:
                # Extract username from directory name (e.g., Ekco_177011971818782721)
                folder_name = os.path.basename(root)
                if "_" in folder_name:
                    username = folder_name.split("_")[0]
                    context_prefix = f"Log ({username}): "
                else:
                    context_prefix = f"Log ({folder_name}): "
            elif is_news:
                context_prefix = "News: "
            
            for f in filenames:
                path = os.path.join(root, f)
                # Skip trigger files and hidden files
                if f.startswith('.') or not f.endswith(('.txt', '.md', '.pdf', '.docx')):
                    continue
                    
                mtime = os.path.getmtime(path)
                
                # Boost latest daily news and DREAMS to ensure visibility
                weight = mtime
                
                from utils.infrastructure.system.yaml_config import config
                daily_news_boost = getattr(config, 'rag_boost_daily_news', 172800)
                dream_boost = getattr(config, 'rag_boost_dreams', 64800)
                
                if "daily" in root and f.startswith("news_brief"):
                    weight += daily_news_boost 
                elif "kaia_dreams" in root:
                    weight += dream_boost
                
                files.append({
                    "filename": f,
                    "path": path,
                    "mtime": mtime,
                    "weight": weight,
                    "context": context_prefix
                })
        
        # Sort by weight descending
        files.sort(key=lambda x: x["weight"], reverse=True)
        
        # Extract snippets for the top files
        recent_with_snippets = []
        for f_info in files[:limit]:
            snippet = ""
            try:
                if f_info["filename"].endswith(('.txt', '.md')):
                    with open(f_info["path"], 'r', encoding='utf-8', errors='replace') as f:
                        # For logs, skip potentially repetitive headers if simple
                        content = f.read(500)
                        # Extract a clean snippet from the end of the log if it's an interaction log
                        if "User Log" in content or "Interaction" in content:
                           # Try to get the last ~300 chars to see latest interaction
                           snippet = content[-300:].strip().replace("\n", " ") + "..."
                        else:
                           snippet = content[:300].strip().replace("\n", " ") + "..."
                elif f_info["filename"].endswith('.pdf'):
                    snippet = "[PDF Content Indexed]"
                else:
                    snippet = "[Document Indexed]"
            except Exception: pass
            
            # Combine context prefix with filename or just use prefix if filename is generic
            display_name = f_info["filename"]
            if f_info["context"]:
                display_name = f_info["context"] + f_info["filename"]
                
            recent_with_snippets.append({
                "filename": display_name,
                "snippet": snippet
            })
            
        return recent_with_snippets

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
        with self._lock:
            index_types = ['persona', 'user_profiles', 'conversations', 'knowledge', 'logs', 'dreams']
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
                    log_error(f"Error initializing {itype} index: {e}")
                    self.indices[itype] = VectorStoreIndex.from_documents([])
            
            # Populate indexed files from all indices
            self._populate_indexed_files()
            log_debug("All hierarchical indices initialized.")

    def _get_node_parser_for_doc(self, itype: str, file_path: str):
        """Dynamic chunking based on content type and index target"""
        if itype == 'logs' or itype == 'conversations':
            # Keep conversations together with larger chunks
            return SentenceSplitter(chunk_size=1024, chunk_overlap=200)
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

    def is_garbage_text(self, text: str) -> bool:
        """Detect garbage text from bad PDF extractions"""
        garbage_patterns = [
            r"Page \d+ of \d+",
            r"© \d+",
            r"All rights reserved",
            r"Confidential",
            r"Proprietary",
            r"(?:\[.*?\]\s*){5,}",  # Excessive consecutive brackets (5+) indicate garbled extraction
            r"\x00",  # Null characters
        ]
        
        text_lower = text.lower()
        
        # If it's very short and looks like metadata
        if len(text.strip()) < 50 and ("page" in text_lower or "chapter" in text_lower):
            return True
        
        # Check patterns
        for pattern in garbage_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False

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
            doc.metadata["source_type"] = "dream"
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

        
        # Add garbage detection metadata
        if self.is_garbage_text(doc.text):
            doc.metadata["priority"] = 0.0
            doc.metadata["source_type"] = "garbage"
            doc.metadata["garbage"] = True

    def _populate_indexed_files(self):
        """Populate the set of indexed files from all hierarchical indices."""
        with self._lock:
            valid_files = {} # path -> mtime
            
            for itype, index in self.indices.items():
                stale_nodes = []
                for node_id, node in index.docstore.docs.items():
                    file_path = node.metadata.get('file_path')
                    if file_path:
                        abs_path = os.path.abspath(file_path)
                        if os.path.exists(abs_path):
                            indexed_mtime = node.metadata.get('last_modified_at', 0)
                            if abs_path not in valid_files or indexed_mtime > valid_files[abs_path]:
                                valid_files[abs_path] = indexed_mtime
                        else:
                            stale_nodes.append(node_id)
                
                if stale_nodes:
                    log_debug(f"Cleaning up {len(stale_nodes)} stale entries from {itype} index...")
                    for node_id in stale_nodes:
                        try:
                            index.delete_nodes([node_id])
                        except Exception as e:
                            log_warning(f"Could not delete node {node_id} in {itype}: {e}")
            
            self.indexed_files = valid_files
            log_success(f"Populated {len(self.indexed_files)} valid indexed files.")

    def refresh_knowledge_base(self):
        """Scan knowledge base for new/modified files and update indices.
        Uses single-flight logic: only one refresh at a time, subsequent calls mark it dirty.
        """
        # Single-flight check
        if not self._refresh_lock.acquire(blocking=False):
            log_info("RAG refresh already in progress, marking as pending.")
            self._refresh_pending = True
            return

        try:
            self._indexing_in_progress = True
            self._refresh_pending = False
            
            # Selective BM25 cache clearing moved inside the update loop
            # and finalized at the end of the refresh to avoid redundant rebuilds.
            # with self._lock:
            #     self.bm25_cache.clear()
            
            if not os.path.exists(self.knowledge_base_dir):
                os.makedirs(self.knowledge_base_dir)
                return

            log_action(f"Refreshing knowledge base...")
            
            # Create corrupt_files directory if it doesn't exist
            corrupt_dir = os.path.join(self.knowledge_base_dir, "corrupt_files")
            if not os.path.exists(corrupt_dir):
                os.makedirs(corrupt_dir)

            # Track which indices actually changed
            updated_itypes = set()

            # 1. Detect and prune DELETED files
            # This ensures that if the user deletes files from knowledge_base, 
            # the index is updated to match.
            deleted_files = [p for p in list(self.indexed_files.keys()) if not os.path.exists(p)]
            if deleted_files:
                log_action(f"Detected {len(deleted_files)} deleted files. Pruning index...")
                for file_path in deleted_files:
                    abs_path = os.path.abspath(file_path)
                    for itype, index in self.indices.items():
                        nodes_to_delete = [
                            node_id for node_id, node in index.docstore.docs.items()
                            if node.metadata.get('file_path') == file_path or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
                        ]
                        if nodes_to_delete:
                            log_info(f"Pruning {len(nodes_to_delete)} stale nodes for {os.path.basename(file_path)} from {itype}")
                            for node_id in nodes_to_delete:
                                index.delete_nodes([node_id])
                            updated_itypes.add(itype)
                    
                    if file_path in self.indexed_files:
                        del self.indexed_files[file_path]
                    elif abs_path in self.indexed_files:
                        del self.indexed_files[abs_path]

            # 2. Manually walk the directory to find NEW files
            new_file_paths = []
            supported_exts = [".pdf", ".txt", ".md", ".docx"]
            
            for root, dirs, files in os.walk(self.knowledge_base_dir):
                if "corrupt_files" in root:
                    continue
                    
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in supported_exts:
                        full_path = os.path.join(root, file)
                        norm_path = os.path.abspath(full_path)
                        mtime = os.path.getmtime(norm_path)
                        
                        # Determine target index
                        itype = 'knowledge'
                        if "user_logs" in full_path:
                            if "user_profile.md" in file:
                                itype = 'user_profiles'
                            else:
                                itype = 'logs'
                        elif "kaia_dreams" in full_path:
                            itype = 'dreams'
                        
                        is_new = norm_path not in self.indexed_files
                        is_modified = not is_new and mtime > self.indexed_files[norm_path]
                        
                        if (is_new or is_modified) and "user_memories.txt" not in file:
                            is_log = itype == 'logs'
                            new_file_paths.append((full_path, is_modified, is_log, itype))

            # 3. Also index the persona file from knowledge_base
            persona_file = "knowledge_base/kaia_persona.md"
            if os.path.exists(persona_file):
                norm_path = os.path.abspath(persona_file)
                mtime = os.path.getmtime(norm_path)
                if norm_path not in self.indexed_files or mtime > self.indexed_files[norm_path]:
                    new_file_paths.append((persona_file, norm_path in self.indexed_files, False, 'persona'))

            if not new_file_paths:
                log_debug("No new documents to index.")
            else:
                log_action(f"Found {len(new_file_paths)} new or modified documents. Processing...")
                
                for file_path, is_modified, is_log, itype in new_file_paths:
                    # I/O MITIGATION: Tiny sleep between files to allow OS/IDE to breathe
                    time.sleep(0.05)
                
                    target_index = self.indices[itype]
                    if is_modified and not is_log:
                        log_action(f"Detected update in {itype} file. Re-indexing...")
                        log_info(file_path)
                        abs_path = os.path.abspath(file_path)
                        nodes_to_delete = [
                            node_id for node_id, node in target_index.docstore.docs.items()
                            if node.metadata.get('file_path') == file_path or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
                        ]
                        if nodes_to_delete:
                            print(f"Deleting {len(nodes_to_delete)} old nodes from {itype} for {file_path}")
                            for node_id in nodes_to_delete:
                                target_index.delete_nodes([node_id])
                            updated_itypes.add(itype)
                    elif is_log:
                        # Don't spam the individual files
                        log_debug(f"Checking for new content in {itype} log: {file_path}")
                    else:
                        log_debug(f"Processing new {itype} file: {file_path}")
                        
                    try:
                        abs_path = os.path.abspath(file_path)
                        # Load file content
                        if is_log:
                            # TAIL-INDEXING for logs: only index what's new
                            last_offset = 0
                            for node in target_index.docstore.docs.values():
                                if os.path.abspath(node.metadata.get('file_path', '')) == abs_path:
                                    offset = node.metadata.get('file_offset', 0)
                                    length = node.metadata.get('content_length', 0)
                                    last_offset = max(last_offset, offset + length)
                            
                            file_size = os.path.getsize(file_path)
                            if file_size <= last_offset:
                                log_debug(f"No new content for index '{itype}' at offset {last_offset}")
                                self.indexed_files[abs_path] = os.path.getmtime(file_path)
                                continue
                                
                            log_action(f"Indexing new {itype} content from offset {last_offset}...")
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                f.seek(last_offset)
                                new_content = f.read()
                                
                            if new_content.strip():
                                # === SMART FICTION FILTER ===
                                # Only filter specific fictional story patterns, NOT user names
                                # Perspective decoupling handles first-person artifacts at context time.
                                # ============================

                                mtime = os.path.getmtime(file_path)
                                # Create a document from the new content
                                doc = Document(
                                    text=new_content,
                                    metadata={
                                        "file_path": abs_path,
                                        "last_modified_at": mtime,
                                        "file_offset": last_offset,
                                        "content_length": len(new_content),
                                        "source": "user_logs"
                                    }
                                )
                                self._apply_priority_metadata(doc, itype, file_path)
                                # Use specialized node parser
                                parser = self._get_node_parser_for_doc(itype, file_path)
                                nodes = parser.get_nodes_from_documents([doc])
                                target_index.insert_nodes(nodes)
                                updated_itypes.add(itype)
                                
                                self.indexed_files[abs_path] = mtime
                                log_success(f"Indexed {len(new_content)} new characters from {itype} log.")
                            else:
                                self.indexed_files[abs_path] = os.path.getmtime(file_path)
                        else:
                            # Robust file loading with encoding fallbacks
                            docs = None
                            try:
                                reader = SimpleDirectoryReader(input_files=[file_path])
                                docs = reader.load_data()
                            except UnicodeDecodeError as unicode_err:
                                # Try with different encodings
                                log_warning(f"UTF-8 decode failed for {file_path}, trying fallback encodings...")
                                
                                fallback_encodings = ['latin-1', 'cp1252', 'iso-8859-1']
                                for enc in fallback_encodings:
                                    try:
                                        # Read with fallback encoding and re-encode to UTF-8
                                        with open(file_path, 'r', encoding=enc, errors='replace') as f:
                                            content = f.read()
                                        
                                        # Create Document manually from the content
                                        from llama_index.core import Document as LlamaDocument
                                        docs = [LlamaDocument(text=content)]
                                        log_success(f"Recovered file using {enc} encoding")
                                        break
                                    except Exception as enc_err:
                                        log_debug(f"{enc} encoding failed: {enc_err}")
                                        continue
                                
                                if not docs:
                                    # Last resort: binary read with best-effort decoding
                                    log_warning(f"All encodings failed, using binary read with error replacement")
                                    with open(file_path, 'rb') as f:
                                        binary_content = f.read()
                                    content = binary_content.decode('utf-8', errors='replace')
                                    from llama_index.core import Document as LlamaDocument
                                    docs = [LlamaDocument(text=content)]
                            
                            if not docs:
                                raise ValueError("Failed to load file with any encoding")
                                
                            mtime = os.path.getmtime(file_path)
                            parser = self._get_node_parser_for_doc(itype, file_path)
                            for doc in docs:
                                doc.metadata['last_modified_at'] = mtime
                                doc.metadata['file_path'] = os.path.abspath(file_path)
                                doc.metadata['itype'] = itype
                                
                                self._apply_priority_metadata(doc, itype, file_path)
                                
                                if itype == 'persona':
                                    doc.metadata['user_id'] = "KAIA_SYSTEM"
                                
                                # Extract user metadata if in user_logs
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
                                
                                # Pre-chunk large documents to avoid embedding overflows
                                sub_docs = self._pre_chunk_document(doc)
                                for sub_doc in sub_docs:
                                    # Ensure sub-docs inherit priority metadata
                                    self._apply_priority_metadata(sub_doc, itype, file_path)
                                    nodes = parser.get_nodes_from_documents([sub_doc])
                                    target_index.insert_nodes(nodes)
                            
                            updated_itypes.add(itype)
                            self.indexed_files[abs_path] = mtime
                            log_success(f"Indexed {file_path} into {itype} index.")
                            if itype != 'logs':
                                snippet = ""
                                try:
                                    # Extract direct snippet from first doc
                                    snippet = docs[0].text[:300].replace("\n", " ") + "..."
                                except Exception: pass
                                bot_state.add_ingestion(os.path.basename(file_path), snippet=snippet)
                            
                    except Exception as e:
                        log_error(f"Failed to load file: {e}")
                        log_info(file_path)
                        
                        conversion_succeeded = False
                        
                        # Attempt conversion if it's a PDF or DOCX
                        if file_path.lower().endswith((".pdf", ".docx")):
                            ext = ".pdf" if file_path.lower().endswith(".pdf") else ".docx"
                            log_action(f"Attempting to recover file by converting to Markdown...")
                            log_info(file_path)
                            
                            if ext == ".pdf":
                                md_path = self._convert_pdf_to_md(file_path)
                            else:
                                md_path = self._convert_docx_to_md(file_path)
                                
                            if md_path:
                                try:
                                    # Load the newly created MD file
                                    md_reader = SimpleDirectoryReader(input_files=[md_path])
                                    md_docs = md_reader.load_data()
                                    if md_docs:
                                        mtime = os.path.getmtime(md_path)
                                        orig_mtime = os.path.getmtime(file_path)
                                        for doc in md_docs:
                                            doc.metadata['last_modified_at'] = mtime
                                            doc.metadata['itype'] = itype
                                            parser = self._get_node_parser_for_doc(itype, md_path)
                                            nodes = parser.get_nodes_from_documents([doc])
                                            target_index.insert_nodes(nodes)
                                        updated_itypes.add(itype)
                                        self.indexed_files[os.path.abspath(md_path)] = mtime
                                        # Also track original PDF as "handled" so we don't retry
                                        self.indexed_files[os.path.abspath(file_path)] = orig_mtime
                                        log_success(f"Successfully indexed converted Markdown")
                                        log_info(md_path)
                                        conversion_succeeded = True
                                        if itype != 'logs':
                                            snippet = ""
                                            try:
                                                with open(md_path, 'r', encoding='utf-8') as f:
                                                    snippet = f.read(300).replace("\n", " ") + "..."
                                            except Exception: pass
                                            bot_state.add_ingestion(os.path.basename(file_path), snippet=snippet)
                                    else:
                                        log_warning(f"Converted MD was empty.")
                                except Exception as md_err:
                                    log_error(f"Failed to index converted MD: {md_err}")

                        # Only move to corrupt_files if conversion failed or wasn't attempted
                        if not conversion_succeeded:
                            try:
                                dest_path = os.path.join(corrupt_dir, os.path.basename(file_path))
                                # Handle name collisions in corrupt_dir
                                if os.path.exists(dest_path):
                                    dest_path = f"{dest_path}_{int(time.time())}"
                                
                                shutil.move(file_path, dest_path)
                                log_critical(f"MOVED CORRUPT FILE TO: {dest_path}")
                            except Exception as move_err:
                                log_warning(f"Failed to move corrupt file: {move_err}")

                # Mark for persistence
                self.persist_needed = True

                # Selective BM25 cache invalidation & Consolidated Persistence
                for itype in updated_itypes:
                    if itype in self.bm25_cache:
                        log_info(f"Invalidating BM25 cache for '{itype}' index due to updates.")
                        self.bm25_cache[itype] = None
                    
                    # IMMEDIATE PERSISTENCE: Save the index state once per type
                    try:
                        itype_dir = os.path.join(self.persist_dir, itype)
                        self.indices[itype].storage_context.persist(persist_dir=itype_dir)
                        log_success(f"Index '{itype}' persisted to storage.")
                    except Exception as p_err:
                        log_error(f"Failed to persist {itype} index: {p_err}")
                
        except Exception as e:
            log_error(f"Error refreshing knowledge base: {e}")
            traceback.print_exc()
        finally:
            self._indexing_in_progress = False
            self._refresh_lock.release()
            
            # If another refresh was requested while we were running, re-enter directly.
            # This runs in the same thread (no orphaned Timer threads, no shutdown leak).
            if self._refresh_pending:
                log_info("Triggering pending RAG refresh...")
                time.sleep(2.0)  # Brief cooldown to prevent tight loops
                self.refresh_knowledge_base()

    @CircuitBreaker(failure_threshold=3)
    def _convert_pdf_to_md(self, pdf_path: str) -> Optional[str]:
        """Convert a PDF file to a Markdown file by extracting text."""
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
                return md_path
            else:
                log_warning(f"No text extracted from PDF")
                return None
        except Exception as e:
            log_error(f"Error converting PDF to MD: {e}")
            return None

    @CircuitBreaker(failure_threshold=3)
    def _convert_docx_to_md(self, docx_path: str) -> Optional[str]:
        """Convert a DOCX file to a Markdown file by extracting text."""
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
                return md_path
            else:
                log_warning(f"No text extracted from DOCX")
                return None
        except Exception as e:
            log_error(f"Error converting DOCX to MD: {e}")
            return None

    @thread_safe_rag_operation
    async def add_memory_async(self, user_id: int, user_name: str, text: str) -> bool:
        """Async wrapper for add_memory."""
        return await asyncio.to_thread(self.add_memory, user_id, user_name, text)

    def add_memory(self, user_id: int, user_name: str, text: str) -> bool:
        """Log a 'remembered' fact into a separate file AND the interaction log."""
        try:
            # 1. Standard interaction log (redundancy/perspective)
            self.log_user_interaction(
                user_id, 
                user_name, 
                f"[REMEMBER_COMMAND]: {text}", 
                "Logged it. I'll remember that."
            )
            
            # 2. SEPARATE INJECTED FILE (Legacy behavior for Dream Mode/Isolation)
            with self._lock:
                safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
                user_dir_name = f"{safe_user_name}_{user_id}"
                user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
                
                os.makedirs(user_log_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = os.path.join(user_log_dir, f"injected_{timestamp}.txt")
                
                log_text = f"User ({user_name}): [REMEMBER_COMMAND]: {text}\nKaia: Logged it. I'll remember that.\n"
                
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(log_text)
                    
                log_success(f"Separate memory file created: injected_{timestamp}.txt")
                return True
                
        except Exception as e:
            log_error(f"Error adding memory: {e}")
            return False

    async def log_user_interaction_async(self, user_id: int, user_name: str, message_content: str, bot_response: str, is_vision_response: bool = False) -> bool:
        """Async wrapper for log_user_interaction."""
        return await asyncio.to_thread(self.log_user_interaction, user_id, user_name, message_content, bot_response, is_vision_response)

    # Removed @thread_safe_rag_operation to ensure file writing always happens
    def log_user_interaction(self, user_id: int, user_name: str, message_content: str, bot_response: str, is_vision_response: bool = False) -> bool:
        """Log user interaction to a single file per user, rotating at 100MB.
        """
        # GUARD: Bot identity not yet initialized (on_ready hasn't fired)
        if self._bot_user_id is None:
            log_debug(f"Skipping log_user_interaction: bot_user_id not yet initialized")
            return True

        # ECHO CHAMBER PROTECTION: Prevent self-logging of bots and reflections.
        # This stops the 'Kaia' user logs folder from poisoning the identity core.
        # EXCEPTION: If user_name is "Kaia-Autonomous", it means an autonomous quip we WANT logged.
        bot_ids = [self._bot_user_id, "KAIA_SYSTEM", "KAIA_DREAM"]
        is_autonomous = user_name == "Kaia-Autonomous"
        
        if not is_autonomous and (str(user_id) in [str(bid) for bid in bot_ids if bid] or user_name == "Kaia"):
            log_debug(f"Skipping log_user_interaction for bot identity: {user_name} ({user_id})")
            return True

        # Acquire lock unconditionally to ensure we write to disk. 
        # Persistence is more important than non-blocking here.
        with self._lock:
            # 1. CANONICAL IDENTITY RESOLUTION
            # Check if this ID is linked to another (e.g. Forum <-> Discord)
            
            u_id_str = str(user_id)
            canonical_id = u_id_str
            
            # If it's a forum ID (forum_user_12345 or just digits), try to get linked Discord ID
            fid = None
            if u_id_str.startswith("forum_"):
                fid_parts = u_id_str.rsplit("_", 1)
                if len(fid_parts) > 1 and fid_parts[1].isdigit():
                    fid = int(fid_parts[1])
            elif u_id_str.isdigit() and len(u_id_str) < 15: # Forum IDs are typically shorter
                fid = int(u_id_str)
                
            if fid:
                linked_discord = registry.get_discord_id(fid)
                if linked_discord:
                    canonical_id = linked_discord
                    log_debug(f"Resolved forum ID {u_id_str} to canonical Discord ID {canonical_id}")
            
            # 2. SELECTION OF LOG DIRECTORY
            # Sanitize user_name for filesystem
            safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
            
            if canonical_id != u_id_str:
                # Use the canonical (Discord) ID to unify logs
                user_dir_name = canonical_id
            elif u_id_str == "social_bluesky_michaelschellhorn.link":
                # Keep legacy hack for this specific user if not in registry yet
                user_dir_name = "Ekco_177011971818782721"
            elif u_id_str.startswith("social_"):
                user_dir_name = u_id_str
            else:
                user_dir_name = f"{safe_user_name}_{u_id_str}"
                
            user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
            
            try:
                # Create user directory if it doesn't exist
                if not os.path.exists(user_log_dir):
                    os.makedirs(user_log_dir)
                    log_success(f"Created user log directory")
                    log_info(user_log_dir)
                
                # Find existing log file for TODAY
                today_str = datetime.now().strftime("%Y%m%d")
                interaction_log_path = os.path.join(user_log_dir, f"interactions_{today_str}.md")
                
                # Check for existing log files and handle oversized logs
                MAX_SIZE = 100 * 1024 * 1024  # 100MB in bytes
                
                if os.path.exists(interaction_log_path):
                    # If today's log exists and is oversized, create a part 2
                    if os.path.getsize(interaction_log_path) >= MAX_SIZE:
                        # Find the next available part number
                        part = 2
                        while os.path.exists(os.path.join(user_log_dir, f"interactions_{today_str}_part{part}.md")):
                            part += 1
                        interaction_log_path = os.path.join(user_log_dir, f"interactions_{today_str}_part{part}.md")
                else:
                    # Check if there's a recent log from another day to potentially reference, 
                    # but we ALWAYS start a new file for a new day to keep RAG indexing clean.
                    log_info(f"Starting new interaction log for {today_str}")
                
                # Append interaction to the single file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # CLEAN HALLUCINATIONS FROM RESPONSE BEFORE LOGGING
                if HallucinationDetector.contains_hallucination(bot_response):
                    log_warning(f"Hallucination detected in response for {user_name}. Cleaning before logging.")
                    bot_response = HallucinationDetector.clean_response(bot_response)

                # Initialize frontmatter if file is new
                is_new_file = not os.path.exists(interaction_log_path)
                
                header_text = ""
                if is_new_file:
                    header_text = "---\nsummary: \"\"\nkeywords: []\ndocument_type: Transcript\n---\n\n"
                
                interaction_text = f"User: {message_content}\nKaia: {bot_response}\n\n"
                
                # Get current size before appending for the offset
                # IF new file, offset is length of header (since we write header then interaction)
                file_offset = os.path.getsize(interaction_log_path) if not is_new_file else len(header_text)
                
                with open(interaction_log_path, "a", encoding="utf-8", errors="replace") as f:
                    if is_new_file:
                        f.write(header_text)
                    f.write(interaction_text)
                
                log_success(f"Logged interaction for {user_name} (Disk Only)")
                
                # OPTIMIZATION: Defer indexing to the periodic refresh cycle.
                # Doing insert_nodes() here triggers synchronous GPU embedding generation,
                # which blocks the event loop and competes with the detailed Intent Analysis.
                # Since short-term context handles "what did I just say", we don't need
                # milliseconds-fresh RAG for logs.
                
                # self.indices['logs'].insert_nodes(nodes) 
                
                return True

            except Exception as e:
                log_error(f"Error logging user interaction: {e}")
                traceback.print_exc()
                return False

    @thread_safe_rag_operation
    async def retrieve(self, query: str, user_id: Any = None, user_name: str = None, top_k: int = 5, 
                strict_identity: bool = False, include_news: bool = False,
                category: str = "general", intent: Optional[Intent] = None) -> List[Dict[str, Any]]:
        """
        Hierarchical retrieval with reciprocal rank fusion, intent-aware routing, 
        and dynamic relevance scoring.
        """
        if not self.indices:
            return []
            
        if not query or not query.strip():
            return []
            
        try:
            query_lower = query.lower()
            base_top_k = top_k
            
            # 1. INTENT-AWARE ROUTING & CONFIGURATION
            # Initialize flags with legacy category
            is_kaia_query = (category == "identity")
            is_social_identity = (category == "social_identity")
            is_dream_query = (category == "dream")
            is_entity_query = (category == "entity")
            is_news_query = (category == "news")
            is_casual = (category == "casual" or category == "greeting" or len(query_lower.split()) <= 4)
            
            # Override with Intent if available
            strategy = None
            if intent:
                strategy = intent.suggested_strategy
                # Map strategies to retrieval contexts
                if strategy == "PRECISE_RECALL":
                    if any(x in query_lower for x in ["who", "what", "kaia", "yourself"]):
                        is_kaia_query = True
                    else:
                        is_entity_query = True
                elif strategy == "RELATIONAL_MIRROR":
                    is_social_identity = True
                elif strategy == "ASSOCIATIVE_WANDERING":
                    # Legacy fallback
                    if "dream" in query_lower:
                        is_dream_query = True
                elif strategy == "DREAM_RECALL":
                    is_dream_query = True
                elif strategy == "SYNTHESIS_SCAN":
                    is_news_query = True
                elif strategy == "DIAGNOSTIC_DEEP_DIVE":
                    # Deep dive into error logs and system knowledge
                    pass 
                elif strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION"]:
                    is_casual = True
                
                # Trust the intent explicitly - NO length penalties
                if is_casual:
                    # Specific casual queries might still need context, but less recall
                    pass
            
            # Legacy fallback: Filter short queries that weren't caught by Intent
            is_followup_query = (not intent and len(query_lower.split()) <= 6 and not is_kaia_query and not is_social_identity and not is_dream_query)
            
            # Detect known user names for enrichment (Optimized & Threaded)
            if time.time() - self._last_user_scan > self._user_scan_interval:
                user_logs_path = os.path.join(self.knowledge_base_dir, "user_logs")
                
                def _scan_user_logs():
                    cache = []
                    if os.path.exists(user_logs_path):
                        for d in os.scandir(user_logs_path):
                            if d.is_dir() and "_" in d.name:
                                u_name = d.name.rsplit("_", 1)[0].replace("_", " ")
                                cache.append(u_name)
                    return cache
                
                self._known_users_cache = await asyncio.to_thread(_scan_user_logs)
                self._last_user_scan = time.time()
            
            known_users = self._known_users_cache
            detected_user = next((u for u in known_users if u.lower() in query_lower), None)
            
            # --- SUMMARIZATION SPECIAL LOGIC ---
            # If strategy is SUMMARIZATION, we want to find the SPECIFIC file and retrieve ALL chunks.
            if strategy == "SUMMARIZATION":
                target_file_path = None
                best_match_score = 0
                
                # 1. Identify the target file from query
                # Scan indexed files for name match
                query_cleaned = query_lower.replace("summarize", "").replace("summary of", "").strip()
                # Remove common stopwords for cleaner token matching
                stopwords = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "for", "with", "on", "at", "by", "from", "you", "have", "kaia"}
                query_tokens = set(re.findall(r'\w+', query_cleaned)) - stopwords
                
                for path, mtime in self.indexed_files.items():
                    fname = os.path.basename(path).lower()
                    fname_no_ext = os.path.splitext(fname)[0]
                    fname_tokens = set(re.findall(r'\w+', fname_no_ext)) - stopwords
                    
                    if not fname_tokens: continue
                    
                    # Exact containment of cleaned query in filename (or vice versa) is prime
                    if query_cleaned and (query_cleaned in fname or fname_no_ext in query_cleaned):
                        score = 1.0 # Highest possible
                        if score > best_match_score:
                            best_match_score = score
                            target_file_path = path
                            continue
                    
                    # Fallback: Keyword intersection
                    common_tokens = query_tokens.intersection(fname_tokens)
                    if len(common_tokens) >= 2: # At least 2 meaningful words match
                        # Score is % of FILENAME words found in the query
                        # (We want to find the file mentioned in the query)
                        fname_coverage = len(common_tokens) / len(fname_tokens)
                        
                        if fname_coverage > 0.5: # If >50% of filename words appear in query
                            score = fname_coverage 
                            if score > best_match_score:
                                best_match_score = score
                                target_file_path = path

                if target_file_path:
                    log_action(f"Summarization target identified: {target_file_path}")
                    # Retrieve ALL nodes for this file from the appropriate index
                    # Find which index contains this file
                    target_nodes = []
                    for itype, index in self.indices.items():
                        all_docs = list(index.docstore.docs.values())
                        file_nodes = [
                            n for n in all_docs 
                            if n.metadata.get('file_path') == target_file_path or 
                               os.path.abspath(n.metadata.get('file_path', '')) == os.path.abspath(target_file_path)
                        ]
                        if file_nodes:
                            # Found the file! Sort by chunk index if available to maintain order
                            file_nodes.sort(key=lambda x: x.metadata.get('chunk_index', 0))
                            target_nodes.extend(file_nodes)
                            break # Assume file is in only one index
                    
                    if target_nodes:
                        from utils.core.rag_utils import get_node_text, get_node_metadata
                        log_success(f"Retrieved {len(target_nodes)} full-document nodes for summarization.")
                        return [{
                            "content": get_node_text(node),
                            "metadata": get_node_metadata(node),
                            "label": f"Full Content: {os.path.basename(target_file_path)}",
                            "score": 1.0 # Force high score
                        } for node in target_nodes]
            # -----------------------------------

            # 2. QUERY ENRICHMENT & ID MAPPING
            # Extract Discord IDs: <@123456789> or <@!123456789>
            id_mentions = re.findall(r"<@!?(\d+)>", query)
            mapped_names = []
            
            if id_mentions:
                user_logs_path = os.path.join(self.knowledge_base_dir, "user_logs")
                if os.path.exists(user_logs_path):
                    # Cache directory scan for mapping
                    for d in os.scandir(user_logs_path):
                        if d.is_dir() and "_" in d.name:
                            name_part, id_part = d.name.rsplit("_", 1)
                            if id_part in id_mentions:
                                mapped_names.append(name_part.replace("_", " "))
            
            enriched_query = query
            if mapped_names:
                enriched_query += " " + " ".join(mapped_names)
                
            if user_name and (is_casual or is_social_identity):
                enriched_query = f"{enriched_query} user:{user_name} {user_name}"
            
            if detected_user:
                enriched_query += f" user:{detected_user} {detected_user}"
            
            # 3. ROUTING: Determine target indices
            # 3. ROUTING: Strict Index Targeting (User Request)
            target_itypes = []
            
            # IDENTITY / PRECISE RECALL -> Knowledge + Logs + Profiles
            # "Who is Thorne?" -> Entity search across all memory types
            if is_kaia_query or strategy == "PRECISE_RECALL" or is_entity_query:
                target_itypes = ['knowledge', 'logs', 'user_profiles']
                
            # TECH / DIAGNOSTIC -> Logs ONLY
            # "Error logs", "Status", "Restart" -> Operational data
            elif strategy == "DIAGNOSTIC_DEEP_DIVE":
                target_itypes = ['logs']
                retrieve_count = 15
                
            # DREAMS -> Dreams Index ONLY
            # "What did you dream?" -> Specific dream file storage
            elif strategy == "DREAM_RECALL" or is_dream_query:
                target_itypes = ['dreams']
                retrieve_count = 10

            # CREATIVE / GENERAL -> Knowledge ONLY
            # "Explain transformers", "Tell me about AI" -> Documents
            elif strategy == "CREATIVE_ASSOCIATION":
                target_itypes = ['knowledge']

            # CASUAL / SOCIAL -> Profiles + Logs (Richness)
            # "Hi Kaia" -> Chat history + Who they are
            elif strategy == "SOCIAL_GREETING" or is_casual:
                target_itypes = ['user_profiles', 'logs']
                retrieve_count = 10

            # RELATIONAL / SOCIAL IDENTITY -> Profiles + Logs
            # "Who am I?", "Our history"
            elif strategy == "RELATIONAL_MIRROR" or is_social_identity:
                target_itypes = ['user_profiles', 'logs']

            # FALLBACK -> Knowledge (Documents) + Logs
            else:
                target_itypes = ['knowledge', 'logs']
            
            # Use config for retrieval count, with a slight reduction for casual queries
            if not intent and is_casual:
                 retrieve_count = max(5, int(base_top_k * 0.6))
            elif not 'retrieve_count' in locals():
                 retrieve_count = base_top_k
            
            # 4. HIERARCHICAL RETRIEVAL
            all_node_results = []
            
            from utils.infrastructure.gpu.gpu_memory_manager import gpu_memory_manager, GPUTaskPriority
            
            async def perform_hybrid_retrieval(itype):
                try:
                    bm25_retriever = self.bm25_cache.get(itype)
                    if bm25_retriever is None:
                        index_nodes = list(self.indices[itype].storage_context.docstore.docs.values())
                        if index_nodes:
                            bm25_retriever = SimpleBM25Retriever(index_nodes)
                            self.bm25_cache[itype] = bm25_retriever
                    
                    if bm25_retriever:
                        mult = config.rag_base_score_multiplier
                        hybrid = HybridRetriever(self.indices[itype], bm25_retriever, multiplier=mult)
                        return await hybrid.retrieve(enriched_query, top_k=retrieve_count)
                    else:
                        # Fallback to vector-only if BM25 is unavailable
                        retriever = self.indices[itype].as_retriever(similarity_top_k=retrieve_count)
                        return await retriever.aretrieve(enriched_query)
                except Exception as e:
                    log_error(f"Retrieval failed for {itype}: {e}")
                    return []

            # Guarded parallel retrieval
            async def run_all_retrievals():
                tasks = [perform_hybrid_retrieval(itype) for itype in target_itypes if itype in self.indices]
                results = await asyncio.gather(*tasks)
                return [node for sublist in results for node in sublist]

            # Embeddings are forced to CPU in __init__, so we bypass the GPU guard
            # This allows retrieval to run in parallel with generation without contention.
            log_debug(f"Executing CPU-based RAG retrieval: nomic-embed-text")
            all_node_results = await run_all_retrievals()
            
            # 5. DYNAMIC SCORING & FILTERING
            scored_nodes = [] 
            seen_texts = set()
            u_id_str = str(user_id) if user_id else None
            
            # --- IDENTITY EXPANSION ---
            relevant_ids = {u_id_str} if u_id_str else set()
            if u_id_str:
                # Case 1: Discord -> Forum
                fids = registry.get_forum_ids(u_id_str)
                for fid in fids:
                    relevant_ids.add(str(fid))
                    # Add common folder naming convention matches
                    # We don't have the forum name here easily, but we can infer or skip
                    # relevant_ids.add(f"forum_{user_name}_{fid}") 
                    
                # Case 2: Forum -> Discord
                if u_id_str.startswith("forum_"):
                    fid_parts = u_id_str.rsplit("_", 1)
                    if len(fid_parts) > 1 and fid_parts[1].isdigit():
                        did = registry.get_discord_id(int(fid_parts[1]))
                        if did:
                            relevant_ids.add(did)
                elif u_id_str.isdigit() and len(u_id_str) < 15:
                    did = registry.get_discord_id(int(u_id_str))
                    if did:
                        relevant_ids.add(did)
            # --------------------------
            
            from utils.core.rag_utils import get_node_text, get_node_metadata
            for node_result in all_node_results:
                node = node_result.node if hasattr(node_result, 'node') else node_result
                base_raw_score = node_result.score if hasattr(node_result, 'score') else 0.5
                base_score = base_raw_score
                content = get_node_text(node)
                metadata = get_node_metadata(node)
                
                # Deduplication
                content_hash = hash(content[:200])
                if content_hash in seen_texts: continue
                seen_texts.add(content_hash)
                
                # Metadata extraction
                source_type = metadata.get('source_type', 'general')
                file_path = metadata.get('file_path', '')
                node_user_id = str(metadata.get('user_id', ''))
                node_user_name = metadata.get('user_name', 'Unknown')

                # Filter: News (if not requested)
                if not include_news and (source_type == 'news' or "news" in file_path.lower()):
                    continue
                
                # Filter: Identity Isolation
                if source_type == 'user_profile' and not (is_social_identity or strict_identity):
                    continue
                
                # Filter: User Isolation for Logs
                if source_type == 'user_logs':
                    if node_user_id and node_user_id not in relevant_ids:
                        continue
                    # Also check path just in case user_id is missing from metadata
                    if "user_logs" in file_path:
                        path_parts = file_path.split("/")
                        if "user_logs" in path_parts:
                            idx = path_parts.index("user_logs")
                            if len(path_parts) > idx + 1:
                                folder_name = path_parts[idx+1]
                                # Check if folder belongs to relevant users
                                # relevant_ids contains "Ekco_177011971818782721" etc.
                                is_my_log = any(rid in folder_name for rid in relevant_ids)
                                if not is_my_log:
                                    continue

                # Filter: User Isolation & Hallucination Guard (DECOMMISSIONED for profiles/general)
                # But kept strict for logs above.

                # Filter: Strict Dream Isolation (User Request)
                if is_dream_query:
                    is_dream_source = source_type == 'dream' or "kaia_dreams" in file_path or "dreams" in file_path
                    # Allow content if it explicitly mentions "dream" or comes from a dream source
                    if not is_dream_source and "dream" not in content.lower():
                        continue

                # DYNAMIC SCORING
                # Path boost (explicit mentions)
                path_boost = 0.0
                if file_path:
                    fname = os.path.basename(file_path).lower()
                    if len(fname) > 8 and fname in query_lower:
                        path_boost = config.rag_path_boost if hasattr(config, 'rag_path_boost') else 0.5
                
                # Type boosts
                # Use config values or fallback to defaults if not present (migration safety)
                type_boosts = getattr(config, 'rag_type_boosts', {
                    'persona': 0.15,
                    'user_profile': 0.20,
                    'dream': 0.10,
                    'user_logs': 0.25
                })
                type_boost = type_boosts.get(source_type, 0.0)

                # Final score composition
                final_score = base_score + path_boost + type_boost
                
                # Contextual Boosts & Strategy Adjustments
                if intent:
                    strategy = intent.suggested_strategy
                    
                    # PRECISE_RECALL: Boost exact matches and knowledge
                    if strategy == "PRECISE_RECALL":
                        if source_type in ['knowledge', 'user_profile']:
                            final_score += 0.15
                        # Penalize fuzzy/associative content slightly
                        if source_type == 'dream':
                            final_score -= 0.1
                            
                    # DIAGNOSTIC_DEEP_DIVE: Boost error logs
                    elif strategy == "DIAGNOSTIC_DEEP_DIVE":
                        if source_type == 'user_logs':
                            # Heavy boost for logs containing error keywords
                            if any(w in content.lower() for w in ['error', 'exception', 'traceback', 'fail', 'bug']):
                                final_score += 0.4
                            else:
                                final_score += 0.1
                        # Lower threshold for diagnostic queries to catch obscure errors
                        
                    elif strategy == "DREAM_RECALL":
                        # STRICTLY boost dream files
                        if source_type == 'dream' or "kaia_dreams" in file_path:
                            final_score += 0.5  # Massive boost for genuine dream logs
                        else:
                            final_score -= 0.1  # Penalize non-dream content slightly
                            
                    elif strategy == "CREATIVE_ASSOCIATION":
                         # Loose associations, lower threshold
                         # Encourage diversity but don't prioritize dreams unless relevant
                         if source_type == 'dream':
                             final_score -= 0.05 # Slight penalty to avoid dream spam
                         pass
                            
                    # RELATIONAL_MIRROR: Boost user interaction history
                    elif strategy == "RELATIONAL_MIRROR":
                        if source_type == 'user_profile':
                            final_score += 0.4
                        elif source_type == 'user_logs' and node_user_id in relevant_ids:
                            final_score += 0.25

                else:
                    # Legacy Contextual Boosts (Fallback)
                    if is_dream_query and source_type == 'dream':
                        final_score += 0.3
                    if is_social_identity and source_type == 'user_profile':
                        final_score += 0.3
                
                # DYNAMIC THRESHOLDING (User Request: Simple & Rigid)
                if strategy == "DREAM_RECALL":
                    min_threshold = 0.40 # Low threshold to ensure fragment recall
                elif strategy == "SOCIAL_GREETING" or is_casual:
                    min_threshold = config.rag_threshold_knowledge + config.rag_threshold_casual_penalty
                else:
                    min_threshold = config.rag_threshold_knowledge

                if final_score < min_threshold:
                    continue

                # Generate label
                label = f"Knowledge [{os.path.basename(file_path)}]"
                if source_type == "persona": label = "Kaia Persona Fragment"
                elif "profile" in file_path: label = f"Profile: {node_user_name}"
                elif "user_logs" in file_path: label = f"Log: {node_user_name}"
                
                scored_nodes.append({
                    "content": content,
                    "metadata": metadata, # Already extracted via get_node_metadata(node)
                    "label": label,
                    "score": final_score
                })
            
            # 6. DE-DOGSHITTED SORT & LIMIT
            scored_nodes.sort(key=lambda x: x["score"], reverse=True)
            results = scored_nodes[:top_k]
            
            if results:
                log_success(f"RAG retrieved {len(results)} nodes for query (category: {category})")
            else:
                log_debug(f"RAG: No relevant nodes found for query (category: {category})")
                
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
                        # Exclude vision responses as they are very long and specific
                        from utils.core.rag_utils import get_node_metadata, get_node_text
                        meta = get_node_metadata(node)
                        if not meta.get('is_vision_response'):
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
                    m = get_node_metadata(node)
                    if not m.get('is_vision_response'):
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


    @thread_safe_rag_operation
    async def persist_async(self, force: bool = False):
        """Async wrapper for persist."""
        await asyncio.to_thread(self.persist, force)

    def persist(self, force: bool = False):
        """Persist all hierarchical indices to storage if needed."""
        # REQUIREMENT: Never wait on locks during shutdown
        if not force and not self.persist_needed:
            return
            
        log_action("Persisting all RAG indices...")
        if not os.path.exists(self.persist_dir):
            os.makedirs(self.persist_dir)
            
        for itype, index in self.indices.items():
            try:
                itype_dir = os.path.join(self.persist_dir, itype)
                temp_dir = f"{itype_dir}_tmp"
                
                # 1. Clean up stale temp dir if it exists
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                
                # 2. Persist to temporary location
                index.storage_context.persist(persist_dir=temp_dir)
                
                # 3. Atomic swap (near-atomic on most filesystems)
                old_dir = f"{itype_dir}_old"
                if os.path.exists(old_dir):
                    shutil.rmtree(old_dir)
                
                if os.path.exists(itype_dir):
                    os.rename(itype_dir, old_dir)
                
                os.rename(temp_dir, itype_dir)
                
                if os.path.exists(old_dir):
                    shutil.rmtree(old_dir)
                    
            except Exception as e:
                log_error(f"Failed to persist {itype} index: {e}")
        
        self.persist_needed = False
        log_success("RAG indices persisted.")

    def pre_warm(self):
        """
        Should be called in a background thread on startup.
        Optimized to avoid 30GB RAM spikes by serializing and checking resources.
        """
        try:
            import psutil
            import gc
            
            log_action("Pre-warming RAG BM25 indices...")
            # Use local copy of indices keys to avoid concurrent mod
            index_list = list(self.indices.items())
            
            for itype, index in index_list:
                # 1. Resource Guard: Check available system RAM
                avail_mem_gb = psutil.virtual_memory().available / (1024**3)
                if avail_mem_gb < 2.0:
                    log_warning(f"Extreme low RAM ({avail_mem_gb:.1f}GB). Skipping pre-warm for index '{itype}' to prevent crash.")
                    continue

                # 2. Quick check with lock
                with self._lock:
                    if itype in self.bm25_cache and self.bm25_cache[itype] is not None:
                        continue
                    # Get nodes while holding lock
                    nodes = list(index.storage_context.docstore.docs.values())
                
                if nodes:
                    log_debug(f"Tokenizing {len(nodes)} nodes for '{itype}' index (background)...")
                    start = time.time()
                    
                    # 3. HEAVY WORK: Tokenize and build BM25 WITHOUT holding the lock
                    # This allows other threads (like retrieval) to proceed
                    retriever = SimpleBM25Retriever(nodes)
                    
                    # 4. Final update with lock
                    with self._lock:
                        self.bm25_cache[itype] = retriever
                        
                    # 5. AGGRESSIVE CLEANUP: Force garbage collection after each index
                    gc.collect() 
                    
                    log_success(f"Index '{itype}' pre-warmed in {time.time() - start:.2f}s")
                    
                    # Brief breath between indices to keep CPU and RAM pressure sane
                    time.sleep(1.0)
            
            log_success("All RAG indices pre-warmed.")
        except Exception as e:
            log_error(f"RAG pre-warm failed: {e}")

if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
