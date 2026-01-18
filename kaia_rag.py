import os
import time
import shutil
import logging
import warnings
import pypdf
import glob

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
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage, Document
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter

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
        
        self.index = None
        
        # Load or create index
        self._initialize_index()

    def _initialize_index(self):
        """Initialize the index from storage or create a new one."""
        try:
            if os.path.exists(self.persist_dir) and os.listdir(self.persist_dir):
                print(f"Loading existing index from {self.persist_dir}...")
                storage_context = StorageContext.from_defaults(persist_dir=self.persist_dir)
                self.index = load_index_from_storage(storage_context)
                self._populate_indexed_files()
                print("✓ Existing index loaded successfully.")
                # Always refresh to pick up new files (e.g. user logs from previous sessions)
                self.refresh_knowledge_base()
            else:
                print("No existing index found. Initializing knowledge base...")
                self.index = VectorStoreIndex.from_documents([])
                if not os.path.exists(self.persist_dir):
                    os.makedirs(self.persist_dir)
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                print("New index created.")
                # Only do the slow refresh on first-time setup
                print("First-time setup: indexing knowledge base (this will take a while)...")
                self.refresh_knowledge_base()
            
        except Exception as e:
            print(f"Error initializing RAG index: {e}")
            import traceback
            traceback.print_exc()
            self.index = VectorStoreIndex.from_documents([])

    def _populate_indexed_files(self):
        """Populate the set of indexed files from the existing index and clean up stale entries."""
        if not self.index:
            return
        
        stale_nodes = []
        valid_files = {} # path -> mtime
        
        for node_id, node in self.index.docstore.docs.items():
            file_path = node.metadata.get('file_path')
            if file_path:
                abs_path = os.path.abspath(file_path)
                if os.path.exists(abs_path):
                    # Get the timestamp from metadata. 
                    # OPTIMIZATION: If missing, use the current disk mtime as the baseline.
                    # This prevents a mass re-index of static files on the first run.
                    indexed_mtime = node.metadata.get('last_modified_at', os.path.getmtime(abs_path))
                    # Keep the OLDEST timestamp found for this file to be safe
                    if abs_path not in valid_files or indexed_mtime < valid_files[abs_path]:
                        valid_files[abs_path] = indexed_mtime
                else:
                    stale_nodes.append(node_id)
        
        # Remove stale nodes from index
        if stale_nodes:
            print(f"Cleaning up {len(stale_nodes)} stale index entries...")
            for node_id in stale_nodes:
                try:
                    self.index.delete_nodes([node_id])
                except Exception as e:
                    print(f"Warning: Could not delete node {node_id}: {e}")
            
            # Persist after cleanup
            self.index.storage_context.persist(persist_dir=self.persist_dir)
            print("✓ Index cleanup complete and persisted.")

        self.indexed_files = valid_files
        
        # Also check for user_memories.txt specifically
        memory_file = os.path.join(self.knowledge_base_dir, "user_memories.txt")
        norm_memory_path = os.path.abspath(memory_file)
        if os.path.exists(norm_memory_path):
            # Check if any node has this source
            for node in self.index.docstore.docs.values():
                if node.metadata.get('source') == "user_memories.txt":
                    indexed_mtime = node.metadata.get('last_modified_at', os.path.getmtime(norm_memory_path))
                    if norm_memory_path not in self.indexed_files or indexed_mtime < self.indexed_files[norm_memory_path]:
                        self.indexed_files[norm_memory_path] = indexed_mtime
                    break
                
        print(f"Populated {len(self.indexed_files)} valid indexed files from storage.")

    def refresh_knowledge_base(self):
        """Load all supported files from the knowledge base directory and update the index incrementally."""
        if not os.path.exists(self.knowledge_base_dir):
            os.makedirs(self.knowledge_base_dir)
            return

        print(f"Refreshing knowledge base from {self.knowledge_base_dir}...")
        
        # Create corrupt_files directory if it doesn't exist
        corrupt_dir = os.path.join(self.knowledge_base_dir, "corrupt_files")
        if not os.path.exists(corrupt_dir):
            os.makedirs(corrupt_dir)

        try:
            # 1. Manually walk the directory to find NEW files
            # This is MUCH faster than letting SimpleDirectoryReader scan everything
            new_file_paths = []
            supported_exts = [".pdf", ".txt", ".md", ".docx"]
            
            for root, dirs, files in os.walk(self.knowledge_base_dir):
                # Skip ONLY the corrupt_files directory (allow user_logs to be scanned)
                if "corrupt_files" in root:
                    continue
                    
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in supported_exts:
                        full_path = os.path.join(root, file)
                        # Normalize path for tracking
                        norm_path = os.path.abspath(full_path)
                        mtime = os.path.getmtime(norm_path)
                        
                        # Check if new OR modified
                        is_new = norm_path not in self.indexed_files
                        is_modified = not is_new and mtime > self.indexed_files[norm_path]
                        
                        if (is_new or is_modified) and "user_memories.txt" not in file:
                            new_file_paths.append((full_path, is_modified))

            if not new_file_paths:
                print("No new documents to index.")
            else:
                print(f"Found {len(new_file_paths)} new documents. Processing...")
                
                for file_path, is_modified in new_file_paths:
                    if is_modified:
                        print(f"Detected update in: {file_path}. Re-indexing...")
                        # Delete old nodes for this file
                        abs_path = os.path.abspath(file_path)
                        nodes_to_delete = [
                            node_id for node_id, node in self.index.docstore.docs.items()
                            if node.metadata.get('file_path') == file_path or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
                        ]
                        if nodes_to_delete:
                            print(f"Deleting {len(nodes_to_delete)} old nodes for {file_path}")
                            for node_id in nodes_to_delete:
                                self.index.delete_nodes([node_id])
                    else:
                        print(f"Processing new file: {file_path}")
                        
                    try:
                        # Load single file
                        reader = SimpleDirectoryReader(input_files=[file_path])
                        docs = reader.load_data()
                        
                        if docs:
                            mtime = os.path.getmtime(file_path)
                            for doc in docs:
                                doc.metadata['last_modified_at'] = mtime
                                self.index.insert(doc)
                            
                            self.indexed_files[os.path.abspath(file_path)] = mtime
                            print(f"✓ Successfully indexed: {file_path}")
                        else:
                            print(f"Warning: No data loaded from {file_path}. Moving to corrupt_files.")
                            try:
                                dest_path = os.path.join(corrupt_dir, os.path.basename(file_path))
                                if os.path.exists(dest_path):
                                    dest_path = f"{dest_path}_{int(time.time())}"
                                shutil.move(file_path, dest_path)
                                print(f"!!! MOVED EMPTY/CORRUPT FILE TO: {dest_path}")
                            except Exception as move_err:
                                print(f"Failed to move empty file: {move_err}")
                            
                    except Exception as e:
                        print(f"CRITICAL ERROR: Failed to load file {file_path}: {e}")
                        
                        conversion_succeeded = False
                        
                        # Attempt conversion if it's a PDF
                        if file_path.lower().endswith(".pdf"):
                            print(f"Attempting to recover {file_path} by converting to Markdown...")
                            md_path = self._convert_pdf_to_md(file_path)
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
                                            self.index.insert(doc)
                                        self.indexed_files[os.path.abspath(md_path)] = mtime
                                        # Also track original PDF as "handled" so we don't retry
                                        self.indexed_files[os.path.abspath(file_path)] = orig_mtime
                                        print(f"✓ Successfully indexed converted Markdown: {md_path}")
                                        conversion_succeeded = True
                                    else:
                                        print(f"Warning: Converted MD {md_path} was empty.")
                                except Exception as md_err:
                                    print(f"Failed to index converted MD {md_path}: {md_err}")

                        # Only move to corrupt_files if conversion failed or wasn't attempted
                        if not conversion_succeeded:
                            try:
                                dest_path = os.path.join(corrupt_dir, os.path.basename(file_path))
                                # Handle name collisions in corrupt_dir
                                if os.path.exists(dest_path):
                                    dest_path = f"{dest_path}_{int(time.time())}"
                                
                                shutil.move(file_path, dest_path)
                                print(f"!!! MOVED CORRUPT FILE TO: {dest_path}")
                            except Exception as move_err:
                                print(f"Failed to move corrupt file: {move_err}")

                # Persist after adding new documents
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                print("Index persisted with new documents.")
            
            # 2. Special handling for user_memories.txt to split by '---'
            memory_file = os.path.join(self.knowledge_base_dir, "user_memories.txt")
            norm_memory_path = os.path.abspath(memory_file)
            
            # For user_memories.txt, we also want to detect updates
            mem_is_new = norm_memory_path not in self.indexed_files
            mem_is_modified = not mem_is_new and os.path.getmtime(norm_memory_path) > self.indexed_files[norm_memory_path]

            if os.path.exists(memory_file) and (mem_is_new or mem_is_modified):
                if mem_is_modified:
                    print("Detected update in user_memories.txt. Re-indexing fragments...")
                    # Delete old fragments
                    nodes_to_delete = [
                        node_id for node_id, node in self.index.docstore.docs.items()
                        if node.metadata.get('source') == "user_memories.txt"
                    ]
                    if nodes_to_delete:
                        for node_id in nodes_to_delete:
                            self.index.delete_nodes([node_id])
                
                try:
                    with open(memory_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Split by '---' and filter out empty fragments
                        fragments = [frag.strip() for frag in content.split("---") if frag.strip()]
                        if fragments:
                            print(f"Indexing {len(fragments)} fragments from user_memories.txt...")
                            mtime = os.path.getmtime(memory_file)
                            for idx, frag in enumerate(fragments):
                                self.index.insert(Document(
                                    text=frag, 
                                    metadata={
                                        "source": "user_memories.txt", 
                                        "fragment_id": idx,
                                        "last_modified_at": mtime
                                    }
                                ))
                            
                            self.indexed_files[norm_memory_path] = mtime
                            self.index.storage_context.persist(persist_dir=self.persist_dir)
                            print("✓ user_memories.txt indexed.")
                except Exception as e:
                    print(f"Warning: Error loading user_memories.txt: {e}")
                
        except Exception as e:
            print(f"Error refreshing knowledge base: {e}")
            import traceback
            traceback.print_exc()

    def _convert_pdf_to_md(self, pdf_path):
        """Convert a PDF file to a Markdown file by extracting text."""
        try:
            # Strip .pdf extension before adding .md for cleaner filenames
            base_path = pdf_path[:-4] if pdf_path.lower().endswith('.pdf') else pdf_path
            md_path = base_path + ".md"
            print(f"Extracting text from {pdf_path}...")
            
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
                print(f"✓ Successfully converted to: {md_path}")
                return md_path
            else:
                print(f"Warning: No text extracted from {pdf_path}")
                return None
        except Exception as e:
            print(f"Error converting PDF to MD: {e}")
            return None

    def add_memory(self, text):
        """Append a user-provided memory to user_memories.txt and add it incrementally."""
        memory_file = os.path.join(self.knowledge_base_dir, "user_memories.txt")
        try:
            with open(memory_file, "a", encoding="utf-8") as f:
                f.write(f"\n---\n[RECOVERED MEMORY]: {text}\n")
            
            print(f"Stored new memory fragment in {memory_file}")
            
            # INCREMENTAL INSERT: Add only the new memory
            new_doc = Document(
                text=f"[RECOVERED MEMORY]: {text}",
                metadata={"source": "user_memories.txt", "timestamp": datetime.now().isoformat()}
            )
            self.index.insert(new_doc)
            self.index.storage_context.persist(persist_dir=self.persist_dir)
            print("Memory indexed incrementally.")
            
            return True
        except Exception as e:
            print(f"Error adding memory: {e}")
            import traceback
            traceback.print_exc()
            return False

    def log_user_interaction(self, user_id, user_name, message_content, bot_response):
        """Log user interaction to a single file per user, rotating at 100MB."""
        # Sanitize user_name for filesystem
        safe_user_name = "".join([c for c in user_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(' ', '_')
        user_dir_name = f"{safe_user_name}_{user_id}"
        user_log_dir = os.path.join(self.knowledge_base_dir, "user_logs", user_dir_name)
        
        try:
            # Create user directory if it doesn't exist
            if not os.path.exists(user_log_dir):
                os.makedirs(user_log_dir)
                print(f"Created user log directory: {user_log_dir}")
            
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
                    print(f"Previous log full, starting new log: {log_file}")
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
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(interaction_text)
            
            print(f"Logged interaction to {log_file}")
            
            # INCREMENTAL INSERT: Add the interaction to the index
            mtime = os.path.getmtime(log_file)
            new_doc = Document(
                text=interaction_text,
                metadata={
                    "source": "user_logs",
                    "user_id": str(user_id),
                    "user_name": user_name,
                    "timestamp": timestamp,
                    "file_path": os.path.abspath(log_file),
                    "last_modified_at": mtime
                }
            )
            self.index.insert(new_doc)
            # NOTE: We don't persist here to avoid blocking on every message.
            # The index is persisted on bot shutdown or next boot.
            self.indexed_files[os.path.abspath(log_file)] = mtime
            print(f"Interaction indexed for user {user_name} ({user_id}).")
            
            # Persist periodically or after interaction
            self.persist()
            
            return True
        except Exception as e:
            print(f"Error logging user interaction: {e}")
            import traceback
            traceback.print_exc()
            return False

    def retrieve(self, query, user_id=None, user_name=None, top_k=5):
        """
        Retrieve relevant nodes, ensuring user logs are prioritized and not drowned out.
        If user_id is provided, specifically looks for that user's history and preferences.
        """
        if not self.index:
            return []
        
        if not query or not query.strip():
            return []
        
        try:
            # 1. Broad retrieval for general context
            retriever = self.index.as_retriever(similarity_top_k=20)
            nodes = retriever.retrieve(query)
            
            # 2. If user_id is provided, do a targeted search for user identity/preferences
            # This helps Kaia remember pronouns/facts even if the query doesn't match them well.
            if user_id and user_name:
                identity_query = f"Who is {user_name}? What are their pronouns, preferences, and history?"
                identity_nodes = retriever.retrieve(identity_query)
                # Add identity nodes to the pool, prioritizing them
                nodes = identity_nodes[:5] + nodes
            
            # Separate logs and lore
            current_user_logs = []
            other_user_logs = []
            lore_results = []
            seen_texts = set()
            
            for node in nodes:
                content = node.get_content()
                if content in seen_texts:
                    continue
                seen_texts.add(content)
                
                # Check source metadata
                source = node.metadata.get('source', '')
                file_path = node.metadata.get('file_path', '')
                node_user_id = str(node.metadata.get('user_id', ''))
                
                if source == "user_logs" or "user_logs" in file_path:
                    node_user_name = node.metadata.get('user_name', 'Unknown')
                    
                    # Prioritize current user
                    if user_id and node_user_id == str(user_id):
                        current_user_logs.append(f"[YOUR_HISTORY_WITH_{node_user_name.upper()}]\n{content}")
                    else:
                        other_user_logs.append(f"[OTHER_USER_LOG: {node_user_name}]\n{content}")
                else:
                    lore_results.append(content)
            
            # Combine: Current User Logs -> Lore -> Other Logs
            # We prioritize current user logs (for pronouns/preferences) but keep lore for factual queries.
            combined = current_user_logs[:3] + lore_results[:3] + other_user_logs[:1]
            return combined[:top_k]
            
        except Exception as e:
            print(f"Error during retrieval: {e}")
            import traceback
            traceback.print_exc()
            return []

    def persist(self):
        """Persist the index to storage."""
        if self.index:
            try:
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                print(f"✓ Index persisted to {self.persist_dir}")
            except Exception as e:
                print(f"Error persisting index: {e}")

if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
