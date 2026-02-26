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
import json
import heapq
import copy

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
    
    # Strip <think>...</think> reasoning blocks from new reasoning models (like Qwen 3.5)
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL)
    
    # Clean up resulting double spaces
    clean = re.sub(r'  +', ' ', clean)
    
    return clean.strip()

# HallucinationDetector moved to dedicated module
from utils.core.hallucination_detector import HallucinationDetector



class SimpleBM25Retriever:
    """BM25 retriever with async initialization and lazy tokenization."""
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
            tokenized = [self._tokenize(get_node_text(node)) for node in self.nodes]
            bm25 = BM25Okapi(tokenized) if tokenized else None
            return tokenized, bm25

        self._tokenized_docs, self.bm25 = await asyncio.to_thread(_build_bm25)
        # We KEEP self.nodes because we need to return them in retrieve()
        # but we no longer need to perform the heavy tokenization in the main thread.
        log_debug(f"BM25 initialized in background with {len(self.nodes)} nodes.")

    def _tokenize(self, text: str) -> List[str]:
        return re.sub(r"[^\w\s]", " ", text.lower()).split()

    def retrieve(self, query: str, top_k: int = 10):
        """Retrieve top_k nodes using BM25, building synchronously if not yet initialized."""
        if self.bm25 is None:
            with self._lock:
                if self.bm25 is None:
                    from utils.core.rag_utils import get_node_text
                    tokenized = [self._tokenize(get_node_text(node)) for node in self.nodes]
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
            node_id = node_with_score.node.node_id
            node_map[node_id] = node_with_score.node
            combined_scores[node_id] = combined_scores.get(node_id, 0) + alpha / (rank + 60)

        # BM25 RRF
        for rank, (node, _) in enumerate(bm25_results):
            node_id = node.node_id
            node_map[node_id] = node
            combined_scores[node_id] = combined_scores.get(node_id, 0) + (1 - alpha) / (rank + 60)

        # 4. Efficient top_k selection via heapq
        top_items = heapq.nlargest(top_k, combined_scores.items(), key=lambda x: x[1])
        
        return [NodeWithScore(node=node_map[nid], score=float(score * self.multiplier)) for nid, score in top_items]



def thread_safe_rag_operation(func):
    """Decorator to ensure thread safety for RAG operations."""
    import inspect
    is_async = inspect.iscoroutinefunction(func)

    @wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        lock_timeout = getattr(config, 'rag_lock_seconds', 10.0)
        
        if func.__name__ == 'retrieve':
            # retrieval_lock allows parallel reads if implemented later, 
            # for now we use data_lock but with short timeouts.
            acquired = await asyncio.to_thread(self._data_lock.acquire, timeout=0.5)
            try:
                if not acquired:
                    log_warning("RAG retrieval lock contention - proceeding with best-effort access")
                return await func(self, *args, **kwargs)
            finally:
                if acquired: self._data_lock.release()
        else:
            # Writes/updates
            if not await asyncio.to_thread(self._data_lock.acquire, timeout=lock_timeout):
                log_warning(f"RAG operation {func.__name__} timed out waiting for data lock")
                return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
            try:
                return await func(self, *args, **kwargs)
            finally:
                self._data_lock.release()

    @wraps(func)
    def sync_wrapper(self, *args, **kwargs):
        from utils.infrastructure.system.yaml_config import config
        lock_timeout = getattr(config, 'rag_lock_seconds', 10.0)
        
        if func.__name__ == 'retrieve':
            acquired = self._data_lock.acquire(timeout=0.5)
            try:
                return func(self, *args, **kwargs)
            finally:
                if acquired: self._data_lock.release()
        else:
            if not self._data_lock.acquire(timeout=lock_timeout):
                return False if func.__name__ in ['add_memory', 'log_user_interaction'] else None
            try:
                return func(self, *args, **kwargs)
            finally:
                self._data_lock.release()

    return async_wrapper if is_async else sync_wrapper

