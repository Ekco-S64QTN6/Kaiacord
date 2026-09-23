import asyncio
import os
import sys
import psutil

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from utils.core.kaia_rag import KaiaRAG
from llama_index.core.schema import Document

# Inserting a document embeds it through the live Ollama daemon.
@pytest.mark.ollama
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
    
    assert 'knowledge' in rag.bm25_cache
    assert len(rag.bm25_cache['knowledge'].nodes) >= 1

    rag._save_bm25_cache('knowledge')
    assert os.path.exists(rag._get_bm25_cache_path('knowledge'))

    rag.bm25_cache = {}
    retriever = await asyncio.to_thread(rag._load_bm25_cache, "knowledge")
    assert retriever is not None, "the saved BM25 cache did not load back"

if __name__ == "__main__":
    asyncio.run(test_bm25())
