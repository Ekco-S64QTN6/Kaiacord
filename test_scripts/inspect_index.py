import os
from llama_index.core import StorageContext, load_index_from_storage, Settings
from llama_index.embeddings.ollama import OllamaEmbedding

# Configure Ollama Embedding
embed_model = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434"
)
Settings.embed_model = embed_model

persist_dir = "./storage"
storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
index = load_index_from_storage(storage_context)

print(f"Total nodes in docstore: {len(index.docstore.docs)}")

starkond_nodes = []
for node_id, node in index.docstore.docs.items():
    file_path = node.metadata.get('file_path', '')
    if 'Starkond' in file_path and 'user_profile.md' in file_path:
        starkond_nodes.append(node)

print(f"Found {len(starkond_nodes)} nodes for Starkond.")
for i, node in enumerate(starkond_nodes[:5]):
    print(f"Node {i} metadata: {node.metadata}")
    print(f"Node {i} content snippet: {node.get_content()[:100]}...")
