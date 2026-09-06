import asyncio
import ollama
import subprocess
import time

import pytest


@pytest.mark.gpu
@pytest.mark.ollama
@pytest.mark.slow
@pytest.mark.asyncio
async def test_gemma3():
    client = ollama.AsyncClient()
    print("Testing gemma3:12b with num_gpu: -1 and num_ctx: 8192...")
    try:
        start = time.time()
        await asyncio.wait_for(
            client.generate(
                model="gemma3:12b", 
                prompt=".", 
                options={"num_gpu": -1, "num_ctx": 8192}
            ),
            timeout=120.0
        )
        duration = time.time() - start
        print(f"Loaded in {duration:.2f}s")
        
        ps = await client.ps()
        for m in ps.models:
            if "gemma3" in m.model:
                print(f"Result in ps: {m.processor} ({m.size_vram / 1024**2:.0f}MB VRAM)")
                
        res = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True)
        print(f"Nvidia-SMI VRAM: {res.stdout.strip()} MB")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemma3())
