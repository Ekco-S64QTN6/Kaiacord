import os
import sys
import asyncio
import traceback

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import VectorStoreIndex

async def test():
    file_path = "./knowledge_base/corrupt_files/interactions_20260224.md"
    print("Reading file...")
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    doc = Document(text=content, metadata={"file_path": file_path})
    print("Splitting...")
    parser = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
    nodes = parser.get_nodes_from_documents([doc])
    print(f"Got {len(nodes)} nodes.")
    
    print("Initializing embedding model...")
    embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url="http://localhost:11434")
    
    print("Initializing VectorStoreIndex...")
    index = VectorStoreIndex(nodes=nodes, embed_model=embed_model)
    
    print("Testing insert...")
    try:
        index.insert_nodes(nodes)
        print("Insert successful!")
    except Exception as e:
        print("Error during insert_nodes:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
