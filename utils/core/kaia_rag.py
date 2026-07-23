import os
import re
import asyncio
import time
import shutil
import logging
import warnings
import pypdf
import docx2txt
import threading
import traceback
import json

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
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage, Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter, CodeSplitter
from llama_index.core.schema import NodeWithScore
from utils.infrastructure.logging.kaia_logger import log_success, log_info, log_warning, log_error, log_critical, log_action, log_debug
from utils.infrastructure.system.bot_state import bot_state
from utils.infrastructure.system.yaml_config import config
from utils.core.kaia_intelligence import Intent
from utils.social.kaia_identities import registry

# ── Extracted Retrieval Components (Phase 28 / CQ-01) ────────────────────
from utils.core.kaia_rag_retriever import (                    # noqa: F401
    CircuitOpenError,
    sanitize_log_content,
    SimpleBM25Retriever,
    HybridRetriever,
    thread_safe_rag_operation,
)

from utils.core.hallucination_detector import HallucinationDetector  # noqa: F401


# ── Mixin Modules (Phase 28 / CQ-01 deep split) ─────────────────────────
from utils.core.kaia_rag_indexer import RAGIndexerMixin
from utils.core.kaia_rag_persistence import RAGPersistenceMixin
from utils.core.kaia_rag_query import RAGQueryMixin

class KaiaRAG(RAGIndexerMixin, RAGPersistenceMixin, RAGQueryMixin):
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
        
        # Construction is I/O-free. NLTK pre-loading moved to initialize_async().
        
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
        # [VRAM LOCK]: Build options from config directly to avoid synchronous 
        # OllamaGPUManager instantiation (which triggers slow NVML probing).
        # Ensures internal LLM calls (synthesis, etc) match the main chat model's fingerprint.
        llm_timeout = getattr(config, 'llm_request_seconds', 360.0)
        
        settings_options = {
            'num_gpu': 99,
            'num_thread': getattr(config, 'num_thread', 8),
            'main_gpu': 0,
            'num_ctx': config.max_context_tokens,
            'keep_alive': -1
        }
        
        Settings.llm = Ollama(
            model=config.chat_model,
            request_timeout=llm_timeout,
            context_window=config.max_context_tokens,
            additional_kwargs=settings_options
        )
        
        # Lazy load indices for faster startup
        self.indices = {} # Hierarchical indices
        self.bm25_cache = {} # Cache for BM25 retrievers {itype: (timestamp, retriever)}
        self.persist_needed = False
        self._data_lock = threading.Lock()  # Shared lock for both sync and async paths
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
        self._refresh_pending = False # Single-flight "dirty" flag
        self._bot_user_id = None # Set by Discord bot on startup
        self._initialized = False

        # Context-isolated RAG state storage (🔴-1)
        self._channel_retrieval_results = {}
        self._channel_retrieval_node_ids = {}
        self._channel_retrieval_confidence = {}
        self._channel_retrieval_node_count = {}
        self._channel_retrieval_time = {}
        self._channel_state_lock = threading.Lock()
        self._last_active_channel = "global"

    async def initialize_async(self):
        """Asynchronously initialize hierarchical indices."""
        if self._initialized: return
        log_action("Initializing RAG indices in background...")
        log_info(f"type_boosts active: {getattr(config, 'rag_type_boosts', {})}")

        # Step 0: Pre-load NLTK data (Safe in Phase 3 background)
        await asyncio.to_thread(self._preload_nltk)

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
    def _get_channel_key(self) -> str:
        from utils.core.message_processor import current_channel_id_var
        try:
            channel_id = current_channel_id_var.get()
            if channel_id:
                return str(channel_id)
        except Exception:
            pass
        return "global"

    @property
    def _last_retrieval_results(self) -> List[Any]:
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key == "global" and self._last_active_channel in self._channel_retrieval_results:
                return self._channel_retrieval_results[self._last_active_channel]
            return self._channel_retrieval_results.get(key, [])

    @_last_retrieval_results.setter
    def _last_retrieval_results(self, val: List[Any]):
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key != "global":
                self._last_active_channel = key
            self._channel_retrieval_results[key] = val

    @property
    def _last_retrieval_node_ids(self) -> List[str]:
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key == "global" and self._last_active_channel in self._channel_retrieval_node_ids:
                return self._channel_retrieval_node_ids[self._last_active_channel]
            return self._channel_retrieval_node_ids.get(key, [])

    @_last_retrieval_node_ids.setter
    def _last_retrieval_node_ids(self, val: List[str]):
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key != "global":
                self._last_active_channel = key
            self._channel_retrieval_node_ids[key] = val

    @property
    def _last_retrieval_confidence(self) -> float:
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key in self._channel_retrieval_confidence:
                return self._channel_retrieval_confidence[key]
            if self._last_active_channel in self._channel_retrieval_confidence:
                return self._channel_retrieval_confidence[self._last_active_channel]
            if self._channel_retrieval_confidence:
                return list(self._channel_retrieval_confidence.values())[-1]
            return 0.0

    @_last_retrieval_confidence.setter
    def _last_retrieval_confidence(self, val: float):
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key != "global":
                self._last_active_channel = key
            self._channel_retrieval_confidence[key] = val

    @property
    def _last_retrieval_node_count(self) -> int:
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key in self._channel_retrieval_node_count:
                return self._channel_retrieval_node_count[key]
            if self._last_active_channel in self._channel_retrieval_node_count:
                return self._channel_retrieval_node_count[self._last_active_channel]
            if self._channel_retrieval_node_count:
                return list(self._channel_retrieval_node_count.values())[-1]
            return 0

    @_last_retrieval_node_count.setter
    def _last_retrieval_node_count(self, val: int):
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key != "global":
                self._last_active_channel = key
            self._channel_retrieval_node_count[key] = val

    @property
    def _last_retrieval_time(self) -> float:
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key in self._channel_retrieval_time:
                return self._channel_retrieval_time[key]
            if self._last_active_channel in self._channel_retrieval_time:
                return self._channel_retrieval_time[self._last_active_channel]
            if self._channel_retrieval_time:
                return list(self._channel_retrieval_time.values())[-1]
            return 0.0

    @_last_retrieval_time.setter
    def _last_retrieval_time(self, val: float):
        key = self._get_channel_key()
        with self._channel_state_lock:
            if key != "global":
                self._last_active_channel = key
            self._channel_retrieval_time[key] = val


if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
