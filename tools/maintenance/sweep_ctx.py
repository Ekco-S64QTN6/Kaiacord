import asyncio
import ollama
import subprocess
import time

async def sweep_ctx():
    client = ollama.AsyncClient()
    for ctx in [2048, 4096, 8192]:
        print(f"\n--- Testing num_ctx: {ctx} with num_gpu: -1 ---")
        await client.generate(model="gemma3:12b", keep_alive=0)
        time.sleep(2)
        
        try:
            await asyncio.wait_for(
                client.generate(model="gemma3:12b", prompt=".", options={"num_gpu": -1, "num_ctx": ctx}),
                timeout=60.0
            )
            ps = await client.ps()
            for m in ps.models:
                if "gemma3:12b" in m.model:
                    vram_mb = m.size_vram / 1024**2
                    print(f"Result: {m.processor} ({vram_mb:.0f}MB VRAM, Size: {m.size/1024**2:.0f}MB)")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(sweep_ctx())
