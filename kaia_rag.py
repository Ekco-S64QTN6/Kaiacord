import os
import re
import time
import shutil
import logging
import warnings
import pypdf
import glob
import docx2txt
import threading

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
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage, Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter, SemanticSplitterNodeParser, CodeSplitter
from utils.kaia_logger import *

class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open"""
    pass

class SimpleBM25Retriever:
    """Simple BM25 retriever for hybrid search."""
    def __init__(self, nodes):
        self.nodes = nodes
        self.tokenized_docs = [self._tokenize(node.get_content()) for node in nodes]
        self.bm25 = BM25Okapi(self.tokenized_docs) if self.tokenized_docs else None
        
    def _tokenize(self, text):
        return re.sub(r'[^\w\s]', '', text.lower()).split()
    
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
    def __init__(self, vector_index, bm25_retriever):
        self.vector_index = vector_index
        self.bm25 = bm25_retriever
        
    def retrieve(self, query, top_k=5, alpha=0.5):
        # 1. Vector Retrieval
        vector_retriever = self.vector_index.as_retriever(similarity_top_k=top_k*2)
        vector_nodes = vector_retriever.retrieve(query)
        
        # 2. BM25 Retrieval
        bm25_results = self.bm25.retrieve(query, top_k=top_k*2)
        
        # 3. Reciprocal Rank Fusion (RRF)
        combined_scores = {} # node_id -> score
        node_map = {} # node_id -> node
        
        # Vector RRF
        for rank, node in enumerate(vector_nodes):
            node_id = node.node_id
            node_map[node_id] = node
            combined_scores[node_id] = combined_scores.get(node_id, 0) + alpha * (1.0 / (rank + 60))
            
        # BM25 RRF
        for rank, (node, score) in enumerate(bm25_results):
            node_id = node.node_id
            node_map[node_id] = node
            combined_scores[node_id] = combined_scores.get(node_id, 0) + (1.0 - alpha) * (1.0 / (rank + 60))
            
        # Sort and return top_k
        sorted_ids = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        return [node_map[node_id] for node_id, _ in sorted_ids[:top_k]]

class CircuitBreaker:
    """Circuit breaker for external services"""
    def __init__(self, failure_threshold: int = 3, reset_timeout: int = 60):
        self.failures = 0
        self.last_failure = 0.0
        self.threshold = failure_threshold
        self.timeout = reset_timeout
        
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
                self.failures += 1
                self.last_failure = time.time()
                raise
        return wrapper
        
    def is_open(self) -> bool:
        return (self.failures >= self.threshold and 
                time.time() - self.last_failure < self.timeout)
                
    def _reset(self):
        self.failures = 0

def thread_safe_rag_operation(func):
    """Decorator to ensure thread safety for RAG operations with timeout and graceful fallback"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Try to acquire the lock with a timeout to avoid hanging the bot
        # 10 seconds is generous but prevents permanent deadlocks
        if not self._lock.acquire(timeout=10):
            log_warning(f"RAG operation {func.__name__} timed out waiting for lock")
            if func.__name__ == 'retrieve': return []
            if func.__name__ in ['add_memory', 'log_user_interaction']: return False
            return None
            
        try:
            # If indexing is in progress, skip other operations to avoid VRAM/CPU contention
            # and potentially long wait times.
            if getattr(self, '_indexing_in_progress', False) and func.__name__ != 'refresh_knowledge_base':
                log_warning(f"RAG operation {func.__name__} skipped: indexing in progress")
                if func.__name__ == 'retrieve': return []
                if func.__name__ in ['add_memory', 'log_user_interaction']: return False
                return None
                
            return func(self, *args, **kwargs)
        finally:
            self._lock.release()
    return wrapper

