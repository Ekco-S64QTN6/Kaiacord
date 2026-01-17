import os
import time
import shutil
import logging
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
        self.indexed_files = set()  # Track indexed files to avoid duplicates
        
        # Configure Ollama Embedding
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434"
        )
        
        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=20)
        Settings.llm = Ollama(model="gemma3:12b", request_timeout=360.0)
        
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
        """Populate the set of indexed files from the existing index to avoid re-indexing."""
        if not self.index:
            return
        
        count = 0
        for node in self.index.docstore.docs.values():
            file_path = node.metadata.get('file_path')
            if file_path:
                # Normalize to absolute path to match scanning logic
                self.indexed_files.add(os.path.abspath(file_path))
                count += 1
        
        # Also check for user_memories.txt specifically
        memory_file = os.path.join(self.knowledge_base_dir, "user_memories.txt")
        for node in self.index.docstore.docs.values():
            if node.metadata.get('source') == "user_memories.txt":
                self.indexed_files.add(memory_file)
                break
                
        print(f"Populated {len(self.indexed_files)} already indexed files from storage.")

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
            supported_exts = [".pdf", ".txt", ".md"]
            
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
                        if norm_path not in self.indexed_files and "user_memories.txt" not in file:
                            new_file_paths.append(full_path)

            if not new_file_paths:
                print("No new documents to index.")
            else:
                print(f"Found {len(new_file_paths)} new documents. Processing...")
                
                for file_path in new_file_paths:
                    print(f"Processing: {file_path}")
                    try:
                        # Load single file
                        reader = SimpleDirectoryReader(input_files=[file_path])
                        docs = reader.load_data()
                        
                        if docs:
                            for doc in docs:
                                self.index.insert(doc)
                            
                            self.indexed_files.add(os.path.abspath(file_path))
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
                        # Move corrupt file to quarantine
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
            if os.path.exists(memory_file) and norm_memory_path not in self.indexed_files:
                try:
                    with open(memory_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Split by '---' and filter out empty fragments
                        fragments = [f.strip() for f in content.split("---") if f.strip()]
                        if fragments:
                            print(f"Indexing {len(fragments)} fragments from user_memories.txt...")
                            for idx, frag in enumerate(fragments):
                                self.index.insert(Document(
                                    text=frag, 
                                    metadata={"source": "user_memories.txt", "fragment_id": idx}
                                ))
                            
                            self.indexed_files.add(norm_memory_path)
                            self.index.storage_context.persist(persist_dir=self.persist_dir)
                            print("✓ user_memories.txt indexed.")
                except Exception as e:
                    print(f"Warning: Error loading user_memories.txt: {e}")
                
        except Exception as e:
            print(f"Error refreshing knowledge base: {e}")
            import traceback
            traceback.print_exc()

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
            
            # Use a single file: interactions.txt
            log_file = os.path.join(user_log_dir, "interactions.txt")
            
            # Check if file exists and if it exceeds 100MB
            MAX_SIZE = 100 * 1024 * 1024  # 100MB in bytes
            if os.path.exists(log_file) and os.path.getsize(log_file) >= MAX_SIZE:
                # Rotate the file by renaming it with a timestamp
                rotation_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                rotated_file = os.path.join(user_log_dir, f"interactions_{rotation_timestamp}.txt")
                shutil.move(log_file, rotated_file)
                print(f"Rotated log file to {rotated_file}")
            
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
            new_doc = Document(
                text=interaction_text,
                metadata={
                    "source": "user_logs",
                    "user_id": str(user_id),
                    "user_name": user_name,
                    "timestamp": timestamp,
                    "file_path": log_file
                }
            )
            self.index.insert(new_doc)
            self.index.storage_context.persist(persist_dir=self.persist_dir)
            self.indexed_files.add(os.path.abspath(log_file))
            print(f"Interaction indexed for user {user_name} ({user_id}).")
            
            return True
        except Exception as e:
            print(f"Error logging user interaction: {e}")
            import traceback
            traceback.print_exc()
            return False

    def retrieve(self, query, top_k=3):
        """Retrieve the top_k relevant nodes for a given query."""
        if not self.index:
            return []
        
        try:
            retriever = self.index.as_retriever(similarity_top_k=top_k)
            nodes = retriever.retrieve(query)
            return [node.get_content() for node in nodes]
        except Exception as e:
            print(f"Error during retrieval: {e}")
            import traceback
            traceback.print_exc()
            return []

if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
