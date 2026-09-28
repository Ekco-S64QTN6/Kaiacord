import asyncio
import sys
import os
from pathlib import Path

import pytest

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.system.yaml_config import config

# Talks to the live Ollama daemon and shells out to `ollama ps` and
# `nvidia-smi`, so it is not a unit test of anything in this tree.
@pytest.mark.ollama
@pytest.mark.gpu
@pytest.mark.asyncio
async def test_embedding_device():
    print("Initializing RAG with new CPU-force settings...")
    rag = KaiaRAG()
    
    print("Triggering embedding request for test text...")
    test_text = "The quick brown fox jumps over the lazy dog."
    
    # This will use Settings.embed_model which we just configured
    # No try/except: a failed embedding printed a cross and returned, so the
    # test passed whatever happened.
    embedding = await rag.embed_model.aget_text_embedding(test_text)
    assert embedding, "empty embedding"

    print("\n--- Live Status Check ---")
    import subprocess
    ps_output = subprocess.check_output(["ollama", "ps"]).decode()
    print("Ollama PS output:")
    print(ps_output)
    
    smi_output = subprocess.check_output(["nvidia-smi"]).decode()
    assert "nomic-embed-text" not in smi_output, "the embedder is on the GPU"

if __name__ == "__main__":
    asyncio.run(test_embedding_device())