class KaiaRAG:
    def __init__(self, knowledge_base_dir="./knowledge_base", persist_dir="./storage"):
        self.knowledge_base_dir = knowledge_base_dir
        self.persist_dir = persist_dir
        self.indexed_files = {}  # Track indexed files {path: mtime} to detect updates
        
        # Configure Ollama Embedding
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434"
        )
        
        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=20)
        Settings.llm = Ollama(model="gemma3:12b", request_timeout=360.0, additional_kwargs={"num_predict": 1536})
        
        self.index = None # Legacy index reference
        self.indices = {} # Hierarchical indices
        self.bm25_cache = {} # Cache for BM25 retrievers {itype: (timestamp, retriever)}
        self.persist_needed = False
        self._lock = threading.RLock()
        self._indexing_in_progress = False
        
        # Load or create indices
        self._initialize_indices()

    def _initialize_indices(self):
        """Initialize hierarchical indices from storage or create new ones."""
        with self._lock:
            index_types = ['persona', 'user_profiles', 'conversations', 'knowledge', 'logs']
            for itype in index_types:
                itype_dir = os.path.join(self.persist_dir, itype)
                try:
                    if os.path.exists(itype_dir) and os.listdir(itype_dir):
                        log_action(f"Loading {itype} index...")
                        storage_context = StorageContext.from_defaults(persist_dir=itype_dir)
                        self.indices[itype] = load_index_from_storage(storage_context)
                    else:
                        log_action(f"Initializing {itype} index...")
                        self.indices[itype] = VectorStoreIndex.from_documents([])
                        if not os.path.exists(itype_dir):
                            os.makedirs(itype_dir)
                        self.indices[itype].storage_context.persist(persist_dir=itype_dir)
                except Exception as e:
                    log_error(f"Error initializing {itype} index: {e}")
                    self.indices[itype] = VectorStoreIndex.from_documents([])
            
            # Populate indexed files from all indices
            self._populate_indexed_files()
            log_success("All hierarchical indices initialized.")

    def _get_node_parser_for_doc(self, itype: str, file_path: str):
        """Dynamic chunking based on content type and index target"""
        if itype == 'logs' or itype == 'conversations':
            # Keep conversations together with larger chunks
            return SentenceSplitter(chunk_size=1024, chunk_overlap=100)
        elif file_path.endswith(('.py', '.js', '.html', '.css', '.go', '.rs')):
            # Code files: preserve structure
            lang = file_path.split('.')[-1]
            if lang == 'py': lang = 'python'
            elif lang == 'js': lang = 'javascript'
            try:
                return CodeSplitter(language=lang, chunk_lines=100, chunk_overlap=10)
            except:
                return SentenceSplitter(chunk_size=512, chunk_overlap=50)
        elif itype == 'knowledge':
            # Semantic chunking for dense content
            return SemanticSplitterNodeParser(
                buffer_size=1,
                breakpoint_percentile_threshold=95,
                embed_model=self.embed_model
            )
        else:
            return SentenceSplitter(chunk_size=512, chunk_overlap=50)

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
                    log_action(f"Cleaning up {len(stale_nodes)} stale entries from {itype} index...")
                    for node_id in stale_nodes:
                        try:
                            index.delete_nodes([node_id])
                        except Exception as e:
                            log_warning(f"Could not delete node {node_id} in {itype}: {e}")
            
            self.indexed_files = valid_files
            log_success(f"Populated {len(self.indexed_files)} valid indexed files.")

    @thread_safe_rag_operation
    def refresh_knowledge_base(self):
        """Scan knowledge base for new/modified files and update indices."""
        with self._lock:
            if self._indexing_in_progress:
                return
            self._indexing_in_progress = True
            # Clear BM25 cache as indices are changing
            self.bm25_cache.clear()
        
        try:
            if not os.path.exists(self.knowledge_base_dir):
                os.makedirs(self.knowledge_base_dir)
                return

            log_action(f"Refreshing knowledge base...")
            
            # Create corrupt_files directory if it doesn't exist
            corrupt_dir = os.path.join(self.knowledge_base_dir, "corrupt_files")
            if not os.path.exists(corrupt_dir):
                os.makedirs(corrupt_dir)

            # 1. Manually walk the directory to find NEW files
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
                        
                        is_new = norm_path not in self.indexed_files
                        is_modified = not is_new and mtime > self.indexed_files[norm_path]
                        
                        if (is_new or is_modified) and "user_memories.txt" not in file:
                            is_log = itype == 'logs'
                            new_file_paths.append((full_path, is_modified, is_log, itype))

            # 2. Also index the persona file from root
            persona_file = "kaia_persona.md"
            if os.path.exists(persona_file):
                norm_path = os.path.abspath(persona_file)
                mtime = os.path.getmtime(norm_path)
                if norm_path not in self.indexed_files or mtime > self.indexed_files[norm_path]:
                    new_file_paths.append((persona_file, norm_path in self.indexed_files, False, 'persona'))

            if not new_file_paths:
                log_info("No new documents to index.")
            else:
                log_action(f"Found {len(new_file_paths)} new or modified documents. Processing...")
                
                for file_path, is_modified, is_log, itype in new_file_paths:
                    target_index = self.indices[itype]
                    if is_modified and not is_log:
                        log_action(f"Detected update in {itype} file. Re-indexing...")
                        log_file(file_path)
                        abs_path = os.path.abspath(file_path)
                        nodes_to_delete = [
                            node_id for node_id, node in target_index.docstore.docs.items()
                            if node.metadata.get('file_path') == file_path or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
                        ]
                        if nodes_to_delete:
                            print(f"Deleting {len(nodes_to_delete)} old nodes from {itype} for {file_path}")
                            for node_id in nodes_to_delete:
                                target_index.delete_nodes([node_id])
                    elif is_log:
                        log_action(f"Checking for new content in {itype} log...")
                        log_file(file_path)
                    else:
                        log_action(f"Processing new {itype} file...")
                        log_file(file_path)
                        
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
                                log_info(f"No new content in {itype} log (Offset: {last_offset})")
                                self.indexed_files[abs_path] = os.path.getmtime(file_path)
                                continue
                                
                            log_action(f"Indexing new {itype} content from offset {last_offset}...")
                            with open(file_path, 'r', encoding='utf-8') as f:
                                f.seek(last_offset)
                                new_content = f.read()
                                
                            if new_content.strip():
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
                                # Use specialized node parser
                                parser = self._get_node_parser_for_doc(itype, file_path)
                                nodes = parser.get_nodes_from_documents([doc])
                                target_index.insert_nodes(nodes)
                                
                                self.indexed_files[abs_path] = mtime
                                log_success(f"Indexed {len(new_content)} new characters from {itype} log.")
                            else:
                                self.indexed_files[abs_path] = os.path.getmtime(file_path)
                        else:
                            # Standard loading for non-log files
                            reader = SimpleDirectoryReader(input_files=[file_path])
                            docs = reader.load_data()
                            
                            if docs:
                                mtime = os.path.getmtime(file_path)
                                parser = self._get_node_parser_for_doc(itype, file_path)
                                for doc in docs:
                                    doc.metadata['last_modified_at'] = mtime
                                    doc.metadata['file_path'] = os.path.abspath(file_path)
                                    doc.metadata['itype'] = itype
                                    
                                    if itype == 'persona':
                                        doc.metadata['source'] = "persona"
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
                                        except: pass
                                    
                                    # Pre-chunk large documents to avoid embedding overflows
                                    sub_docs = self._pre_chunk_document(doc)
                                    for sub_doc in sub_docs:
                                        nodes = parser.get_nodes_from_documents([sub_doc])
                                        target_index.insert_nodes(nodes)
                                
                                self.indexed_files[abs_path] = mtime
                                log_success(f"Indexed {file_path} into {itype} index.")
                            else:
                                log_warning(f"No data loaded from file. Moving to corrupt_files.")
                                log_file(file_path)
                                try:
                                    dest_path = os.path.join(corrupt_dir, os.path.basename(file_path))
                                    if os.path.exists(dest_path):
                                        dest_path = f"{dest_path}_{int(time.time())}"
                                    shutil.move(file_path, dest_path)
                                    log_critical(f"MOVED EMPTY/CORRUPT FILE TO: {dest_path}")
                                except Exception as move_err:
                                    log_warning(f"Failed to move empty file: {move_err}")
                            
                    except Exception as e:
                        log_error(f"Failed to load file: {e}")
                        log_file(file_path)
                        
                        conversion_succeeded = False
                        
                        # Attempt conversion if it's a PDF or DOCX
                        if file_path.lower().endswith((".pdf", ".docx")):
                            ext = ".pdf" if file_path.lower().endswith(".pdf") else ".docx"
                            log_action(f"Attempting to recover file by converting to Markdown...")
                            log_file(file_path)
                            
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
                                        self.indexed_files[os.path.abspath(md_path)] = mtime
                                        # Also track original PDF as "handled" so we don't retry
                                        self.indexed_files[os.path.abspath(file_path)] = orig_mtime
                                        log_success(f"Successfully indexed converted Markdown")
                                        log_file(md_path)
                                        conversion_succeeded = True
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
                log_info("New documents indexed. Persistence marked as needed.")
                
        except Exception as e:
            log_error(f"Error refreshing knowledge base: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._indexing_in_progress = False

    @CircuitBreaker(failure_threshold=3)
    def _convert_pdf_to_md(self, pdf_path: str) -> Optional[str]:
        """Convert a PDF file to a Markdown file by extracting text."""
        try:
            # Strip .pdf extension before adding .md for cleaner filenames
            base_path = pdf_path[:-4] if pdf_path.lower().endswith('.pdf') else pdf_path
            md_path = base_path + ".md"
            log_action(f"Extracting text from PDF...")
            log_file(pdf_path)
            
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
                log_file(md_path)
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
            log_file(docx_path)
            
            text = docx2txt.process(docx_path)
            
            if text and text.strip():
                basename = os.path.basename(docx_path)
                title = basename[:-5] if basename.lower().endswith('.docx') else basename
                
                md_content = f"# {title}\n\n{text}"
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                log_success(f"Successfully converted to Markdown")
                log_file(md_path)
                return md_path
            else:
                log_warning(f"No text extracted from DOCX")
                return None
        except Exception as e:
            log_error(f"Error converting DOCX to MD: {e}")
            return None

    @thread_safe_rag_operation
    def add_memory(self, user_id: int, user_name: str, text: str) -> bool:
        """Log a 'remembered' fact into the user's interaction log."""
        try:
            # We treat this as a special interaction where the user says "remember this" 
            # and Kaia acknowledges it.
            return self.log_user_interaction(
                user_id, 
                user_name, 
                f"[REMEMBER_COMMAND]: {text}", 
                "Logged it. I'll remember that."
            )
        except Exception as e:
            log_error(f"Error adding memory: {e}")
            return False

    @thread_safe_rag_operation
    def log_user_interaction(self, user_id: int, user_name: str, message_content: str, bot_response: str, is_vision_response: bool = False) -> bool:
        """Log user interaction to a single file per user, rotating at 100MB.
        
        Args:
            is_vision_response: If True, marks this as a vision analysis response
                               to be filtered from non-vision RAG retrievals.
        """
        with self._lock:
            # Sanitize user_name for filesystem
            safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
            user_dir_name = f"{safe_user_name}_{user_id}"
            user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
            
            try:
                # Create user directory if it doesn't exist
                if not os.path.exists(user_log_dir):
                    os.makedirs(user_log_dir)
                    log_success(f"Created user log directory")
                    log_file(user_log_dir)
                
                # Find existing log file or create new one with today's date
                # Pattern: interactions_YYYYMMDD.txt
                existing_logs = sorted(glob.glob(os.path.join(user_log_dir, "interactions_*.txt")))
                
                MAX_SIZE = 100 * 1024 * 1024  # 100MB in bytes
                
                if existing_logs:
                    # Use the most recent log file
                    log_file = existing_logs[-1]
                    
                    # Check if it exceeds 100MB - if so, create a new file with today's date
                    if os.path.getsize(log_file) >= MAX_SIZE:
                        new_timestamp = datetime.now().strftime("%Y%m%d")
                        log_file = os.path.join(user_log_dir, f"interactions_{new_timestamp}.txt")
                        log_info(f"Previous log full, starting new log")
                else:
                    # No existing logs - create first one with today's date
                    new_timestamp = datetime.now().strftime("%Y%m%d")
                    log_file = os.path.join(user_log_dir, f"interactions_{new_timestamp}.txt")
                
                # Append interaction to the single file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                interaction_text = f"""--- {timestamp} ---
User ({user_name}): {message_content}
Kaia: {bot_response}

"""
                # Get current size before appending for the offset
                file_offset = os.path.getsize(log_file) if os.path.exists(log_file) else 0
                
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(interaction_text)
                
                log_success(f"Logged interaction for {user_name}")
                
                # INCREMENTAL INSERT: Add the interaction to the index
                mtime = os.path.getmtime(log_file)
                new_doc = Document(
                    text=interaction_text,
                    metadata={
                        "source": "user_logs",
                        "itype": "logs",
                        "user_id": str(user_id),
                        "user_name": user_name,
                        "timestamp": timestamp,
                        "file_path": os.path.abspath(log_file),
                        "last_modified_at": mtime,
                        "file_offset": file_offset,
                        "content_length": len(interaction_text),
                        "is_vision_response": is_vision_response
                    }
                )
                
                # Use specialized node parser for logs
                parser = self._get_node_parser_for_doc('logs', log_file)
                nodes = parser.get_nodes_from_documents([new_doc])
                self.indices['logs'].insert_nodes(nodes)
                
                # Clear BM25 cache for logs
                if 'logs' in self.bm25_cache:
                    self.bm25_cache['logs'] = None
                
                self.indexed_files[os.path.abspath(log_file)] = mtime
                self.persist_needed = True
                log_success(f"Interaction indexed for user {user_name} into logs index")
                
                return True
            except Exception as e:
                log_error(f"Error logging user interaction: {e}")
                import traceback
                traceback.print_exc()
                return False

    @thread_safe_rag_operation
    def retrieve(self, query: str, user_id: Optional[int] = None, user_name: Optional[str] = None, top_k: int = 4) -> List[str]:
        """
        Retrieve relevant nodes, ensuring user logs are prioritized and not drowned out.
        If user_id is provided, specifically looks for that user's history and preferences.
        
        OPTIMIZED: No longer iterates through entire docstore. Uses retriever results only.
        """
        with self._lock:
            if not self.indices:
                return []
        
        if not query or not query.strip():
            return []
        
        try:
            # 1. Identify the type of query FIRST to determine retrieval strategy
            query_lower = query.lower()
            is_kaia_query = any(phrase in query_lower for phrase in ["who are you", "who is kaia", "tell me about yourself", "what are you"])
            is_user_identity_query = any(phrase in query_lower for phrase in ["who am i", "what is my name", "my pronoun", "who is"]) and not is_kaia_query
            
            # Detect casual/social conversation that doesn't need knowledge retrieval
            casual_patterns = [
                "how are you", "what's up", "hey", "hello", "hi ", "sup", "yo ",
                "good morning", "good night", "thanks", "thank you", "bye",
                "my name is", "i'm ", "i am ", "nice to meet", "what do you think",
                "how's it going", "what are you doing", "what are you up to"
            ]
            # A query is casual if it matches patterns AND isn't a specific identity query
            is_casual = (any(phrase in query_lower for phrase in casual_patterns) or len(query_lower.split()) <= 4) and not (is_kaia_query or is_user_identity_query)
            is_identity_query = is_kaia_query or is_user_identity_query
            
            # Detect if this is a vision-related query
            is_vision_query = any(word in query_lower for word in ["analyze", "look", "image", "picture", "what is this", "describe this"])
            
            # 2. Single retrieval pass with query enrichment
            enriched_query = query
            
            # Detect known user names in the query to improve retrieval
            known_users = []
            user_logs_path = os.path.join(self.knowledge_base_dir, "user_logs")
            if os.path.exists(user_logs_path):
                for d in os.scandir(user_logs_path):
                    if d.is_dir() and "_" in d.name:
                        u_name = d.name.rsplit("_", 1)[0].replace("_", " ")
                        known_users.append(u_name)
            
            detected_user = None
            for u_name in known_users:
                if u_name.lower() in query_lower:
                    detected_user = u_name
                    break
                # Also check parts of the name
                for part in u_name.split():
                    if len(part) > 3 and part.lower() in query_lower:
                        detected_user = u_name
                        break
                if detected_user: break
            
            # Only enrich with user context if the query is specifically about the current user
            is_self_query = any(phrase in query_lower for phrase in ["who am i", "what am i", "my character", "my profile", "my history", "my name", "my pronoun"])
            
            # ENRICHMENT STRATEGY:
            # Always boost the current user for casual/identity queries to ensure their nodes are in the top_k
            if user_name and (is_casual or is_self_query):
                enriched_query = f"{query} user:{user_name} {user_name}"
            
            # If another user is detected, boost them too
            if detected_user:
                # Repeat the name to boost its importance in the embedding
                enriched_query += f" user:{detected_user} {detected_user} {detected_user}"
            
            # 2. ROUTING: Determine which indices to hit
            target_itypes = []
            if is_kaia_query:
                target_itypes = ['persona']
            elif is_user_identity_query:
                target_itypes = ['user_profiles', 'logs']
            elif is_vision_query:
                target_itypes = ['logs']
            else:
                # General query: hit everything except persona (unless explicitly asked)
                target_itypes = ['knowledge', 'logs', 'user_profiles']
            
            # Retrieve with a significantly higher limit to ensure profiles are found
            retrieve_count = 15 if is_casual else 25
            
            all_node_results = []
            for itype in target_itypes:
                if itype in self.indices:
                    # Get or build BM25 retriever
                    if itype not in self.bm25_cache or self.bm25_cache[itype] is None:
                        index_nodes = list(self.indices[itype].storage_context.docstore.docs.values())
                        if index_nodes:
                            self.bm25_cache[itype] = SimpleBM25Retriever(index_nodes)
                        else:
                            self.bm25_cache[itype] = None
                    
                    bm25_retriever = self.bm25_cache.get(itype)
                    if bm25_retriever:
                        hybrid = HybridRetriever(self.indices[itype], bm25_retriever)
                        all_node_results.extend(hybrid.retrieve(enriched_query, top_k=retrieve_count))
                    else:
                        # Fallback to vector only
                        retriever = self.indices[itype].as_retriever(similarity_top_k=retrieve_count)
                        all_node_results.extend(retriever.retrieve(enriched_query))
            
            # 3. Categorize and Score nodes
            scored_nodes = [] # List of (score, content, label)
            seen_texts = set()
            u_id_str = str(user_id) if user_id else None
            
            # Lore relevance threshold
            lore_threshold = 0.80 if is_casual else 0.60
            
            for node_result in all_node_results:
                node = node_result.node if hasattr(node_result, 'node') else node_result
                base_score = node_result.score if hasattr(node_result, 'score') else 0.5
                content = node.get_content()
                
                # Skip duplicates
                content_hash = hash(content[:200]) if len(content) > 200 else hash(content)
                if content_hash in seen_texts:
                    continue
                seen_texts.add(content_hash)
                
                # FILTER: Skip vision response nodes for non-vision queries to prevent feedback loop
                if node.metadata.get('is_vision_response') and not is_vision_query:
                    continue
                
                # Quality filter
                sample = content[:500]
                if sample:
                    ascii_count = sum(1 for c in sample if c.isascii() and c.isprintable())
                    if (ascii_count / len(sample)) < 0.80:
                        continue
                
                # ENHANCED SCORING LOGIC
                # 1. Recency boost
                timestamp = node.metadata.get('timestamp')
                if timestamp:
                    if isinstance(timestamp, str):
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            ts = dt.timestamp()
                        except:
                            ts = time.time() - 86400 * 30
                    else:
                        ts = timestamp
                    days_old = (time.time() - ts) / 86400
                    recency_boost = max(0, 1 - (days_old / 30))
                else:
                    recency_boost = 0.5
                
                # 2. User specificity boost
                node_user_id = str(node.metadata.get('user_id', ''))
                user_match_boost = 2.0 if node_user_id == u_id_str else 1.0
                
                # 3. Content type boost
                source = node.metadata.get('source', '')
                type_boost = {
                    'user_profile': 3.0,
                    'persona': 2.5,
                    'conversation': 1.5,
                    'knowledge': 1.0
                }.get(source, 1.0)
                
                # 4. Length penalty
                content_len = len(content)
                if 50 < content_len < 2000:
                    length_penalty = 1.0
                elif content_len <= 50:
                    length_penalty = 0.7
                else:
                    length_penalty = 0.8
                
                final_score = (
                    base_score * 0.4 +
                    recency_boost * 0.2 +
                    user_match_boost * 0.3 +
                    type_boost * 0.1
                ) * length_penalty
                
                # Determine label for display
                file_path = node.metadata.get('file_path', '')
                node_user_name = node.metadata.get('user_name', 'Unknown')
                label = ""
                
                if source == "persona" or node_user_id == "KAIA_SYSTEM":
                    label = "Kaia Persona Fragment"
                elif source == "user_logs" or "user_logs" in file_path:
                    if "user_profile.md" in file_path:
                        label = f"User Profile: {node_user_name.upper()}"
                    else:
                        label = f"Conversation History: {node_user_name.upper()}"
                else:
                    label = f"Knowledge: {os.path.basename(file_path)}"
                
                scored_nodes.append((final_score, content, label))
            
            # 4. Sort and Filter
            scored_nodes.sort(key=lambda x: x[0], reverse=True)
            
            # Apply query-type specific filtering
            final_results = []
            persona_count = 0
            user_log_count = 0
            lore_count = 0
            
            for _, content, label in scored_nodes:
                if "Kaia Persona" in label:
                    if is_user_identity_query: continue # Skip persona for user identity queries
                    if persona_count >= (4 if is_kaia_query else 1): continue
                    persona_count += 1
                elif "User Profile" in label or "Conversation History" in label:
                    if user_log_count >= (6 if is_identity_query else 5): continue
                    user_log_count += 1
                elif "Historical Reference" in label:
                    if is_identity_query: continue # Skip lore for identity queries
                    if lore_count >= (2 if is_casual else 4): continue
                    lore_count += 1
                
                final_results.append(content)
                if len(final_results) >= top_k:
                    break
            
            query_type = "casual" if is_casual else ("identity" if is_identity_query else "knowledge")
            log_success(f"Retrieved {len(final_results)} results [{query_type}] (P:{persona_count}, U:{user_log_count}, L:{lore_count}, thresh:{lore_threshold:.2f})")
            return final_results

            
        except Exception as e:
            log_error(f"Error during retrieval: {e}")
            import traceback
            traceback.print_exc()
            return []

    @thread_safe_rag_operation
    def persist(self, force: bool = False):
        """Persist all hierarchical indices to storage if needed."""
        if self.persist_needed or force:
            try:
                for itype, index in self.indices.items():
                    itype_dir = os.path.join(self.persist_dir, itype)
                    index.storage_context.persist(persist_dir=itype_dir)
                self.persist_needed = False
                log_success(f"All hierarchical indices persisted to {self.persist_dir}")
            except Exception as e:
                log_error(f"Error persisting indices: {e}")

if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
