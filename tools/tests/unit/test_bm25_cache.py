import asyncio
import os
import sys
import psutil

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from utils.core.kaia_rag import KaiaRAG
from llama_index.core.schema import Document

@pytest.mark.asyncio
async def test_bm25(tmp_path):
    avail = psutil.virtual_memory().available / 1024**3
    print(f"Available memory: {avail}GB")

    rag = KaiaRAG()
    # Persist under pytest's tmp_path, never memory/. The previous
    # "./memory/test_rag_storage" left a stale index inside the production
    # memory directory and let one run's artifacts leak into the next.
    rag.persist_dir = str(tmp_path / "rag_storage")
    os.makedirs(rag.persist_dir, exist_ok=True)
    
    rag._initialize_indices()
    
    # Add a mock document
    doc = Document(text="This is an interesting test document about AI and RAG.", metadata={"file_path": "/tmp/mock.txt"})
    rag.indices["knowledge"].insert(doc)
    rag.indexed_files["/tmp/mock.txt"] = {"mtime": 100, "size": 100, "nodes": list(rag.indices["knowledge"].docstore.docs.keys())}
    
    print("Testing pre-warm (builds BM25 and saves)...")
    await rag.pre_warm()
    
    print(f"Cache populated? {'knowledge' in rag.bm25_cache}")
    if 'knowledge' in rag.bm25_cache:
        retriever = rag.bm25_cache['knowledge']
        print(f"Nodes in BM25: {len(retriever.nodes)}")
        print(f"BM25 initialized object: {getattr(retriever, 'bm25', None)}")
    
    print("Testing save...")
    rag._save_bm25_cache('knowledge')
    print(f"File exists after save? {os.path.exists(rag._get_bm25_cache_path('knowledge'))}")

    print("Testing reload...")
    rag.bm25_cache = {} 
    retriever = await asyncio.to_thread(rag._load_bm25_cache, "knowledge")
    if retriever:
        print(f"Successfully loaded knowledge from disk! {retriever.bm25}")
    else:
        print(f"Failed to load knowledge from disk or no data.")

if __name__ == "__main__":
    asyncio.run(test_bm25())
