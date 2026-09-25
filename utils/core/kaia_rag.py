import os
import asyncio
import logging
import threading
import warnings

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

# Library warnings are noise here — except RuntimeWarning, which is how Python
# reports a coroutine that was never awaited, and must stay visible.
warnings.filterwarnings("ignore")
warnings.filterwarnings("default", category=RuntimeWarning)

from typing import List, Any
from llama_index.core import Settings
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter
from utils.infrastructure.logging.kaia_logger import log_success, log_info, log_action
from utils.infrastructure.system.yaml_config import config

# Re-exported: callers import it from here.
from utils.core.kaia_rag_retriever import sanitize_log_content  # noqa: F401

# ── Mixin modules ───────────────────────────────────────────────────────
from utils.core.kaia_rag_indexer import RAGIndexerMixin
from utils.core.kaia_rag_persistence import RAGPersistenceMixin
from utils.core.kaia_rag_query import RAGQueryMixin

class KaiaRAG(RAGIndexerMixin, RAGPersistenceMixin, RAGQueryMixin):
    def __init__(self, knowledge_base_dir="./knowledge_base", persist_dir="./memory/rag_storage"):
        # Under pytest this becomes `./memory/rag_storage.test`. Without it the
        # suite opened the live index and wrote an empty manifest over it — see
        # `telemetry_paths.persist_dir`.
        from utils.infrastructure.monitoring.telemetry_paths import (
            persist_dir as _resolve_persist_dir)
        persist_dir = _resolve_persist_dir(persist_dir)
        self.knowledge_base_dir = knowledge_base_dir
        self.persist_dir = persist_dir
        self.indexed_files = {}  # Manifest: {path: {"mtime": mtime, "size": size, "nodes": [node_ids]}}
        self._file_to_nodes = {} # Inverse index for fast deletion/update
        
        # Embeddings run on CPU so the chat model keeps the VRAM it is pinned
        # into with keep_alive: -1 — a GPU embed evicts it and every subsequent
        # reply pays a reload.
        #
        # That trade inverts for an offline rebuild, where there is no chat model
        # to protect and the job is tens of thousands of embeddings.
        # `KAIA_EMBED_GPU=1` flips it, and reindex_rag.py sets it automatically
        # when no bot process is running. `nomic-embed-text-cpu` and
        # `nomic-embed-text` are the same weights; placement is decided entirely
        # by num_gpu here.
        _embed_on_gpu = os.getenv("KAIA_EMBED_GPU") == "1"
        if _embed_on_gpu:
            log_info("Embeddings: GPU (KAIA_EMBED_GPU=1) — offline batch mode.")
        self.embed_model = OllamaEmbedding(
            model_name=config.embedding_model,
            base_url="http://localhost:11434",
            query_instruction=config.rag_query_instruction,
            text_instruction=config.rag_text_instruction,
            # Placement is worth ~9x on a full rebuild (measured on realistic
            # ~1,750-token nodes; short strings flatter the CPU badly). Batch size
            # is not a lever: Ollama serialises the requests, so throughput
            # saturates around concurrency 10 and is flat above it.
            ollama_additional_kwargs={
                "num_gpu": 99 if _embed_on_gpu else 0,
                "num_thread": 8 if _embed_on_gpu else 4,
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
        
        # Query synthesis uses the chat model, and `num_gpu: 0` must NOT be set
        # here: LlamaIndex passes the option through on every runtime query, which
        # evicts the chat model from VRAM to satisfy it.
        #
        # Options are built from config directly rather than through
        # OllamaGPUManager, which probes Ollama over NVML and can allocate VRAM
        # before the Phase 1 GPU lock is established. Construction itself is
        # I/O-free — the Ollama() wrapper does not call the engine until the first
        # query, well after that lock.
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
        
        self._known_users_cache = []
        self._last_user_scan = 0

        self._user_scan_interval = getattr(config, 'rag_user_scan_interval', 300)
        self._indexing_in_progress = False
        self._refresh_pending = False # Single-flight "dirty" flag
        self._bot_user_id = None # Set by Discord bot on startup
        self._initialized = False

        # Context-isolated RAG state storage (🔴-1)
        self._channel_retrieval_results = {}
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
