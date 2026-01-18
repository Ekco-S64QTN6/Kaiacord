import os
import time
import shutil
import logging
import warnings
import pypdf
import glob
import docx2txt

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
        self.persist_needed = False
        
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
                # We'll call refresh_knowledge_base separately to avoid blocking init
            else:
                print("No existing index found. Initializing knowledge base...")
                self.index = VectorStoreIndex.from_documents([])
                if not os.path.exists(self.persist_dir):
                    os.makedirs(self.persist_dir)
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                print("New index created.")
            
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
                    indexed_mtime = node.metadata.get('last_modified_at', 0)
                    # Keep the NEWEST timestamp found for this file to be safe
                    if abs_path not in valid_files or indexed_mtime > valid_files[abs_path]:
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
                        
                        # Check if new OR modified OR missing metadata
                        is_new = norm_path not in self.indexed_files
                        is_modified = not is_new and mtime > self.indexed_files[norm_path]
                        
                        # Check if metadata is missing (e.g. from an old version of the bot)
                        missing_meta = False
                        if not is_new and not is_modified and "user_logs" in full_path:
                            # Sample a node for this file to check metadata
                            for node in self.index.docstore.docs.values():
                                if node.metadata.get('file_path') == full_path or os.path.abspath(node.metadata.get('file_path', '')) == norm_path:
                                    if not node.metadata.get('user_id'):
                                        missing_meta = True
                                        break
                                    break
                        
                        if (is_new or is_modified or missing_meta) and "user_memories.txt" not in file:
                            # For user logs, we use a special 'is_log' flag to trigger tail-indexing
                            is_log = "user_logs" in full_path
                            new_file_paths.append((full_path, is_modified or missing_meta, is_log))

            # 2. Also index the persona file from root
            persona_file = "kaia_persona.md"
            if os.path.exists(persona_file):
                norm_path = os.path.abspath(persona_file)
                mtime = os.path.getmtime(norm_path)
                if norm_path not in self.indexed_files or mtime > self.indexed_files[norm_path]:
                    new_file_paths.append((persona_file, norm_path in self.indexed_files, False))

            if not new_file_paths:
                print("No new documents to index.")
            else:
                print(f"Found {len(new_file_paths)} new or modified documents. Processing...")
                
                for file_path, is_modified, is_log in new_file_paths:
                    if is_modified and not is_log:
                        print(f"Detected update in: {file_path}. Re-indexing...")
                        # Delete old nodes for this file (only for non-log files)
                        abs_path = os.path.abspath(file_path)
                        nodes_to_delete = [
                            node_id for node_id, node in self.index.docstore.docs.items()
                            if node.metadata.get('file_path') == file_path or os.path.abspath(node.metadata.get('file_path', '')) == abs_path
                        ]
                        if nodes_to_delete:
                            print(f"Deleting {len(nodes_to_delete)} old nodes for {file_path}")
                            for node_id in nodes_to_delete:
                                self.index.delete_nodes([node_id])
                    elif is_log:
                        print(f"Checking for new content in log: {file_path}")
                    else:
                        print(f"Processing new file: {file_path}")
                        
                    try:
                        # Load file content
                        if is_log:
                            # TAIL-INDEXING for logs: only index what's new
                            # 1. Find the last byte offset we indexed
                            last_offset = 0
                            abs_path = os.path.abspath(file_path)
                            for node in self.index.docstore.docs.values():
                                if os.path.abspath(node.metadata.get('file_path', '')) == abs_path:
                                    offset = node.metadata.get('file_offset', 0)
                                    length = node.metadata.get('content_length', 0)
                                    last_offset = max(last_offset, offset + length)
                            
                            file_size = os.path.getsize(file_path)
                            if file_size <= last_offset:
                                print(f"No new content in log {file_path} (Offset: {last_offset})")
                                self.indexed_files[abs_path] = os.path.getmtime(file_path)
                                continue
                                
                            print(f"Indexing new log content from offset {last_offset}...")
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
                                # Extract user metadata for the new doc
                                parts = file_path.split(os.sep)
                                try:
                                    ul_idx = parts.index("user_logs")
                                    user_folder = parts[ul_idx + 1]
                                    if "_" in user_folder:
                                        u_name, u_id = user_folder.rsplit("_", 1)
                                        doc.metadata['user_id'] = u_id
                                        doc.metadata['user_name'] = u_name
                                except: pass
                                
                                self.index.insert(doc)
                                self.indexed_files[abs_path] = mtime
                                print(f"✓ Indexed {len(new_content)} new characters from log.")
                            else:
                                self.indexed_files[abs_path] = os.path.getmtime(file_path)
                        else:
                            # Standard loading for non-log files
                            reader = SimpleDirectoryReader(input_files=[file_path])
                            docs = reader.load_data()
                            
                            if docs:
                                mtime = os.path.getmtime(file_path)
                                for doc in docs:
                                    doc.metadata['last_modified_at'] = mtime
                                    doc.metadata['file_path'] = os.path.abspath(file_path)
                                    
                                    # Tag persona file specifically
                                    if "kaia_persona.md" in file_path:
                                        doc.metadata['source'] = "persona"
                                        doc.metadata['user_id'] = "KAIA_SYSTEM"
                                        
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
                        
                        # Attempt conversion if it's a PDF or DOCX
                        if file_path.lower().endswith((".pdf", ".docx")):
                            ext = ".pdf" if file_path.lower().endswith(".pdf") else ".docx"
                            print(f"Attempting to recover {file_path} by converting to Markdown...")
                            
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

                # Mark for persistence
                self.persist_needed = True
                print("New documents indexed. Persistence marked as needed.")
                
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

    def _convert_docx_to_md(self, docx_path):
        """Convert a DOCX file to a Markdown file by extracting text."""
        try:
            # Strip .docx extension before adding .md
            base_path = docx_path[:-5] if docx_path.lower().endswith('.docx') else docx_path
            md_path = base_path + ".md"
            print(f"Extracting text from {docx_path}...")
            
            text = docx2txt.process(docx_path)
            
            if text and text.strip():
                basename = os.path.basename(docx_path)
                title = basename[:-5] if basename.lower().endswith('.docx') else basename
                
                md_content = f"# {title}\n\n{text}"
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"✓ Successfully converted to: {md_path}")
                return md_path
            else:
                print(f"Warning: No text extracted from {docx_path}")
                return None
        except Exception as e:
            print(f"Error converting DOCX {docx_path} to MD: {e}")
            return None

    def add_memory(self, user_id, user_name, text):
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
            print(f"Error adding memory: {e}")
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
            # Get current size before appending for the offset
            file_offset = os.path.getsize(log_file) if os.path.exists(log_file) else 0
            
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
                    "last_modified_at": mtime,
                    "file_offset": file_offset,
                    "content_length": len(interaction_text)
                }
            )
            self.index.insert(new_doc)
            self.indexed_files[os.path.abspath(log_file)] = mtime
            self.persist_needed = True
            print(f"Interaction indexed for user {user_name} ({user_id}).")
            
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
        
        OPTIMIZED: No longer iterates through entire docstore. Uses retriever results only.
        """
        if not self.index:
            return []
        
        if not query or not query.strip():
            return []
        
        try:
            # 1. Identify the type of query FIRST to determine retrieval strategy
            query_lower = query.lower()
            is_kaia_query = any(phrase in query_lower for phrase in ["who are you", "who is kaia", "tell me about yourself", "what are you"])
            is_user_identity_query = any(phrase in query_lower for phrase in ["who am i", "what is my name", "my pronoun", "who is"]) and not is_kaia_query
            is_identity_query = is_kaia_query or is_user_identity_query
            
            # Detect casual/social conversation that doesn't need knowledge retrieval
            casual_patterns = [
                "how are you", "what's up", "hey", "hello", "hi ", "sup", "yo ",
                "good morning", "good night", "thanks", "thank you", "bye",
                "my name is", "i'm ", "i am ", "nice to meet", "what do you think",
                "how's it going", "what are you doing", "what are you up to"
            ]
            is_casual = any(phrase in query_lower for phrase in casual_patterns) or len(query_lower.split()) <= 4
            
            # 2. Single retrieval pass with query enrichment
            enriched_query = query
            if user_id and (is_user_identity_query or is_casual) and user_name:
                # Add user context to query to improve retrieval for user-specific questions
                enriched_query = f"{query} user:{user_name}"
            
            # Retrieve with a reasonable limit - fewer for casual chat
            if is_casual:
                retrieve_count = 8
            elif is_identity_query:
                retrieve_count = 15
            else:
                retrieve_count = 12
            retriever = self.index.as_retriever(similarity_top_k=retrieve_count)
            nodes = retriever.retrieve(enriched_query)
            
            # 3. Categorize nodes from retrieval results ONLY (no docstore iteration!)
            persona_results = []
            current_user_logs = []
            lore_results = []
            seen_texts = set()
            u_id_str = str(user_id) if user_id else None
            
            # Lore relevance threshold - higher for casual to filter noise
            lore_threshold = 0.65 if is_casual else 0.45
            
            for node_result in nodes:
                # Handle both NodeWithScore and raw Node objects
                node = node_result.node if hasattr(node_result, 'node') else node_result
                score = node_result.score if hasattr(node_result, 'score') else 1.0
                content = node.get_content()
                
                # Skip duplicates
                content_hash = hash(content[:200]) if len(content) > 200 else hash(content)
                if content_hash in seen_texts:
                    continue
                seen_texts.add(content_hash)
                
                # Quick quality filter - only check first 500 chars for speed
                sample = content[:500]
                if sample:
                    ascii_count = sum(1 for c in sample if c.isascii() and c.isprintable())
                    if (ascii_count / len(sample)) < 0.80:
                        continue
                
                # Truncate very long content to reduce context size
                if len(content) > 800:
                    content = content[:800] + "..."
                
                # Check source metadata
                source = node.metadata.get('source', '')
                file_path = node.metadata.get('file_path', '')
                node_user_id = str(node.metadata.get('user_id', ''))
                
                if source == "persona" or node_user_id == "KAIA_SYSTEM":
                    persona_results.append(f"[KAIA_PERSONA_FRAGMENT]\n{content}")
                elif source == "user_logs" or "user_logs" in file_path:
                    node_user_name = node.metadata.get('user_name', 'Unknown')
                    if u_id_str and node_user_id == u_id_str:
                        current_user_logs.append(f"[USER_PROFILE_AND_HISTORY: {node_user_name.upper()}]\n{content}")
                    # Skip other users' logs entirely to reduce noise
                else:
                    # Apply relevance threshold to lore - filter out noise
                    if score >= lore_threshold:
                        lore_results.append(f"[GENERAL_KNOWLEDGE]\n{content}")
            
            # 4. Combine based on query type with TIGHTER limits
            if is_kaia_query:
                combined = persona_results[:3] + lore_results[:2]
            elif is_user_identity_query:
                combined = current_user_logs[:5] + persona_results[:1]
            elif is_casual:
                # Casual conversation: prioritize user context, include only highly relevant lore
                combined = current_user_logs[:3] + persona_results[:1] + lore_results[:1]
            else:
                # Knowledge query: Lore priority with some user context
                combined = lore_results[:5] + current_user_logs[:2]
            
            # Final top_k slice
            final_results = combined[:top_k]
            query_type = "casual" if is_casual else ("identity" if is_identity_query else "knowledge")
            print(f"Retrieved {len(final_results)} results [{query_type}] (P:{len(persona_results)}, U:{len(current_user_logs)}, L:{len(lore_results)}, thresh:{lore_threshold:.2f})")
            return final_results
            
        except Exception as e:
            print(f"Error during retrieval: {e}")
            import traceback
            traceback.print_exc()
            return []

    def persist(self, force=False):
        """Persist the index to storage if needed."""
        if self.index and (self.persist_needed or force):
            try:
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                self.persist_needed = False
                print(f"✓ Index persisted to {self.persist_dir}")
            except Exception as e:
                print(f"Error persisting index: {e}")

if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
