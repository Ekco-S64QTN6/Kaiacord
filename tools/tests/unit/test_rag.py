import os
import sys

# Test the RAG file loading logic
from llama_index.core import SimpleDirectoryReader, Document
from llama_index.core.node_parser import SentenceSplitter

file_path = "./knowledge_base/corrupt_files/interactions_20260224.md"

def test_load():
    try:
        print("Testing SimpleDirectoryReader...")
        docs = SimpleDirectoryReader(input_files=[file_path]).load_data()
        print(f"Docs loaded: {len(docs)}")
        
        parser = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
        nodes = parser.get_nodes_from_documents(docs)
        print(f"Nodes loaded: {len(nodes)}")
    except Exception as e:
        import traceback
        traceback.print_exc()

test_load()
