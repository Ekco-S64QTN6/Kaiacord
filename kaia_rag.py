import os
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings, load_index_from_storage
from llama_index.embeddings.ollama import OllamaEmbedding

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
        """Load all text files from the knowledge base directory and update the index."""
        if not os.path.exists(self.knowledge_base_dir):
            os.makedirs(self.knowledge_base_dir)
            return

        print(f"Refreshing knowledge base from {self.knowledge_base_dir}...")
        try:
            documents = SimpleDirectoryReader(self.knowledge_base_dir).load_data()
            if documents:
                # For SimpleVectorStore, we can just rebuild or insert
                # To avoid duplicates, we'll just rebuild for now if it's small
                # or use refresh_ref_docs if we had doc_ids.
                # For simplicity, we'll just insert and persist.
                for doc in documents:
                    self.index.insert(doc)
                self.index.storage_context.persist(persist_dir=self.persist_dir)
                print(f"Added {len(documents)} documents to the index.")
            else:
                print("No documents found in knowledge base.")
        except Exception as e:
            print(f"Error refreshing knowledge base: {e}")

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
