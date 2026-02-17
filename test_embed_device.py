import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from utils.core.kaia_rag import KaiaRAG
from utils.infrastructure.system.yaml_config import config

async def test_embedding_device():
    print("Initializing RAG with new CPU-force settings...")
    rag = KaiaRAG()
    
    print("Triggering embedding request for test text...")
    test_text = "The quick brown fox jumps over the lazy dog."
    
    # This will use Settings.embed_model which we just configured
    try:
        embedding = await rag.embed_model.aget_text_embedding(test_text)
        print(f"✅ Embedding successful. Vector length: {len(embedding)}")
    except Exception as e:
        print(f"❌ Embedding failed: {e}")
        return

    print("\n--- Live Status Check ---")
    import subprocess
    ps_output = subprocess.check_output(["ollama", "ps"]).decode()
    print("Ollama PS output:")
    print(ps_output)
    
    smi_output = subprocess.check_output(["nvidia-smi"]).decode()
    if "nomic-embed-text" in smi_output or "638MiB" in smi_output:
        print("❌ FAILURE: nomic-embed-text is still on the GPU!")
    else:
        print("✅ SUCCESS: nomic-embed-text is NOT on the GPU.")

if __name__ == "__main__":
    asyncio.run(test_embedding_device())