class KaiaRAG:
    def __init__(self, knowledge_base_dir="./knowledge_base", persist_dir="./memory/rag_storage"):
        self.knowledge_base_dir = knowledge_base_dir
        self.persist_dir = persist_dir
        self.indexed_files = {}  # Manifest: {path: {"mtime": mtime, "size": size, "nodes": [node_ids]}}
        self._file_to_nodes = {} # Inverse index for fast deletion/update
        
        # Configure Ollama Embedding
        # Force CPU for embeddings to save VRAM for the main 12b model
        self.embed_model = OllamaEmbedding(
            model_name=config.embedding_model,
            base_url="http://localhost:11434",
            query_instruction=config.rag_query_instruction,
            text_instruction=config.rag_text_instruction,
            # Force CPU for embeddings to save VRAM for the main 12b model
            ollama_additional_kwargs={
                "num_gpu": 0,
                "num_thread": 4,
                "num_ctx": config.embedding_context_tokens
            },
            client_kwargs={"timeout": config.embedding_request_seconds}
        )
        
        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.node_parser = SentenceSplitter(
            chunk_size=config.rag_node_chunk_size, 
            chunk_overlap=config.rag_node_chunk_overlap
        )
        
        # Pre-load NLTK data to prevent LazyCorpusLoader thread-safety issues
        # when running get_nodes_from_documents in parallel later.
        try:
            import nltk
            from nltk.corpus import stopwords
            # Ensure it is downloaded and loaded into memory on the main thread
            nltk.download('stopwords', quiet=True)
            nltk.download('punkt', quiet=True)
            nltk.download('punkt_tab', quiet=True)
            stopwords.ensure_loaded()
        except Exception as e:
            log_warning(f"Failed to pre-load NLTK data: {e}")
        
        # RAG uses the chat model for query synthesis. We deliberately DO NOT 
        # set `num_gpu: 0` here. If we did, LlamaIndex would pass that option 
        # to Ollama during runtime queries, forcing the main model to be evicted 
        # from VRAM back to system RAM to satisfy the request.
        # 
        # Construction is I/O-free and safe because LlamaIndex's Ollama() wrapper
        # doesn't call out to the engine until the first query is actually sent
        # (which happens well after the Phase 1 GPU lock is established).
        #
        # WARNING: Do NOT use OllamaGPUManager here — it probes Ollama and can trigger
        # VRAM allocation before the Phase 1 GPU lock has been established.
        llm_timeout = getattr(config, 'llm_request_seconds', 360.0)
        Settings.llm = Ollama(
            model=config.chat_model,
            request_timeout=llm_timeout
        )
        
        # Lazy load indices for faster startup
        self.indices = {} # Hierarchical indices
        self.bm25_cache = {} # Cache for BM25 retrievers {itype: (timestamp, retriever)}
        self.persist_needed = False
        self._data_lock = threading.Lock()  # Granular data access (retrieval vs insertion)
        self._index_lock = threading.Lock() # Higher-level maintenance lock
        self.state_file = os.path.join(self.persist_dir, "file_manifest.json")
        # NOTE: _load_indexed_files() is intentionally NOT called here.
        # It performs disk I/O and must not run during Phase 0 (synchronous boot).
        # It is called inside initialize_async() which runs in Phase 3 via asyncio.to_thread().
        self.indexed_files = {}
        
        # Performance Cache: Rolling Recent Files
        self._recent_files_cache = []
        self._last_recent_scan = 0
        self._known_users_cache = []
        self._last_user_scan = 0

        self._user_scan_interval = getattr(config, 'rag_user_scan_interval', 300)
        self._indexing_in_progress = False
        self._indexing_in_progress = False
        self._refresh_pending = False # Single-flight "dirty" flag
        self._bot_user_id = None # Set by Discord bot on startup
        self._initialized = False

        # Audit flag system: caches from the most recent retrieve() call
        self._last_retrieval_node_ids = []   # Node IDs from the last retrieval
        self._last_retrieval_results = []    # Full scored results from the last retrieval

    async def initialize_async(self):
        """Asynchronously initialize hierarchical indices."""
        if self._initialized: return
        log_action("Initializing RAG indices in background...")

        # Step 1: Load manifest from disk (I/O — runs in thread, safe in Phase 3)
        await asyncio.to_thread(self._load_indexed_files)

        # Step 2: Load or create vector indices (CPU-bound, may trigger embeddings)
        # Embeddings are forced to CPU via num_gpu: 0 in OllamaEmbedding above.
        await asyncio.to_thread(self._initialize_indices)
        
        self._initialized = True
        log_success("RAG indices initialized.")

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

    def _save_bm25_cache(self, itype: str):
        """Persists the SimpleBM25Retriever to disk using pickle."""
        import pickle
        with self._data_lock:
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
                    # We can't perfectly filter by itype easily here, so we invalidate 
                    # if ANY file in the manifest is newer than the cache cache
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

        
        # Add garbage detection metadata
        if self.is_garbage_text(doc.text):
            doc.metadata["priority"] = 0.0
            doc.metadata["source_type"] = "garbage"
            doc.metadata["garbage"] = True

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
        count_added = 0
        for abs_path, node_ids in self._file_to_nodes.items():
            if abs_path not in self.indexed_files:
                if os.path.exists(abs_path):
                    mtime = os.path.getmtime(abs_path)
                    size = os.path.getsize(abs_path)
                    self.indexed_files[abs_path] = {
                        "mtime": mtime,
                        "size": size,
                        "nodes": node_ids
                    }
                    count_added += 1
            else:
                # Sync nodes in manifest
                self.indexed_files[abs_path]["nodes"] = node_ids

        log_success(f"RAG State: {len(self.indexed_files)} files in manifest ({count_added} newly discovered).")
        self._save_indexed_files()

    def _prune_deleted_files(self) -> Set[str]:
        """Detect and remove files from indices that no longer exist on disk using manifest."""
        updated_itypes = set()
        deleted_files = [p for p in list(self.indexed_files.keys()) if not os.path.exists(p)]
        if not deleted_files:
            return updated_itypes
            
        log_action(f"Detected {len(deleted_files)} deleted files. Pruning index O(k)...")
        with self._data_lock: # Lock for modifying indexed_files and indices
            for file_path in deleted_files:
                # O(k) deletion using manifest nodes
                node_ids = self.indexed_files[file_path].get("nodes", [])
                log_info(f"Pruning {len(node_ids)} nodes for deleted file: {os.path.basename(file_path)}")
                
                for itype, index in self.indices.items():
                    # Filter nodes that belong to this index (or just try/except delete)
                    # itype is usually in metadata if we want to be precise
                    try:
                        index.delete_nodes(node_ids)
                        updated_itypes.add(itype)
                    except Exception: pass
                
                self.indexed_files.pop(file_path, None)
                self._file_to_nodes.pop(file_path, None)
            
        self._save_indexed_files()
        return updated_itypes

    def _save_indexed_files(self):
        """Persist the mapping of indexed files to disk."""
        try:
            if not os.path.exists(self.persist_dir):
                os.makedirs(self.persist_dir)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.indexed_files, f, indent=4)
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
            if "corrupt_files" in root: continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in supported_exts:
                    full_path = os.path.join(root, file)
                    norm_path = os.path.abspath(full_path)
                    mtime = os.path.getmtime(norm_path)
                    
                    itype = 'knowledge'
                    if "user_logs" in full_path:
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
        persona_file = "knowledge_base/kaia_persona.md"
        if os.path.exists(persona_file):
            norm_path = os.path.abspath(persona_file)
            mtime = os.path.getmtime(norm_path)
            entry = self.indexed_files.get(norm_path)
            if entry is None or mtime > entry.get("mtime", 0):
                new_file_paths.append((persona_file, entry is not None, False, 'persona'))
        
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
                "nodes": entry.get("nodes", []) if entry else []
            }
            return False
            
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(last_offset)
            new_content = f.read()
            
        if not new_content.strip():
            mtime = os.path.getmtime(file_path)
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": os.path.getsize(file_path),
                "nodes": entry.get("nodes", []) if entry else []
            }
            return False

        mtime = os.path.getmtime(file_path)
        doc = Document(text=new_content, metadata={
            "file_path": abs_path, "last_modified_at": mtime,
            "file_offset": last_offset, "content_length": len(new_content), "source": "user_logs"
        })
        self._apply_priority_metadata(doc, itype, file_path)
        nodes = self._get_node_parser_for_doc(itype, file_path).get_nodes_from_documents([doc])
        with self._data_lock: # Lock for modifying indices and manifest
            target_index.insert_nodes(nodes)
            
            # Update manifest
            node_ids = [n.node_id for n in nodes]
            existing_nodes = entry.get("nodes", []) if entry else []
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": os.path.getsize(file_path),
                "nodes": list(set(existing_nodes + node_ids))
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
        with self._data_lock: # Lock for modifying indices and manifest
            for doc in docs:
                doc.metadata.update({'last_modified_at': mtime, 'file_path': abs_path, 'itype': itype})
                self._apply_priority_metadata(doc, itype, file_path)
                if itype == 'persona': doc.metadata['user_id'] = "KAIA_SYSTEM"
                
                # ... (user metadata logic) ...
                
                for sub_doc in self._pre_chunk_document(doc):
                    # self._apply_priority_metadata(sub_doc, itype, file_path) # Duplicate call removed
                    nodes = parser.get_nodes_from_documents([sub_doc])
                    self.indices[itype].insert_nodes(nodes)
                    all_node_ids.extend([n.node_id for n in nodes])
            
            self.indexed_files[abs_path] = {
                "mtime": mtime,
                "size": os.path.getsize(file_path),
                "nodes": all_node_ids
            }
            self._file_to_nodes[abs_path] = all_node_ids
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
                            self.indexed_files[os.path.abspath(md_path)] = mtime
                            self.indexed_files[os.path.abspath(file_path)] = os.path.getmtime(file_path)
                        return True
                except Exception: pass
        
        # Move to corrupt
        dest = os.path.join(corrupt_dir, os.path.basename(file_path))
        if os.path.exists(dest): dest = f"{dest}_{int(time.time())}"
        import shutil
        shutil.move(file_path, dest)
        log_critical(f"MOVED CORRUPT FILE TO: {dest}")
        return False

    def _persist_updated_indices(self, updated_itypes: Set[str]):
        """Save indices to disk and invalidate/save BM25 cache."""
        self.persist_needed = True
        with self._data_lock: # Lock for modifying bm25_cache and indices
            for itype in updated_itypes:
                if itype in self.bm25_cache:
                    log_info(f"Invalidating memory BM25 cache for '{itype}' to trigger re-save")
                    # Ensure we re-build/re-save the BM25 for this type if it changed
                try:
                    self.indices[itype].storage_context.persist(persist_dir=os.path.join(self.persist_dir, itype))
                    log_success(f"Index '{itype}' persisted.")
                    # Also persist BM25 if already in memory
                    if itype in self.bm25_cache and self.bm25_cache[itype]:
                        self._save_bm25_cache(itype)
                except Exception as e: log_error(f"Failed to persist {itype}: {e}")
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
                results = await asyncio.gather(*tasks)
                
                # Track updated types
                for itype in results:
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
            self._docx_breaker = CircuitBreaker("docx_convert", failure_threshold=3, reset_timeout=60)
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
            with self._data_lock:
                safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
                user_dir_name = f"{safe_user_name}_{user_id}"
                user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
                
                os.makedirs(user_log_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                log_file = os.path.join(user_log_dir, f"injected_{timestamp}.txt")
                
                log_text = f"User ({user_name}): Remember this: {text}\nKaia: Logged it. I'll remember that.\n"
                
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write(log_text)
                    
                log_success(f"Separate memory file created: injected_{timestamp}.txt")
                return True
                
        except Exception as e:
            log_error(f"Error adding memory: {e}")
            return False

    async def log_user_interaction_async(self, user_id: int, user_name: str, message_content: str, bot_response: str) -> bool:
        """Async wrapper for log_user_interaction."""
        return await asyncio.to_thread(self.log_user_interaction, user_id, user_name, message_content, bot_response)

    # Removed @thread_safe_rag_operation to ensure file writing always happens
    def log_user_interaction(self, user_id: int, user_name: str, message_content: str, bot_response: str) -> bool:
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
        with self._data_lock:
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
                
                # CLEAN HALLUCINATIONS FROM RESPONSE BEFORE LOGGING (Skip for Owners)
                if HallucinationDetector.contains_hallucination(bot_response):
                    if not config.is_owner(user_name, user_id=str(user_id)):
                        log_warning(f"Hallucination detected in response for {user_name}. Cleaning before logging.")
                        bot_response = HallucinationDetector.clean_response(bot_response)
                    else:
                        log_debug(f"Hallucination pattern detected in owner response ({user_name}), but skipping clean.")

                # BUG 1 FIX: Strip JSON wrapper from response before logging
                json_wrapper_pattern = r'^\s*\{[\s\S]*"response"\s*:\s*"([\s\S]*)"\s*\}\s*$'
                match = re.search(json_wrapper_pattern, bot_response)
                if match:
                    bot_response = match.group(1).replace('\\"', '"').replace('\\n', '\n')

                # Initialize frontmatter if file is new
                is_new_file = not os.path.exists(interaction_log_path)
                
                header_text = ""
                if is_new_file:
                    header_text = "---\nsummary: \"\"\nkeywords: []\ndocument_type: Transcript\n---\n\n"
                
                # Sanitize internal tags before logging to prevent RAG pollution
                message_content = sanitize_log_content(message_content)
                bot_response = sanitize_log_content(bot_response)
                
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
        
        query_cleaned = query_lower.replace("summarize", "").replace("summary of", "").strip()
        stopwords = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "for", "with", "on", "at", "by", "from", "you", "have", "kaia"}
        query_tokens = set(re.findall(r'\w+', query_cleaned)) - stopwords
        
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
            
            common_tokens = query_tokens.intersection(fname_tokens)
            if len(common_tokens) >= 2:
                fname_coverage = len(common_tokens) / len(fname_tokens)
                if fname_coverage > 0.5:
                    score = fname_coverage 
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
                    with self._data_lock:
                        self.bm25_cache[itype] = bm25_retriever
                else:
                    # Cold start rebuild
                    index_nodes = list(index.storage_context.docstore.docs.values())
                    if index_nodes:
                        # Offload the potentially heavy BM25 initialization (tokenization of all nodes)
                        bm25_retriever = await asyncio.to_thread(SimpleBM25Retriever, index_nodes)
                        with self._data_lock: # Lock for modifying bm25_cache
                            self.bm25_cache[itype] = bm25_retriever
                        # Trigger save for next time
                        await asyncio.to_thread(self._save_bm25_cache, itype)
            
            if bm25_retriever:
                from utils.infrastructure.system.yaml_config import config
                hybrid = HybridRetriever(self.indices[itype], bm25_retriever, multiplier=config.rag_base_score_multiplier)
                return await hybrid.retrieve(query, top_k=retrieve_count)
            else:
                retriever = self.indices[itype].as_retriever(similarity_top_k=retrieve_count)
                return await retriever.aretrieve(query)
        except Exception as e:
            log_error(f"Retrieval failed for {itype}: {e}")
            return []

    def _resolve_identity_mappings(self, user_id: Any) -> Set[str]:
        """Resolve all linked identities (Discord/Forum) for a given user ID."""
        try:
            from utils.social.identity_registry import registry
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
        seen_texts = set()
        strategy = routing["strategy"]
        is_casual = routing["is_casual"]
        is_dream_query = routing["is_dream_query"]
        is_social_identity = routing["is_social_identity"]

        for node_result in all_node_results:
            node = node_result.node if hasattr(node_result, 'node') else node_result
            base_score = node_result.score if hasattr(node_result, 'score') else 0.5
            
            content = get_node_text(node)
            if not content: continue
            content_hash = hash(content[:200])
            if content_hash in seen_texts: continue
            seen_texts.add(content_hash)
            
            metadata = get_node_metadata(node)
            source_type = metadata.get('source_type', 'general')
            file_path = metadata.get('file_path', '')
            node_user_id = str(metadata.get('user_id', ''))
            
            # FILTERS
            if not include_news and (source_type == 'news' or "news" in file_path.lower()): continue
            if source_type == 'user_profile' and (not (is_social_identity or strict_identity) or (node_user_id and node_user_id not in relevant_ids)): continue
            if source_type == 'user_logs' and node_user_id and node_user_id not in relevant_ids: continue
            if is_dream_query and not (source_type == 'dream' or "kaia_dreams" in file_path or "dream" in content.lower()): continue

            # SCORING
            path_boost = 0.5 if file_path and len(os.path.basename(file_path)) > 8 and os.path.basename(file_path).lower() in query_lower else 0
            type_boosts = getattr(config, 'rag_type_boosts', {'persona': 0.15, 'user_profile': 0.20, 'dream': 0.10, 'user_logs': 0.25})
            type_boost = type_boosts.get(source_type, 0.0)
            
            final_score = base_score + path_boost + type_boost

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

            # THRESHOLDING
            min_threshold = 0.40 if strategy == "DREAM_RECALL" else (config.rag_threshold_knowledge + (config.rag_threshold_casual_penalty if is_casual else 0))
            if final_score < min_threshold: continue

            # LABELING
            label = f"Knowledge [{os.path.basename(file_path)}]"
            if source_type == "persona": label = "Kaia Persona Fragment"
            elif source_type == "user_profile": label = f"Profile: {metadata.get('user_name', 'Unknown')}"
            elif source_type == "user_logs": label = f"Log: {metadata.get('user_name', 'Unknown')}"
            
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
            all_results = await asyncio.gather(*tasks)
            all_node_results = [node for sublist in all_results for node in sublist]
            
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

    @thread_safe_rag_operation
    async def detect_hallucination(self, bot_response: str, context_text: Optional[str] = None) -> Dict[str, Any]:
        """Detect potential hallucinations in a bot response."""
        detector = HallucinationDetector()
        has_hallucination = detector.contains_hallucination(bot_response)
        
        return {
            "has_hallucination": has_hallucination,
            "patterns_detected": has_hallucination,
            "cleaned_response": detector.clean_response(bot_response) if has_hallucination else bot_response
        }


    def flag_nodes(self, node_ids: list, construct_name: str) -> int:
        """Flag nodes with a Data Rot construct label. Returns count of nodes flagged."""
        flagged = 0
        with self._data_lock: # Lock for modifying indices
            for itype, index in self.indices.items():
                docstore = index.storage_context.docstore
                for node_id in node_ids:
                    try:
                        node = docstore.get_node(node_id)
                        if node:
                            if 'audit_flags' not in node.metadata:
                                node.metadata['audit_flags'] = []
                            # Avoid duplicate flags of the same construct
                            if construct_name not in node.metadata['audit_flags']:
                                node.metadata['audit_flags'].append(construct_name)
                                flagged += 1
                    except Exception:
                        continue
            if flagged:
                self.persist_needed = True
        # Persist outside the lock
        if flagged:
            self.persist(force=True)
        return flagged

    def get_audit_summary(self) -> dict:
        """Scan all nodes for audit_flags metadata and return summary statistics."""
        from collections import Counter
        total_flagged = 0
        construct_counts = Counter()
        source_counts = Counter()

        with self._data_lock: # Lock for reading indices
            for itype, index in self.indices.items():
                docstore = index.storage_context.docstore
                for node in docstore.docs.values():
                    flags = node.metadata.get('audit_flags', [])
                    if flags:
                        total_flagged += 1
                        for flag in flags:
                            construct_counts[flag] += 1
                        file_path = node.metadata.get('file_path', 'unknown')
                        source_counts[file_path] += 1

        return {
            "total_flagged": total_flagged,
            "by_construct": dict(construct_counts),
            "top_sources": source_counts.most_common(10),
        }

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
            
        with self._data_lock: # Lock for modifying indices
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

    async def pre_warm(self):
        """
        Warms up individual BM25 retrievers asynchronously.
        Replaces raw nodes with tokenized structures to save RAM.
        """
        try:
            import psutil
            import gc
            
            log_action("Pre-warming RAG BM25 indices (Async)...")
            index_list = list(self.indices.items())
            
            for itype, index in index_list:
                # 1. Resource Guard
                avail_mem_gb = psutil.virtual_memory().available / (1024**3)
                if avail_mem_gb < 1.0: # Lowered threshold slightly due to better efficiency
                    log_warning(f"Low RAM ({avail_mem_gb:.1f}GB). Skipping pre-warm for '{itype}'.")
                    continue

                # 2. Check cache (Memory or Disk)
                with self._data_lock:
                    if itype in self.bm25_cache and self.bm25_cache[itype] is not None:
                        continue
                
                # Try loading from disk first
                retriever = await asyncio.to_thread(self._load_bm25_cache, itype)
                
                if not retriever:
                    with self._data_lock:
                        nodes = list(index.storage_context.docstore.docs.values())
                    
                    if nodes:
                        log_debug(f"Async pre-warming '{itype}' ({len(nodes)} nodes) via full build...")
                        start = time.time()
                        
                        # 3. Use the new async-ready retriever
                        retriever = SimpleBM25Retriever(nodes)
                        await retriever.initialize_async()
                        
                        with self._data_lock:
                            self.bm25_cache[itype] = retriever
                            
                        # Persist to disk for faster next start
                        await asyncio.to_thread(self._save_bm25_cache, itype)
                        
                        gc.collect() 
                        log_success(f"Index '{itype}' pre-warmed in {time.time() - start:.2f}s")
                else:
                    # Successfully loaded from disk
                    with self._data_lock:
                        self.bm25_cache[itype] = retriever
                    
                    # Breath between indices
                    await asyncio.sleep(0.5)
            
            log_success("All RAG indices pre-warmed.")
        except Exception as e:
            log_error(f"RAG pre-warm failed: {e}")
            traceback.print_exc()



if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
