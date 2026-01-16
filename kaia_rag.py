import os
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter

class KaiaRAG:
    def __init__(self, knowledge_base_dir="./knowledge_base", persist_dir="./storage"):
        self.knowledge_base_dir = knowledge_base_dir
        self.persist_dir = persist_dir
        
        # Configure Ollama Embedding
        self.embed_model = OllamaEmbedding(
            model_name="nomic-embed-text",
            base_url="http://localhost:11434"
        )
        
        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=20)
        Settings.llm = None
        
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
            else:
                print("No existing index found. Initializing empty index.")
                self.index = VectorStoreIndex.from_documents([])
                if not os.path.exists(self.persist_dir):
                    os.makedirs(self.persist_dir)
                self.index.storage_context.persist(persist_dir=self.persist_dir)
            
            self.refresh_knowledge_base()
            
        except Exception as e:
            print(f"Error initializing RAG index: {e}")
            self.index = VectorStoreIndex.from_documents([])

    def refresh_knowledge_base(self):
        """Load all supported files from the knowledge base directory and update the index."""
        if not os.path.exists(self.knowledge_base_dir):
            os.makedirs(self.knowledge_base_dir)
            return

        print(f"Refreshing knowledge base from {self.knowledge_base_dir}...")
        try:
            all_docs = []
            
            # 1. Load regular files (excluding user_memories.txt for special handling)
            reader = SimpleDirectoryReader(
                self.knowledge_base_dir, 
                exclude=["user_memories.txt"]
            )
            all_docs.extend(reader.load_data())
            
            # 2. Special handling for user_memories.txt to split by '---'
            memory_file = os.path.join(self.knowledge_base_dir, "user_memories.txt")
            if os.path.exists(memory_file):
                with open(memory_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Split by '---' and filter out empty fragments
                    fragments = [f.strip() for f in content.split("---") if f.strip()]
                    from llama_index.core import Document
                    for frag in fragments:
                        all_docs.append(Document(text=frag, metadata={"source": "user_memories.txt"}))
            
            if all_docs:
                # Rebuild index with all documents
                self.index = VectorStoreIndex.from_documents(all_docs)
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                print(f"Indexed {len(all_docs)} document nodes.")
            else:
                print("No documents found in knowledge base.")
        except Exception as e:
            print(f"Error refreshing knowledge base: {e}")

    def add_memory(self, text):
        """Append a user-provided memory to user_memories.txt and re-index."""
        memory_file = os.path.join(self.knowledge_base_dir, "user_memories.txt")
        try:
            with open(memory_file, "a", encoding="utf-8") as f:
                f.write(f"\n---\n[RECOVERED MEMORY]: {text}\n")
            
            print(f"Stored new memory fragment in {memory_file}")
            self.refresh_knowledge_base()
            return True
        except Exception as e:
            print(f"Error adding memory: {e}")
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
            return []

if __name__ == "__main__":
    rag = KaiaRAG()
    results = rag.retrieve("Who is Kaia?")
    print(f"Test retrieval results: {results}")
