import asyncio
import ollama
import subprocess
import time

async def test_value(val):
    print(f"\n--- Testing num_gpu: {val} ---")
    client = ollama.AsyncClient()
    
    # First unload
    print("Unloading...")
    await client.generate(model="gemma3:12b", keep_alive=0)
    time.sleep(2)
    
    print(f"Loading with num_gpu={val}...")
    try:
        start = time.time()
        # Use very small context to ensure it fits
        options = {"num_ctx": 4096}
        if val is not None:
            options["num_gpu"] = val
            
        await asyncio.wait_for(
            client.generate(model="gemma3:12b", prompt=".", options=options),
            timeout=60.0
        )
        duration = time.time() - start
        print(f"Loaded in {duration:.2f}s")
        
        ps = await client.ps()
        found = False
        for m in ps.models:
            if "gemma3:12b" in m.model:
                print(f"Result in ps: {m.processor} ({m.size_vram / 1024**2:.0f}MB VRAM)")
                found = True
        if not found:
            print("Model not found in ps!")
                
        # Check nvidia-smi
        res = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], capture_output=True, text=True)
        print(f"Nvidia-SMI VRAM: {res.stdout.strip()} MB")
        
    except asyncio.TimeoutError:
        print("Timeout reached!")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    # Try: Auto (None), forced GPU (-1), Phase 14 bypass (99), Safe mid-range (32)
    for v in [None, -1, 99, 32, 1]:
        await test_value(v)

asyncio.run(main())
