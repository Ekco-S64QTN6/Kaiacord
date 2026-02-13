import asyncio
from ollama import AsyncClient

async def force_unload():
    client = AsyncClient(host='http://localhost:11434')
    models = ['gemma3:12b', 'nomic-embed-text']
    
    for model in models:
        print(f"🔄 Unloading {model}...")
        try:
            await client.generate(model=model, keep_alive=0)
            print(f"✅ Unloaded {model}")
        except Exception as e:
            print(f"❌ Failed to unload {model}: {e}")

if __name__ == "__main__":
    asyncio.run(force_unload())
